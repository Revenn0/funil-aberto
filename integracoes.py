"""Saídas para o mundo: Meta Conversions API, envio de mensagem (WhatsApp, e-mail) e Biblioteca de Anúncios.

Regra: sem a variável de ambiente do serviço, nada sai da máquina. A função devolve
`{"status": "simulado"}` e o painel mostra isso. Ninguém confunde "enviado" com "simulado".
"""
from __future__ import annotations

import json
import os
import smtplib
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage

import conexoes as cx
import nucleo as n

GRAPH = "https://graph.facebook.com/v21.0"


def _post_json(url: str, corpo: dict, cabecalhos: dict | None = None, tempo: int = 10) -> dict:
    req = urllib.request.Request(cx._so_http(url), data=json.dumps(corpo).encode(), method="POST",  # noqa: S310
                                 headers={"Content-Type": "application/json", **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=tempo) as r:  # noqa: S310 (esquema conferido em _so_http)
        return json.loads(r.read() or b"{}")


# ---------- Meta Conversions API (o "tracker server-side") ----------

def evento_capi(nome: str, ped: dict, visitante: dict | None, url: str) -> dict:
    """Monta o evento no formato da Meta. Dado pessoal vai só em sha256, como a Meta exige."""
    v = visitante or {}
    user = {"em": [n.sha(ped["email"])]}
    if ped.get("telefone"):
        user["ph"] = [n.sha(n.telefone_e164(ped["telefone"]))]
    if v.get("fbclid"):
        user["fbc"] = f"fb.1.{int(v['criado'] * 1000)}.{v['fbclid']}"
    if v.get("ip"):
        user["client_ip_address"] = v["ip"]
    if v.get("ua"):
        user["client_user_agent"] = v["ua"]
    return {
        "event_name": nome, "event_time": int(time.time()), "event_id": f"{ped['id']}-{nome}",
        "action_source": "website", "event_source_url": url, "user_data": user,
        "custom_data": {"currency": "BRL", "value": ped["valor"], "content_ids": [ped["produto"]]},
    }


def enviar_capi(evento: dict) -> dict:
    pixel, token = os.environ.get("META_PIXEL_ID"), os.environ.get("META_CAPI_TOKEN")
    if not (pixel and token):
        return {"status": "simulado", "motivo": "META_PIXEL_ID/META_CAPI_TOKEN ausentes"}
    corpo = {"data": [evento]}
    if os.environ.get("META_TEST_EVENT_CODE"):
        corpo["test_event_code"] = os.environ["META_TEST_EVENT_CODE"]
    try:
        return {"status": "enviado", "resposta": _post_json(f"{GRAPH}/{pixel}/events?access_token={token}", corpo)}
    except Exception as e:  # noqa: BLE001 - a venda não pode cair porque a Meta caiu
        return {"status": "erro", "erro": type(e).__name__}


# ---------- mensagens ----------

def enviar(canal: str, para: str, texto: str, motivo: str = "", pedido_id: str = "") -> str:
    """Envia por WhatsApp (Evolution ou Cloud API), Telegram (bot) ou e-mail (SMTP ou Gmail pela Composio).
    Devolve o status gravado: enviado, simulado (sem credencial) ou erro."""
    canais = {"whatsapp": cx.whatsapp_enviar, "telegram": cx.telegram_enviar, "email": _email}
    if canal not in canais:
        raise ValueError(f"canal desconhecido: {canal}")
    try:
        status, erro = canais[canal](para, texto), ""
    except cx.ErroConexao as e:
        status, erro = "erro", str(e)
    except Exception as e:  # noqa: BLE001 - mensagem que falha não pode derrubar a venda
        status, erro = "erro", type(e).__name__
    n.registrar_mensagem(canal, para, texto, motivo, pedido_id, status, erro)
    return status


def _email(para: str, texto: str) -> str:
    linhas = texto.strip().splitlines()
    assunto = linhas[0][:120] if linhas else "Mensagem"
    if os.environ.get("EMAIL_VIA") == "composio":
        # Sai do Gmail que o dono conectou na Composio: o e-mail chega do endereço dele, não de um SMTP genérico.
        cx.composio_executar("GMAIL_SEND_EMAIL", {"recipient_email": para, "subject": assunto, "body": texto})
        return "enviado"
    host = os.environ.get("SMTP_HOST")
    if not host:
        return "simulado"
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(texto)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
        s.send_message(msg)
    return "enviado"


def preencher(modelo: str, ped: dict, base_url: str) -> str:
    p = n.produto(ped["produto"]) or {}
    primeiro = (ped.get("nome") or "").split(" ")[0]
    return (modelo.replace("{nome}", primeiro).replace("{produto}", p.get("nome", ""))
            .replace("{link}", f"{base_url}/c/{ped['produto']}?pedido={ped['id']}"))


def rodar_recuperacao(base_url: str) -> list[dict]:
    """Uma rodada da sequência de recuperação. Idempotente por etapa (o contador avança antes de reenviar)."""
    feitos = []
    for ped, etapa in n.recuperacao_pendente():
        if not n.reservar_etapa(ped["id"], ped["etapa_recuperacao"]):
            continue  # outra rodada (outro processo) já pegou esta etapa
        para = {"whatsapp": ped["telefone"], "email": ped["email"],
                "telegram": n.telegram_do_pedido(ped["id"]) or ""}.get(etapa["canal"], "")
        if not para:
            continue
        st = enviar(etapa["canal"], para, preencher(etapa["texto"], ped, base_url), "recuperacao", ped["id"])
        feitos.append({"pedido": ped["id"], "canal": etapa["canal"], "status": st})
    return feitos


# ---------- robô de mensagens (estilo Manychat) ----------

def responder(canal: str, contato: str, texto: str) -> list[str]:
    """Palavra-chave abre um fluxo; cada resposta da pessoa avança um passo. Fluxo é dado no config.json."""
    fluxos = n.config().get("fluxos", {})
    t = (texto or "").strip().lower()
    for nome, f in fluxos.items():
        if any(p in t for p in f.get("palavras", [])):
            n.gravar_conversa(canal, contato, nome, 1)
            return [f["passos"][0]]
    conv = n.conversa(canal, contato)
    if conv and conv["fluxo"] in fluxos:
        passos = fluxos[conv["fluxo"]]["passos"]
        if conv["passo"] < len(passos):
            n.gravar_conversa(canal, contato, conv["fluxo"], conv["passo"] + 1)
            return [passos[conv["passo"]]]
        n.gravar_conversa(canal, contato, None, 0)
    padrao = n.config().get("resposta_padrao")
    return [padrao] if padrao else []


# ---------- espionagem: Biblioteca de Anúncios da Meta ----------

def buscar_anuncios(termo: str, pais: str = "BR", limite: int = 25) -> dict:
    """API oficial da Biblioteca de Anúncios. Limite da Meta: fora da UE/Reino Unido ela só devolve
    anúncios políticos/sociais; para anúncio comercial no Brasil, use a página pública e salve no swipe file."""
    token = os.environ.get("META_AD_LIBRARY_TOKEN")
    if not token:
        return {"status": "simulado", "motivo": "META_AD_LIBRARY_TOKEN ausente",
                "link_publico": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country="
                                f"{pais}&q={urllib.parse.quote(termo)}"}
    q = urllib.parse.urlencode({
        "search_terms": termo, "ad_reached_countries": json.dumps([pais]), "ad_active_status": "ACTIVE",
        "fields": "page_name,ad_creative_bodies,ad_snapshot_url,ad_delivery_start_time", "limit": limite,
        "access_token": token})
    with urllib.request.urlopen(f"{GRAPH}/ads_archive?{q}", timeout=15) as r:  # noqa: S310 (GRAPH é constante https)
        return {"status": "ok", "anuncios": json.loads(r.read()).get("data", [])}
