"""funil-aberto: a operação de venda online inteira num processo só (MIT).

Tracker com atribuição + Meta CAPI, página de VSL, checkout com Pix direto na sua chave,
área de membros, recuperação de checkout abandonado (WhatsApp/e-mail), robô de mensagens
por palavra-chave (estilo Manychat) e biblioteca de anúncios (spy). Só biblioteca padrão
do Python 3.12 + SQLite.

    python3 app.py           servidor em PORT (padrão 8080)
    python3 app.py tick      uma rodada da recuperação de checkout (para cron)

Variáveis: PORT, DATA_DIR, BASE_URL, ADMIN_TOKEN (painel e API admin), WEBHOOK_SECRET (gateway),
META_PIXEL_ID, META_CAPI_TOKEN, META_TEST_EVENT_CODE, META_AD_LIBRARY_TOKEN,
EVOLUTION_URL/EVOLUTION_KEY/EVOLUTION_INSTANCIA ou WA_CLOUD_TOKEN/WA_PHONE_ID, SMTP_HOST/PORT/USER/PASS/FROM.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import conexoes as cx
import integracoes as ig
import nucleo as n
import paginas as pg
import pix

VERSAO = "0.1.0"
AQUI = Path(__file__).resolve().parent
LIMITE_CORPO = 64 * 1024


def base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")


def _selo_admin() -> str:
    # O cookie guarda um derivado do token, nunca o token: um cookie vazado não vira a chave da API.
    return hmac.new(os.environ.get("ADMIN_TOKEN", "").encode(), b"funil-admin-cookie", hashlib.sha256).hexdigest()


def token_ok(dado: str) -> bool:
    token = os.environ.get("ADMIN_TOKEN", "")
    # Sem ADMIN_TOKEN configurado o painel fica fechado: aberto por padrão é vazamento de cliente.
    return bool(token) and bool(dado) and hmac.compare_digest(dado.encode(), token.encode())


def admin_ok(cabecalhos) -> bool:
    """Bearer (API) ou cookie de sessão (painel). Token na URL não vale: URL vai para histórico e log de proxy."""
    if token_ok(cabecalhos.get("Authorization", "").removeprefix("Bearer ").strip()):
        return True
    if not os.environ.get("ADMIN_TOKEN"):
        return False
    for parte in cabecalhos.get("Cookie", "").split(";"):
        k, _, v = parte.strip().partition("=")
        if k == "fa_adm" and hmac.compare_digest(v.encode(), _selo_admin().encode()):
            return True
    return False


def cookie_admin(valor: str, idade: int) -> str:
    seguro = "; Secure" if base_url().startswith("https://") else ""
    return f"fa_adm={valor}; Path=/; HttpOnly; SameSite=Strict; Max-Age={idade}{seguro}"


def assinatura_ok(corpo: bytes, assinatura: str) -> bool:
    segredo = os.environ.get("WEBHOOK_SECRET", "")
    if not segredo:
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura.strip().lower())


# ---------------- páginas ----------------

TRACKER_JS = """(function(){var k='fa_vid',m=document.cookie.match(/fa_vid=([^;]+)/),v=m?m[1]:null;
var q=new URLSearchParams(location.search),d={referrer:document.referrer,landing:location.pathname};
['utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid','ttclid'].forEach(function(c){if(q.get(c))d[c]=q.get(c)});
window.fa=function(nome,extra){var b=Object.assign({vid:v,nome:nome,produto:document.body.dataset.produto||''},d,extra||{});
return fetch('/t',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),keepalive:true})
.then(function(r){return r.json()}).then(function(j){if(j.vid&&j.vid!==v){v=j.vid;document.cookie=k+'='+v+';path=/;max-age=31536000;samesite=lax'}return j})};
window.fa('visita');})();"""


def marca() -> str:
    return n.config().get("marca", "Funil Aberto")


def pg_inicio() -> str:
    return pg.inicio(marca(), n.config()["produtos"])


def pg_vsl(p: dict) -> str:
    return pg.vsl(marca(), p)


def pg_checkout(p: dict, erro: str = "") -> str:
    return pg.checkout(marca(), p, n.order_bump(p), erro)


def pg_pix(p: dict, ped: dict) -> str:
    cfg = p.get("pix", {})
    codigo = pix.copia_e_cola(cfg["chave"], cfg["nome"], cfg["cidade"], ped["valor"], txid=ped["id"].replace("_", "")[:25])
    nomes = [(n.produto(s) or {"nome": s})["nome"] for s in n.itens_do_pedido(ped)]
    return pg.pix_pagina(marca(), p, ped, codigo, cx.telegram_link(ped["id"]), nomes)


def _produtos_do(m: dict) -> list[dict]:
    return [p for p in (n.produto(s) for s in n.produtos_do_membro(m["id"])) if p]


def pg_membros(m: dict) -> str:
    return pg.membros(marca(), m, _produtos_do(m), n.aulas_feitas(m["id"]), m["token"])


def pg_aula(m: dict, aula_id: str) -> str | None:
    return pg.aula(marca(), m, _produtos_do(m), aula_id, n.aulas_feitas(m["id"]), m["token"])


def pg_painel() -> str:
    return pg.painel(n.resumo(), n.funil(), n.pedidos_recentes(), n.mensagens(20), n.vendas_por_dia(14))


TOOLKITS = ("gmail", "googlesheets", "hubspot", "notion", "slack", "googlecalendar", "airtable", "trello")


def _estado_seguro(f) -> dict:
    try:
        return f()
    except cx.ErroConexao as ex:
        return {"configurado": True, "estado": "erro", "erro": str(ex)}


def pg_conexoes(aviso: str = "") -> str:
    wa, tg = _estado_seguro(cx.whatsapp_estado), _estado_seguro(cx.telegram_estado)
    try:
        contas = cx.composio_contas()
    except cx.ErroConexao as ex:
        contas, aviso = [], aviso or str(ex)
    return pg.conexoes(wa, tg, bool(os.environ.get("COMPOSIO_API_KEY")), TOOLKITS, {c["toolkit"] for c in contas},
                       cx.TETO_DIA, aviso)


pg_qr, pg_entrar = pg.qr_whatsapp, pg.entrar

# Arquivos servidos de static/: lista fechada de tipos, nunca caminho com "..".
ESTATICOS = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".woff2": "font/woff2",
             ".webp": "image/webp", ".mp4": "video/mp4"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' https:; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https:")


# ---------------- servidor ----------------

class H(BaseHTTPRequestHandler):
    server_version = f"funil-aberto/{VERSAO}"

    def log_message(self, *a):  # sem IP nem caminho com dado pessoal no log
        pass

    def _resp(self, codigo: int, corpo: str | bytes, tipo: str = "text/html; charset=utf-8", extra: dict | None = None):
        dados = corpo.encode() if isinstance(corpo, str) else corpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if tipo.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def _estatico(self, arq, tipo: str):
        """Arquivo de static/, com Range: o Safari do iPhone só toca vídeo se o servidor responder 206 por pedaço."""
        dados, cab = arq.read_bytes(), {"Cache-Control": "public, max-age=86400", "Accept-Ranges": "bytes"}
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if not m or not (m.group(1) or m.group(2)):
            return self._resp(200, dados, tipo, cab)
        total = len(dados)
        ini, fim = (int(m.group(1)), int(m.group(2) or total - 1)) if m.group(1) else (max(0, total - int(m.group(2))), total - 1)
        if ini >= total or ini > fim:
            return self._resp(416, b"", tipo, {**cab, "Content-Range": f"bytes */{total}"})
        fim = min(fim, total - 1)
        return self._resp(206, dados[ini:fim + 1], tipo, {**cab, "Content-Range": f"bytes {ini}-{fim}/{total}"})

    def _json(self, codigo: int, obj) -> None:
        self._resp(codigo, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _corpo(self) -> bytes:
        tam = int(self.headers.get("Content-Length") or 0)
        if tam > LIMITE_CORPO:
            raise ValueError("corpo grande demais")
        return self.rfile.read(tam)

    def _ip(self) -> str:
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def _rota(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path.rstrip("/") or "/", dict(urllib.parse.parse_qsl(u.query))

    def do_GET(self):
        caminho, q = self._rota()
        partes = caminho.strip("/").split("/")
        try:
            if caminho == "/":
                return self._resp(200, pg_inicio())
            if caminho == "/t.js":
                return self._resp(200, TRACKER_JS, "application/javascript; charset=utf-8")
            if partes[0] == "static" and len(partes) in (2, 3) and ".." not in caminho:
                arq = AQUI.joinpath(*partes)
                tipo = ESTATICOS.get(arq.suffix)
                if tipo and arq.is_file():
                    return self._estatico(arq, tipo)
            if caminho == "/saude":
                return self._json(200, {"ok": True, "versao": VERSAO, "processo": os.getpid()})
            if partes[0] == "v" and len(partes) == 2 and (p := n.produto(partes[1])):
                return self._resp(200, pg_vsl(p))
            if partes[0] == "c" and len(partes) == 2 and (p := n.produto(partes[1])):
                ped = n.pedido(q.get("pedido", "")) if q.get("pedido") else None
                if ped and ped["produto"] == p["slug"]:
                    return self._resp(200, pg_pix(p, ped))
                return self._resp(200, pg_checkout(p))
            if partes[0] == "m" and len(partes) == 2 and (m := n.membro_por_token(partes[1])):
                return self._resp(200, pg_membros(m), extra={"Cache-Control": "no-store"})
            if (partes[0] == "m" and len(partes) == 4 and partes[2] == "aula" and (m := n.membro_por_token(partes[1]))
                    and (pagina := pg_aula(m, partes[3]))):
                return self._resp(200, pagina, extra={"Cache-Control": "no-store"})
            if partes[:2] == ["api", "pedido"] and len(partes) == 3 and (ped := n.pedido(partes[2])):
                return self._json(200, {"status": ped["status"]})  # só o status: o id é o segredo de quem comprou
            if caminho == "/entrar":
                return self._resp(200, pg_entrar())
            if caminho == "/sair":
                return self._resp(303, "", extra={"Location": "/entrar", "Set-Cookie": cookie_admin("", 0)})
            if partes[0] == "painel":
                if not admin_ok(self.headers):
                    return self._resp(303, "", extra={"Location": "/entrar"})
                pagina_admin = {"/painel": pg_painel, "/painel/conexoes": pg_conexoes}.get(caminho)
                if pagina_admin:
                    return self._resp(200, pagina_admin(), extra={"Cache-Control": "no-store"})
            if partes[:2] == ["api", "admin"]:
                if not admin_ok(self.headers):
                    return self._json(401, {"erro": "token"})
                if partes[2:] == ["funil"]:
                    return self._json(200, n.funil(q.get("produto")))
                if partes[2:] == ["publico"]:
                    return self._json(200, n.publico_hash(q.get("status", "pendente")))
                if partes[2:] == ["spy"]:
                    return self._json(200, ig.buscar_anuncios(q.get("q", ""), q.get("pais", "BR")))
                if partes[2:] == ["anuncios"]:
                    return self._json(200, n.anuncios(q.get("q", "")))
            return self._resp(404, pg.nao_encontrado())
        except Exception as ex:  # noqa: BLE001
            return self._json(500, {"erro": type(ex).__name__})

    def do_POST(self):
        caminho, _q = self._rota()
        partes = caminho.strip("/").split("/")
        try:
            corpo = self._corpo()
            if caminho == "/t":
                d = json.loads(corpo or b"{}")
                vid = n.visitante(d.get("vid"), d, self._ip(), self.headers.get("User-Agent", ""))
                n.evento(vid, str(d.get("nome", "")), str(d.get("produto", "")))
                return self._json(200, {"vid": vid})
            if partes[0] == "c" and len(partes) == 2 and (p := n.produto(partes[1])):
                f = dict(urllib.parse.parse_qsl(corpo.decode()))
                vid = n.visitante(f.get("vid") or None, {}, self._ip(), self.headers.get("User-Agent", ""))
                try:
                    if f.get("email2") is not None and f.get("email2", "").strip().lower() != f.get("email", "").strip().lower():
                        raise ValueError("Os dois e-mails não são iguais. Confira para o acesso não se perder.")
                    ped = n.criar_pedido(p["slug"], vid, f.get("nome", ""), f.get("email", ""), f.get("telefone", ""), "pix",
                                         com_bump=f.get("bump") == "1")
                except ValueError as ex:
                    return self._resp(400, pg_checkout(p, str(ex)))
                ig.enviar_capi(ig.evento_capi("InitiateCheckout", ped, _visitante(vid), f"{base_url()}/c/{p['slug']}"))
                cx.disparar("checkout", _contexto(ped, p))
                return self._resp(303, "", extra={"Location": f"/c/{p['slug']}?pedido={ped['id']}"})
            if partes[0] == "m" and len(partes) == 3 and partes[2] == "feito" and (m := n.membro_por_token(partes[1])):
                aula_id = dict(urllib.parse.parse_qsl(corpo.decode())).get("aula", "")
                n.marcar_aula(m["id"], aula_id)
                volta = f"/m/{m['token']}/aula/{urllib.parse.quote(aula_id)}" if pg_aula(m, aula_id) else f"/m/{m['token']}"
                return self._resp(303, "", extra={"Location": volta})
            if caminho == "/api/webhook/pagamento":
                if not assinatura_ok(corpo, self.headers.get("X-Assinatura", "")):
                    return self._json(401, {"erro": "assinatura"})
                d = json.loads(corpo)
                if d.get("status") != "pago":
                    return self._json(200, {"ignorado": True})
                return self._json(200, liberar(d["pedido"]))
            if caminho == "/api/bot/entrada":
                if not assinatura_ok(corpo, self.headers.get("X-Assinatura", "")):
                    return self._json(401, {"erro": "assinatura"})
                d = json.loads(corpo)
                canal, contato = d.get("canal", "whatsapp"), str(d.get("de", ""))[:40]
                respostas = [r.replace("{base}", base_url()) for r in ig.responder(canal, contato, str(d.get("texto", "")))]
                if d.get("enviar"):
                    for r in respostas:
                        ig.enviar(canal, contato, r, "robo")
                return self._json(200, {"respostas": respostas})
            if caminho == "/entrar":
                if not token_ok(dict(urllib.parse.parse_qsl(corpo.decode())).get("token", "")):
                    time.sleep(1)  # freia quem tenta adivinhar o token
                    return self._resp(401, pg_entrar("Token inválido."))
                return self._resp(303, "", extra={"Location": "/painel", "Set-Cookie": cookie_admin(_selo_admin(), 43200)})
            if partes[0] == "api" and len(partes) == 3 and partes[1] == "telegram":
                segredo = cx.telegram_segredo_webhook()
                if not segredo or not hmac.compare_digest(partes[2].encode(), segredo.encode()):
                    return self._json(404, {"erro": "rota"})
                telegram_entrada(json.loads(corpo or b"{}"))
                return self._json(200, {"ok": True})
            if partes[0] == "painel":
                if not admin_ok(self.headers):
                    return self._resp(303, "", extra={"Location": "/entrar"})
                return self._painel_post(caminho, partes, corpo)
            if partes[:2] == ["api", "admin"]:
                if not admin_ok(self.headers):
                    return self._json(401, {"erro": "token"})
                if len(partes) == 5 and partes[2] == "pedido" and partes[4] == "pago":
                    return self._json(200, liberar(partes[3]))
                if partes[2:] == ["recuperacao"]:
                    return self._json(200, ig.rodar_recuperacao(base_url()))
                if partes[2:] == ["anuncios"]:
                    d = json.loads(corpo)
                    return self._json(200, {"id": n.salvar_anuncio(d.get("fonte", "manual"), d.get("anunciante", ""),
                                                                    d.get("texto", ""), d.get("url", ""), d.get("nota", ""))})
            return self._json(404, {"erro": "rota"})
        except KeyError as ex:
            return self._json(404, {"erro": str(ex)})
        except (ValueError, json.JSONDecodeError) as ex:
            return self._json(400, {"erro": str(ex)[:200]})


    def _painel_post(self, caminho: str, partes: list[str], corpo: bytes):
        f = dict(urllib.parse.parse_qsl(corpo.decode()))
        try:
            if len(partes) == 4 and partes[1] == "pedido" and partes[3] == "pago":
                liberar(partes[2])
                return self._resp(303, "", extra={"Location": "/painel"})
            if caminho == "/painel/conexoes/whatsapp/qr":
                return self._resp(200, pg_qr(cx.whatsapp_qr()), extra={"Cache-Control": "no-store"})
            if caminho == "/painel/conexoes/whatsapp/desconectar":
                cx.whatsapp_desconectar()
            elif caminho == "/painel/conexoes/telegram/webhook":
                cx.telegram_registrar_webhook(base_url())
            elif caminho == "/painel/conexoes/composio":
                return self._resp(303, "", extra={"Location": cx.composio_link(f.get("toolkit", ""))})
            else:
                return self._resp(404, pg.nao_encontrado())
        except cx.ErroConexao as ex:
            return self._resp(502, pg_conexoes(str(ex)))
        return self._resp(303, "", extra={"Location": "/painel/conexoes"})


def telegram_entrada(update: dict) -> None:
    """Mensagem que chega no bot: /start <pedido> liga o chat ao pedido; o resto vai para o robô."""
    msg = update.get("message") or {}
    chat, texto = str((msg.get("chat") or {}).get("id", "")), str(msg.get("text") or "")
    if not chat:
        return
    if texto.startswith("/start"):
        pid = texto.removeprefix("/start").strip()
        if pid and n.ligar_telegram(pid, chat):
            ig.enviar("telegram", chat, "Pronto! Você vai receber por aqui a confirmação do pagamento e o acesso.", "telegram", pid)
            return
    for r in ig.responder("telegram", chat, texto):
        ig.enviar("telegram", chat, r.replace("{base}", base_url()), "robo")


def _visitante(vid: str) -> dict | None:
    return n.visitante_por_id(vid)


def _contexto(ped: dict, p: dict) -> dict:
    """O que um modelo de integração pode usar: {pedido}, {nome}, {email}, {telefone}, {produto}, {valor}, {status}."""
    return {"pedido": ped["id"], "nome": ped["nome"], "email": ped["email"], "telefone": ped["telefone"],
            "produto": p.get("nome", ped["produto"]), "valor": f"{ped['valor']:.2f}", "status": ped["status"]}


def liberar(pid: str) -> dict:
    """Pagamento confirmado: libera acesso, manda o link de membros e conta a venda na Meta (uma vez só)."""
    r = n.marcar_pago(pid)
    if r["novo"]:
        ped, mem = r["pedido"], r["membro"]
        p = n.produto(ped["produto"]) or {}
        link = f"{base_url()}/m/{mem['token']}"
        ig.enviar("email", ped["email"], f"Seu acesso ao {p.get('nome','')}\n\nEntre aqui: {link}", "acesso", pid)
        if ped["telefone"]:
            ig.enviar("whatsapp", ped["telefone"], f"Pagamento confirmado! Seu acesso: {link}", "acesso", pid)
        if chat := n.telegram_do_pedido(pid):
            ig.enviar("telegram", chat, f"Pagamento confirmado! Seu acesso: {link}", "acesso", pid)
        cx.disparar("compra", _contexto(ped, p))
        ig.enviar_capi(ig.evento_capi("Purchase", ped, _visitante(ped["visitante"]), f"{base_url()}/c/{ped['produto']}"))
    return {"pedido": r["pedido"]["id"], "status": "pago", "novo": r["novo"]}


def _laco_recuperacao():
    while True:
        time.sleep(60)
        try:
            ig.rodar_recuperacao(base_url())
        except Exception as ex:  # noqa: BLE001 - o laço não pode morrer
            print(f"recuperacao falhou: {type(ex).__name__}", file=sys.stderr)


class Servidor(ThreadingHTTPServer):
    # A fila padrão do socketserver é 5: com 64 clientes chegando juntos o kernel recusava a conexão e o navegador
    # só tentava de novo 1 a 2 s depois (p99 de 2 s medido em 15/11 com 64 clientes).
    request_queue_size = 512
    daemon_threads = True


def _servir(servidor: Servidor, com_laco: bool) -> None:
    if com_laco:
        threading.Thread(target=_laco_recuperacao, daemon=True).start()
    servidor.serve_forever()


def _supervisionar(servidor: Servidor, workers: int, laco: bool) -> None:
    """WORKERS > 1: o pai só supervisiona. Os filhos dividem o mesmo socket (o kernel distribui as conexões), cada
    um com o seu núcleo de CPU; filho que cai nasce de novo. Só o filho 0 roda o laço da recuperação, e a reserva
    atômica de etapa (nucleo.reservar_etapa) garante uma mensagem só mesmo se duas rodadas se cruzarem."""
    filhos: dict[int, int] = {}
    parar = False

    def nascer(i: int) -> None:
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            try:
                _servir(servidor, laco and i == 0)
            finally:
                os._exit(0)
        filhos[pid] = i

    def ao_terminar(*_):
        nonlocal parar
        parar = True
        for pid in list(filhos):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    for i in range(workers):
        nascer(i)
    signal.signal(signal.SIGTERM, ao_terminar)
    signal.signal(signal.SIGINT, ao_terminar)
    while filhos:
        try:
            pid, _ = os.wait()
        except ChildProcessError:
            break
        i = filhos.pop(pid, None)
        if i is not None and not parar:
            nascer(i)


def main(argv: list[str]) -> None:
    if argv[1:2] == ["tick"]:
        print(json.dumps(ig.rodar_recuperacao(base_url()), ensure_ascii=False))
        return
    n.db()       # schema e migração uma vez, antes de qualquer fork
    n.fechar()   # conexão SQLite não atravessa fork
    porta = int(os.environ.get("PORT", "8080"))
    workers = max(1, int(os.environ.get("WORKERS", "1")))
    # FUNIL_RECUPERACAO_LACO=0 quando quem roda a recuperação é um agendador de fora (`python3 app.py tick` ou
    # POST /api/admin/recuperacao): com o processo escalando a zero, o laço interno dormiria junto.
    laco = os.environ.get("FUNIL_RECUPERACAO_LACO", "1") != "0"
    print(f"funil-aberto {VERSAO} em http://0.0.0.0:{porta} ({workers} processo(s))", flush=True)
    # BIND=127.0.0.1 quando o contêiner usa a rede do host: sem isso a porta abriria em todas as interfaces da máquina.
    servidor = Servidor((os.environ.get("BIND", "0.0.0.0"), porta), H)  # noqa: S104 (contêiner; BIND restringe)
    if workers == 1 or not hasattr(os, "fork"):
        _servir(servidor, laco)
    else:
        _supervisionar(servidor, workers, laco)


if __name__ == "__main__":
    main(sys.argv)
