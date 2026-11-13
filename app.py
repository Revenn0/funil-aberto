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
import html
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import integracoes as ig
import nucleo as n
import pix

VERSAO = "0.1.0"
AQUI = Path(__file__).resolve().parent
LIMITE_CORPO = 64 * 1024
e = html.escape


def base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")


def admin_ok(cabecalho: str, query: dict) -> bool:
    token = os.environ.get("ADMIN_TOKEN", "")
    dado = cabecalho.removeprefix("Bearer ").strip() or query.get("token", "")
    # Sem ADMIN_TOKEN configurado o painel fica fechado: aberto por padrão é vazamento de cliente.
    return bool(token) and hmac.compare_digest(dado.encode(), token.encode())


def assinatura_ok(corpo: bytes, assinatura: str) -> bool:
    segredo = os.environ.get("WEBHOOK_SECRET", "")
    if not segredo:
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura.strip().lower())


# ---------------- páginas ----------------

CSS = """*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,sans-serif;background:#0b0d10;color:#e8eaed}
main{max-width:760px;margin:0 auto;padding:24px 16px}a{color:#7cc4ff}h1{line-height:1.2}
.bt{display:block;width:100%;padding:16px;border:0;border-radius:10px;background:#22c55e;color:#04120a;
font-weight:700;font-size:18px;text-align:center;text-decoration:none;cursor:pointer}
input{width:100%;padding:12px;margin:6px 0 12px;border-radius:8px;border:1px solid #333;background:#15181d;color:#fff}
video{width:100%;border-radius:12px;background:#000}.cx{background:#15181d;border-radius:12px;padding:16px;margin:16px 0}
code,textarea{word-break:break-all}table{display:block;overflow-x:auto;width:100%;border-collapse:collapse;font-size:14px}td,th{padding:6px;border-bottom:1px solid #222;text-align:left}
.p{color:#9aa0a6;font-size:13px}.ok{color:#22c55e}"""

TRACKER_JS = """(function(){var k='fa_vid',m=document.cookie.match(/fa_vid=([^;]+)/),v=m?m[1]:null;
var q=new URLSearchParams(location.search),d={referrer:document.referrer,landing:location.pathname};
['utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid','ttclid'].forEach(function(c){if(q.get(c))d[c]=q.get(c)});
window.fa=function(nome,extra){var b=Object.assign({vid:v,nome:nome,produto:document.body.dataset.produto||''},d,extra||{});
return fetch('/t',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),keepalive:true})
.then(function(r){return r.json()}).then(function(j){if(j.vid&&j.vid!==v){v=j.vid;document.cookie=k+'='+v+';path=/;max-age=31536000;samesite=lax'}return j})};
window.fa('visita');})();"""


def pagina(titulo: str, corpo: str, produto: str = "") -> str:
    return (f"<!doctype html><html lang=pt-BR><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(titulo)}</title><style>{CSS}</style></head><body data-produto='{e(produto)}'><main>{corpo}</main>"
            f"<script src=/t.js></script></body></html>")


def pg_inicio() -> str:
    itens = "".join(f"<li><a href='/v/{e(p['slug'])}'>{e(p['nome'])}</a> (R$ {p['preco']:.2f})</li>" for p in n.config()["produtos"])
    return pagina("Funil Aberto", f"""<h1>Funil Aberto</h1><p>Tracker, VSL, checkout com Pix, área de membros,
recuperação de carrinho, robô de WhatsApp e biblioteca de anúncios. Um processo, código aberto (MIT).</p>
<div class=cx><b>Produtos</b><ul>{itens}</ul></div><p class=p>Painel do operador em <code>/painel?token=...</code>.
Código: <a href='https://github.com/thiagopatzdorf/funil-aberto'>github.com/thiagopatzdorf/funil-aberto</a>.</p>""")


def pg_vsl(p: dict) -> str:
    v = p.get("vsl", {})
    seg = int(v.get("cta_segundos", 0))
    return pagina(p["nome"], f"""<h1>{e(p['nome'])}</h1><p>{e(p.get('promessa',''))}</p>
<video id=vsl src="{e(v.get('video',''))}" controls playsinline preload=metadata></video>
<p class=p>{e(v.get('credito_video',''))}</p>
<div id=cta hidden><a class=bt href="/c/{e(p['slug'])}" onclick="fa('cta_clique')">{e(v.get('cta_texto','Comprar agora'))}</a></div>
<script>(function(){{var vi=document.getElementById('vsl'),c=document.getElementById('cta'),f={{}},seg={seg};
function mostra(){{if(c.hidden){{c.hidden=false;fa('cta_visto')}}}}if(seg<=0)setTimeout(mostra,0);
vi.addEventListener('play',function(){{if(!f.p){{f.p=1;fa('vsl_play')}}}});
vi.addEventListener('timeupdate',function(){{var t=vi.currentTime,d=vi.duration||1;if(t>=seg)mostra();
[25,50,75,100].forEach(function(x){{if(!f[x]&&t/d*100>=x-0.5){{f[x]=1;fa('vsl_'+x)}}}})}});}})();</script>""", p["slug"])


