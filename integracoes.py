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

import nucleo as n

GRAPH = "https://graph.facebook.com/v21.0"


def _post_json(url: str, corpo: dict, cabecalhos: dict | None = None, tempo: int = 10) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=tempo) as r:
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
    """Envia por WhatsApp (Evolution API ou Cloud API) ou e-mail (SMTP). Devolve o status gravado."""
    try:
        status = {"whatsapp": _whatsapp, "email": _email}[canal](para, texto)
        erro = ""
    except KeyError:
        raise ValueError(f"canal desconhecido: {canal}") from None
    except Exception as e:  # noqa: BLE001
        status, erro = "erro", type(e).__name__
    n.registrar_mensagem(canal, para, texto, motivo, pedido_id, status, erro)
    return status


def _whatsapp(para: str, texto: str) -> str:
    numero = n.telefone_e164(para)
    if os.environ.get("EVOLUTION_URL") and os.environ.get("EVOLUTION_KEY") and os.environ.get("EVOLUTION_INSTANCIA"):
        url = f"{os.environ['EVOLUTION_URL'].rstrip('/')}/message/sendText/{os.environ['EVOLUTION_INSTANCIA']}"
        _post_json(url, {"number": numero, "text": texto}, {"apikey": os.environ["EVOLUTION_KEY"]})
        return "enviado"
    if os.environ.get("WA_CLOUD_TOKEN") and os.environ.get("WA_PHONE_ID"):
        # A Cloud API oficial só aceita texto livre dentro da janela de 24 h; fora dela exige template aprovado.
        url = f"{GRAPH}/{os.environ['WA_PHONE_ID']}/messages"
        _post_json(url, {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}},
                   {"Authorization": f"Bearer {os.environ['WA_CLOUD_TOKEN']}"})
        return "enviado"
    return "simulado"


def _email(para: str, texto: str) -> str:
    host = os.environ.get("SMTP_HOST")
    if not host:
        return "simulado"
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
    msg["To"] = para
    linhas = texto.strip().splitlines()
    msg["Subject"] = linhas[0][:120] if linhas else "Mensagem"
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
        n.avancar_recuperacao(ped["id"])
        para = ped["telefone"] if etapa["canal"] == "whatsapp" else ped["email"]
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
    with urllib.request.urlopen(f"{GRAPH}/ads_archive?{q}", timeout=15) as r:
        return {"status": "ok", "anuncios": json.loads(r.read()).get("data", [])}
