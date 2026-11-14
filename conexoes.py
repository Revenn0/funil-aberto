"""Conexões do funil: WhatsApp pela Evolution API (QR no painel), Telegram por bot oficial e integrações pela Composio.

Mesmo desenho do maus-conexoes (apps/maus-conexoes): o dono conecta o próprio WhatsApp lendo um QR numa instância
só dele da Evolution, e a chave da Evolution nunca sai do servidor. Sem a variável de ambiente de um serviço, a função
devolve `simulado` e nada sai da máquina.

Telegram é o Bot API oficial (TELEGRAM_BOT_TOKEN): o comprador abre o bot por um link com o número do pedido e daí em
diante recebe a recuperação e conversa com o robô. Não é a conta pessoal do dono (apps/maus-telegram): mensagem
automática em volume por conta pessoal derruba a credencial de aplicativo da casa inteira.

Composio (COMPOSIO_API_KEY) é a camada de integrações: o dono conecta Gmail, Planilhas, CRM etc. pelo link da
Composio e o funil executa uma ferramenta quando um evento acontece (config.json, "integracoes").
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import nucleo as n

TETO_DIA = int(os.environ.get("FUNIL_TETO_WHATSAPP_DIA", "300"))  # freio contra banimento do número (o mesmo do maus-conexoes)


class ErroConexao(Exception):
    pass


def _so_http(url: str) -> str:
    # As URLs vêm de variável de ambiente; urlopen aceitaria file:// e leria disco do servidor.
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("URL de integração precisa ser http ou https")
    return url


def _http(metodo: str, url: str, corpo: dict | None = None, cabecalhos: dict | None = None, tempo: int = 20) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(_so_http(url), data=dados, method=metodo,  # noqa: S310
                                 headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:  # noqa: S310 (esquema conferido em _so_http)
            bruto = r.read()
    except urllib.error.HTTPError as e:
        # O corpo de erro pode ecoar a requisição; só o código sobe, para nada sensível ir a log ou tela.
        raise ErroConexao(f"{urllib.parse.urlsplit(url).hostname} respondeu {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroConexao(f"sem resposta de {urllib.parse.urlsplit(url).hostname}: {type(e).__name__}") from None
    return json.loads(bruto or b"{}")


# ---------------- WhatsApp: o número que o dono já conectou no maus (maus-conexoes) ----------------
# Na Genesis o WhatsApp do dono já está pareado na Evolution da casa, pela página Conexões do maus. Reaproveitar a rota
# interna /_interno/enviar evita um segundo QR, herda o teto de 300/dia e o modo simular, e não entrega ao funil a chave
# da Evolution da casa (que mexe em todas as instâncias).

def _casa() -> tuple[str, str, str] | None:
    url, tok, usu = (os.environ.get(k) for k in ("CONEXOES_URL", "CONEXOES_SERVICO_TOKEN", "CONEXOES_USUARIO"))
    return (url.rstrip("/"), tok, usu) if url and tok and usu else None


def _casa_enviar(para: list[str], texto: str, simular: bool) -> dict:
    url, tok, usu = _casa()
    return _http("POST", f"{url}/_interno/enviar", {"usuario": usu, "para": para, "texto": texto, "simular": simular},
                 {"Authorization": f"Bearer {tok}"})


# ---------------- WhatsApp (Evolution API própria) ----------------

def _evo() -> tuple[str, str, str] | None:
    url, chave = os.environ.get("EVOLUTION_URL"), os.environ.get("EVOLUTION_KEY")
    if not (url and chave):
        return None
    return url.rstrip("/"), chave, os.environ.get("EVOLUTION_INSTANCIA", "funil")


def whatsapp_estado() -> dict:
    """{configurado, estado: open|connecting|close|ausente, instancia}. Não cria nada."""
    if _casa():
        # simular=true confere que o número do dono está conectado (a rota recusa com 409 se não estiver) sem mandar nada.
        try:
            _casa_enviar(["eu"], "teste de conexão", simular=True)
            return {"configurado": True, "estado": "open", "via": "maus"}
        except ErroConexao as ex:
            return {"configurado": True, "estado": "close" if "409" in str(ex) else "erro", "via": "maus", "erro": str(ex)}
    e = _evo()
    if not e:
        return {"configurado": False, "estado": "simulado"}
    url, chave, inst = e
    try:
        r = _http("GET", f"{url}/instance/connectionState/{inst}", cabecalhos={"apikey": chave})
        return {"configurado": True, "instancia": inst, "estado": (r.get("instance") or {}).get("state", "close")}
    except ErroConexao as ex:
        if "404" in str(ex):
            return {"configurado": True, "instancia": inst, "estado": "ausente"}
        raise


def whatsapp_qr() -> dict:
    """Cria a instância na primeira vez e devolve o QR (data: URI) e o código de pareamento para o dono escanear."""
    e = _evo()
    if not e:
        raise ErroConexao("WhatsApp não configurado: defina EVOLUTION_URL e EVOLUTION_KEY")
    url, chave, inst = e
    if whatsapp_estado()["estado"] == "ausente":
        _http("POST", f"{url}/instance/create", {"instanceName": inst, "integration": "WHATSAPP-BAILEYS", "qrcode": True},
              {"apikey": chave})
    r = _http("GET", f"{url}/instance/connect/{inst}", cabecalhos={"apikey": chave})
    qr = r.get("base64") or ""
    if qr and not qr.startswith("data:"):
        qr = "data:image/png;base64," + qr
    return {"qr": qr, "codigo": r.get("pairingCode") or ""}


def whatsapp_desconectar() -> None:
    e = _evo()
    if e:
        url, chave, inst = e
        _http("DELETE", f"{url}/instance/logout/{inst}", cabecalhos={"apikey": chave})


def _enviados_hoje() -> int:
    return n.mensagens_enviadas_desde("whatsapp", time.time() - 86400)


def whatsapp_enviar(para: str, texto: str) -> str:
    if _casa():
        r = _casa_enviar([n.telefone_e164(para)], texto, simular=False)
        if not r.get("enviados"):
            raise ErroConexao("o WhatsApp não aceitou a mensagem")
        return "enviado"
    e = _evo()
    if not e:
        if os.environ.get("WA_CLOUD_TOKEN") and os.environ.get("WA_PHONE_ID"):
            return _whatsapp_cloud(para, texto)
        return "simulado"
    if _enviados_hoje() >= TETO_DIA:
        raise ErroConexao(f"teto de {TETO_DIA} mensagens de WhatsApp em 24 h atingido")
    url, chave, inst = e
    _http("POST", f"{url}/message/sendText/{inst}", {"number": n.telefone_e164(para), "text": texto}, {"apikey": chave})
    return "enviado"


def _whatsapp_cloud(para: str, texto: str) -> str:
    # A API oficial só aceita texto livre até 24 h depois da última mensagem da pessoa; fora disso exige template.
    _http("POST", f"https://graph.facebook.com/v21.0/{os.environ['WA_PHONE_ID']}/messages",
          {"messaging_product": "whatsapp", "to": n.telefone_e164(para), "type": "text", "text": {"body": texto}},
          {"Authorization": f"Bearer {os.environ['WA_CLOUD_TOKEN']}"})
    return "enviado"


# ---------------- Telegram (bot oficial) ----------------

def _tg(metodo: str, corpo: dict) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ErroConexao("Telegram não configurado: defina TELEGRAM_BOT_TOKEN")
    r = _http("POST", f"{os.environ.get('TELEGRAM_API', 'https://api.telegram.org').rstrip('/')}/bot{token}/{metodo}", corpo)
    if not r.get("ok"):
        raise ErroConexao("o Telegram recusou o pedido")
    return r.get("result") or {}


def telegram_estado() -> dict:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return {"configurado": False, "estado": "simulado"}
    eu = _tg("getMe", {})
    return {"configurado": True, "estado": "open", "bot": eu.get("username", "")}


def telegram_link(pedido_id: str) -> str:
    """Link que abre o bot já com o pedido: /start <pedido> liga o chat ao pedido (deep link do Telegram)."""
    bot = os.environ.get("TELEGRAM_BOT_USUARIO", "")
    return f"https://t.me/{bot}?start={pedido_id}" if bot else ""


def telegram_enviar(chat_id: str, texto: str) -> str:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return "simulado"
    _tg("sendMessage", {"chat_id": chat_id, "text": texto})
    return "enviado"


def telegram_segredo_webhook() -> str:
    """O caminho do webhook leva um segredo derivado do token: ninguém de fora injeta mensagem falsa no robô."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    return hashlib.sha256(f"funil-telegram:{token}".encode()).hexdigest()[:32] if token else ""