def pg_checkout(p: dict, erro: str = "") -> str:
    aviso = f"<p style='color:#f87171'>{e(erro)}</p>" if erro else ""
    return pagina(f"Checkout · {p['nome']}", f"""<h1>{e(p['nome'])}</h1><div class=cx><b>R$ {p['preco']:.2f}</b>
<span class=p>· acesso imediato depois do pagamento · garantia de 7 dias</span></div>{aviso}
<form method=post action="/c/{e(p['slug'])}"><input type=hidden name=vid id=vid>
<label>Nome<input name=nome required maxlength=120 autocomplete=name></label>
<label>E-mail (o acesso chega aqui)<input name=email type=email required maxlength=200 autocomplete=email></label>
<label>WhatsApp<input name=telefone inputmode=tel maxlength=20 autocomplete=tel></label>
<button class=bt>Pagar com Pix</button></form>
<script>var m=document.cookie.match(/fa_vid=([^;]+)/);if(m)document.getElementById('vid').value=m[1];</script>""", p["slug"])


def pg_pix(p: dict, ped: dict) -> str:
    cfg = p.get("pix", {})
    codigo = pix.copia_e_cola(cfg["chave"], cfg["nome"], cfg["cidade"], ped["valor"], txid=ped["id"].replace("_", "")[:25])
    pago = ped["status"] == "pago"
    return pagina("Pague com Pix", f"""<h1>{'Pagamento confirmado' if pago else 'Falta só o Pix'}</h1>
<div class=cx><p>Valor: <b>R$ {ped['valor']:.2f}</b>. Copie o código abaixo e cole no app do seu banco (Pix copia e cola).</p>
<textarea id=px rows=4 style='width:100%' readonly>{e(codigo)}</textarea>
<button class=bt onclick="navigator.clipboard.writeText(document.getElementById('px').value);this.textContent='Copiado!'">Copiar código Pix</button></div>
<p class=p>Pedido <code>{e(ped['id'])}</code>. Assim que o pagamento for confirmado o acesso chega em {e(ped['email'])}.</p>
<p id=st class=ok>{'Acesso liberado: confira seu e-mail.' if pago else ''}</p>
<script>setInterval(function(){{fetch('/api/pedido/{e(ped['id'])}').then(r=>r.json()).then(j=>{{if(j.status==='pago')
document.getElementById('st').textContent='Pagamento confirmado! O acesso chegou no seu e-mail.'}})}},5000)</script>""", p["slug"])


def pg_membros(m: dict) -> str:
    feitas = n.aulas_feitas(m["id"])
    blocos = []
    for slug in n.produtos_do_membro(m["id"]):
        p = n.produto(slug)
        if not p:
            continue
        mods = ""
        for mod in p.get("modulos", []):
            aulas = "".join(
                f"<li>{'✔ ' if a['id'] in feitas else ''}<b>{e(a['titulo'])}</b><br><span class=p>{e(a.get('texto',''))}</span>"
                + (f"<video src='{e(a['video'])}' controls></video>" if a.get("video") else "")
                + ("" if a["id"] in feitas else
                   f"<form method=post action='/m/{e(m['token'])}/feito'><input type=hidden name=aula value='{e(a['id'])}'>"
                   "<button>Marcar como vista</button></form>") + "</li>"
                for a in mod["aulas"])
            mods += f"<h3>{e(mod['titulo'])}</h3><ul>{aulas}</ul>"
        blocos.append(f"<div class=cx><h2>{e(p['nome'])}</h2>{mods}</div>")
    return pagina("Área de membros", f"<h1>Olá, {e(m['nome'] or m['email'])}</h1>" + ("".join(blocos) or "<p>Nenhum produto ainda.</p>"))


def pg_painel() -> str:
    linhas = "".join(
        f"<tr><td>{e(r['src'])}</td><td>{e(r['camp'])}</td><td>{r['visita']}</td><td>{r['vsl_play']}</td>"
        f"<td>{r['cta_visto']}</td><td>{r['checkout']}</td><td>{r['compra']}</td><td>R$ {r['receita'] or 0:.2f}</td></tr>"
        for r in n.funil())
    msgs = "".join(f"<tr><td>{e(m['canal'])}</td><td>{e(m['motivo'])}</td><td>{e(m['status'])}</td><td>{e(m['pedido'] or '')}</td></tr>"
                   for m in n.mensagens(20))
    peds = "".join(f"<tr><td><code>{e(r['id'])}</code></td><td>{e(r['produto'])}</td><td>{e(r['status'])}</td><td>R$ {r['valor']:.2f}</td></tr>"
                   for r in n.db().execute("select * from pedido order by criado desc limit 30"))
    return pagina("Painel", f"""<h1>Painel</h1><h2>Funil por origem (visitantes únicos)</h2><table><tr><th>origem</th><th>campanha</th>
<th>visita</th><th>play</th><th>CTA</th><th>checkout</th><th>compra</th><th>receita</th></tr>{linhas}</table>
<h2>Pedidos</h2><table>{peds}</table><p class=p>Confirmar Pix recebido: <code>POST /api/admin/pedido/&lt;id&gt;/pago</code>.</p>
<h2>Mensagens (recuperação e robô)</h2><table>{msgs}</table>""")


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
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

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
            if caminho == "/saude":
                return self._json(200, {"ok": True, "versao": VERSAO})
            if partes[0] == "v" and len(partes) == 2 and (p := n.produto(partes[1])):
                return self._resp(200, pg_vsl(p))
            if partes[0] == "c" and len(partes) == 2 and (p := n.produto(partes[1])):
                ped = n.pedido(q.get("pedido", "")) if q.get("pedido") else None
                if ped and ped["produto"] == p["slug"]:
                    return self._resp(200, pg_pix(p, ped))
                if p.get("link_pagamento"):  # gateway externo (Stripe, Genesis Pagar, Mercado Pago)
                    return self._resp(302, "", extra={"Location": p["link_pagamento"]})
                return self._resp(200, pg_checkout(p))
            if partes[0] == "m" and len(partes) == 2 and (m := n.membro_por_token(partes[1])):
                return self._resp(200, pg_membros(m), extra={"Cache-Control": "no-store"})
            if partes[:2] == ["api", "pedido"] and len(partes) == 3 and (ped := n.pedido(partes[2])):
                return self._json(200, {"status": ped["status"]})  # só o status: o id é o segredo de quem comprou
            if caminho == "/painel":
                if not admin_ok(self.headers.get("Authorization", ""), q):
                    return self._resp(401, pagina("Painel", "<p>Token inválido.</p>"))
                return self._resp(200, pg_painel(), extra={"Cache-Control": "no-store"})
            if partes[:2] == ["api", "admin"]:
                if not admin_ok(self.headers.get("Authorization", ""), q):
                    return self._json(401, {"erro": "token"})
                if partes[2:] == ["funil"]:
                    return self._json(200, n.funil(q.get("produto")))
                if partes[2:] == ["publico"]:
                    return self._json(200, n.publico_hash(q.get("status", "pendente")))
                if partes[2:] == ["spy"]:
                    return self._json(200, ig.buscar_anuncios(q.get("q", ""), q.get("pais", "BR")))
                if partes[2:] == ["anuncios"]:
                    return self._json(200, n.anuncios(q.get("q", "")))
            return self._resp(404, pagina("Não encontrado", "<h1>Página não encontrada</h1>"))
        except Exception as ex:  # noqa: BLE001
            return self._json(500, {"erro": type(ex).__name__})

    def do_POST(self):
        caminho, q = self._rota()
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
                    ped = n.criar_pedido(p["slug"], vid, f.get("nome", ""), f.get("email", ""), f.get("telefone", ""), "pix")
                except ValueError as ex:
                    return self._resp(400, pg_checkout(p, str(ex)))
                ig.enviar_capi(ig.evento_capi("InitiateCheckout", ped, _visitante(vid), f"{base_url()}/c/{p['slug']}"))
                return self._resp(303, "", extra={"Location": f"/c/{p['slug']}?pedido={ped['id']}"})
            if partes[0] == "m" and len(partes) == 3 and partes[2] == "feito" and (m := n.membro_por_token(partes[1])):
                n.marcar_aula(m["id"], dict(urllib.parse.parse_qsl(corpo.decode())).get("aula", ""))
                return self._resp(303, "", extra={"Location": f"/m/{m['token']}"})
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
            if partes[:2] == ["api", "admin"]:
                if not admin_ok(self.headers.get("Authorization", ""), q):
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


def _visitante(vid: str) -> dict | None:
    r = n.db().execute("select * from visitante where id=?", (vid,)).fetchone()
    return dict(r) if r else None


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
        ig.enviar_capi(ig.evento_capi("Purchase", ped, _visitante(ped["visitante"]), f"{base_url()}/c/{ped['produto']}"))
    return {"pedido": r["pedido"]["id"], "status": "pago", "novo": r["novo"]}


def _laco_recuperacao():
    while True:
        time.sleep(60)
        try:
            ig.rodar_recuperacao(base_url())
        except Exception as ex:  # noqa: BLE001 - o laço não pode morrer
            print(f"recuperacao falhou: {type(ex).__name__}", file=sys.stderr)


def main(argv: list[str]) -> None:
    if argv[1:2] == ["tick"]:
        print(json.dumps(ig.rodar_recuperacao(base_url()), ensure_ascii=False))
        return
    n.db()
    threading.Thread(target=_laco_recuperacao, daemon=True).start()
    porta = int(os.environ.get("PORT", "8080"))
    print(f"funil-aberto {VERSAO} em http://0.0.0.0:{porta}")
    ThreadingHTTPServer(("0.0.0.0", porta), H).serve_forever()


if __name__ == "__main__":
    main(sys.argv)