def telegram_registrar_webhook(base_url: str) -> dict:
    return _tg("setWebhook", {"url": f"{base_url}/api/telegram/{telegram_segredo_webhook()}",
                              "allowed_updates": ["message"]})


# ---------------- Composio (integrações) ----------------

def _cp(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    chave = os.environ.get("COMPOSIO_API_KEY")
    if not chave:
        raise ErroConexao("Composio não configurada: defina COMPOSIO_API_KEY")
    base = os.environ.get("COMPOSIO_URL", "https://backend.composio.dev").rstrip("/")
    return _http(metodo, f"{base}{caminho}", corpo, {"x-api-key": chave})


def composio_usuario() -> str:
    """user_id da operação na Composio, sem e-mail nem nome.

    COMPOSIO_USUARIO vai como está: é o id de quem já conectou Gmail, Planilhas etc. em outro sistema, e o funil
    reaproveita essas contas. Antes ele passava pelo hash e virava um usuário novo, sem nenhuma conta ligada."""
    if os.environ.get("COMPOSIO_USUARIO"):
        return os.environ["COMPOSIO_USUARIO"]
    base = os.environ.get("BASE_URL", "funil-aberto")
    return "funil_" + hashlib.sha256(f"funil-aberto:{base}".encode()).hexdigest()[:24]


def composio_contas() -> list[dict]:
    if not os.environ.get("COMPOSIO_API_KEY"):
        return []
    q = urllib.parse.urlencode({"user_ids": composio_usuario(), "statuses": "ACTIVE"})
    itens = _cp("GET", f"/api/v3.1/connected_accounts?{q}").get("items", [])
    return [{"toolkit": (i.get("toolkit") or {}).get("slug", ""), "id": i.get("id", ""), "status": i.get("status", "")}
            for i in itens]


def composio_link(toolkit: str) -> str:
    """Link da Composio para o dono autorizar um app (Gmail, Planilhas...). A conta fica do user_id da operação."""
    if not toolkit.replace("_", "").isalnum() or len(toolkit) > 40:
        raise ErroConexao("toolkit inválido")
    sessao = _cp("POST", "/api/v3.1/tool_router/session", {"user_id": composio_usuario()})
    # A API devolve `session_id` (medido em 13/11 contra a Composio real; `id` era suposição e dava KeyError).
    sid = sessao.get("session_id") or sessao.get("id")
    if not sid:
        raise ErroConexao("a Composio não devolveu a sessão")
    r = _cp("POST", f"/api/v3.1/tool_router/session/{sid}/link", {"toolkit": toolkit})
    return r.get("redirect_url", "")


def composio_executar(ferramenta: str, argumentos: dict) -> dict:
    r = _cp("POST", f"/api/v3/tools/execute/{ferramenta}", {"user_id": composio_usuario(), "arguments": argumentos})
    if r.get("successful") is False:
        raise ErroConexao(f"{ferramenta} falhou na Composio")
    return r


def _preencher(valor, contexto: dict):
    if isinstance(valor, str):
        for k, v in contexto.items():
            valor = valor.replace("{" + k + "}", str(v))
        return valor
    if isinstance(valor, list):
        return [_preencher(x, contexto) for x in valor]
    if isinstance(valor, dict):
        return {k: _preencher(v, contexto) for k, v in valor.items()}
    return valor


def disparar(evento: str, contexto: dict) -> list[dict]:
    """Roda as integrações do config.json ligadas a este evento. Uma integração que falha não derruba a venda."""
    feitos = []
    for integ in n.config().get("integracoes", []):
        if integ.get("evento") != evento:
            continue
        if not os.environ.get("COMPOSIO_API_KEY"):
            feitos.append({"ferramenta": integ["ferramenta"], "status": "simulado"})
            continue
        try:
            composio_executar(integ["ferramenta"], _preencher(integ.get("argumentos", {}), contexto))
            feitos.append({"ferramenta": integ["ferramenta"], "status": "enviado"})
        except ErroConexao as e:
            feitos.append({"ferramenta": integ["ferramenta"], "status": "erro", "erro": str(e)})
    for f in feitos:
        n.registrar_mensagem("composio", f["ferramenta"], "", evento, str(contexto.get("pedido", "")), f["status"],
                             f.get("erro", ""))
    return feitos
