"""As telas do funil, no padrão dos checkouts de infoproduto do mercado brasileiro.

Comprador: página de vendas escura com vídeo no centro (VSL); checkout claro com banner, prazo da oferta, capa, campos
grandes, escolha do pagamento, order bump, botão verde, depoimentos e selo de garantia; Pix com QR; área de membros
escura com capas por módulo e página de aula. Dono: painel com menu lateral, números, gráfico de vendas e conexões.

Só monta HTML (não toca banco nem rede). Todo texto de fora passa por `e()`. Estilo em static/estilo.css e
comportamento em static/funil.js: nenhum script inline (CSP `script-src 'self'`).
"""
from __future__ import annotations

import functools
import hashlib
import html
from pathlib import Path

e = html.escape

NOMES_ESTADO = {"open": ("conectado", "ok"), "connecting": ("aguardando leitura do QR", "espera vivo"),
                "close": ("desconectado", "erro"), "ausente": ("não conectado", ""),
                "simulado": ("não configurado", ""), "erro": ("com erro", "erro")}

# Ícones desenhados aqui (traço simples, 24x24): nada de biblioteca de ícone de fora.
_I = {
    "cadeado": '<path d="M6 10V8a6 6 0 0 1 12 0v2"/><rect x="4" y="10" width="16" height="11" rx="2"/>',
    "escudo": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "pix": '<path d="m12 3 4.2 4.2-4.2 4.2-4.2-4.2zM12 12.6l4.2 4.2L12 21l-4.2-4.2zM3 12l4.2-4.2 4.2 4.2-4.2 4.2zM12.6 12l4.2-4.2L21 12l-4.2 4.2z"/>',
    "cartao": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
    "raio": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "play": '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4z"/>',
    "grafico": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "tomada": '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
    "sair": '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11"/>',
    "zap": '<path d="M5 19l1.4-4A8 8 0 1 1 9 18z"/><path d="M9 10c.5 2 2 3.5 4 4l1.2-1.2 2 1-1 1.8c-3 0-6.5-3.5-6.5-6.5L10.5 8l1 2z"/>',
    "aviao": '<path d="m22 3-20 8 7 3 3 7z"/><path d="m22 3-13 11"/>',
    "blocos": '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/>',
}


def icone(nome: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{_I[nome]}</svg>')


def selo_garantia(dias: int) -> str:
    return (f'<svg viewBox="0 0 120 120" role="img" aria-label="Garantia de {dias} dias">'
            '<circle cx="60" cy="60" r="56" fill="#f5b301"/><circle cx="60" cy="60" r="47" fill="#fff" stroke="#f5b301" stroke-width="3" stroke-dasharray="4 4"/>'
            f'<text x="60" y="58" text-anchor="middle" font-family="Bricolage,sans-serif" font-weight="800" font-size="34" fill="#111827">{dias}</text>'
            '<text x="60" y="76" text-anchor="middle" font-family="Plex,sans-serif" font-weight="700" font-size="11" fill="#111827" letter-spacing="1">DIAS</text>'
            '<text x="60" y="92" text-anchor="middle" font-family="Plex,sans-serif" font-weight="700" font-size="9" fill="#92400e" letter-spacing="1">GARANTIA</text></svg>')


def brl(v: float | None) -> str:
    """R$ 1.234,56: o comprador brasileiro lê vírgula como decimal (R$ 97.00 parece outro número)."""
    s = f"{float(v or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def pct(parte: float, todo: float) -> str:
    return f"{(parte / todo * 100):.1f}%".replace(".", ",") if todo else "–"  # noqa: RUF001 (travessão de propósito)


@functools.cache
def estatico(rel: str) -> str:
    """URL de static/ com a impressão do conteúdo: arquivo novo, URL nova.

    Sem isso o celular (e a borda da Cloudflare) guardava o estilo.css velho por 24 h depois de uma publicação,
    e a página nova saía com o estilo antigo: no Pix, o ícone sem tamanho ocupava a tela inteira (14/11)."""
    dados = (Path(__file__).resolve().parent / "static" / rel).read_bytes()
    return f"/static/{rel}?v={hashlib.sha256(dados).hexdigest()[:10]}"


def documento(titulo: str, corpo: str, *, tema: str, produto: str = "", tracker: bool = True, extra_head: str = "") -> str:
    return (
        "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<title>{e(titulo)}</title><link rel=stylesheet href={estatico('estilo.css')}>"
        "<link rel=preload href=/static/fontes/bricolage.woff2 as=font type=font/woff2 crossorigin>"
        f"{extra_head}</head><body class='t-{tema}' data-produto='{e(produto)}'>{corpo}"
        + ("<script src=/t.js></script>" if tracker else "")
        + f"<script src={estatico('funil.js')} defer></script></body></html>"
    )


def _cor_avatar(nome: str) -> str:
    return ("#12a150", "#1f6feb", "#c026d3", "#ea580c", "#0891b2")[sum(map(ord, nome)) % 5]


def _depoimentos(dep: dict | None) -> str:
    if not dep or not dep.get("itens"):
        return ""
    cards = "".join(
        f"<article class='cartao depo'><div class=depo-topo><span class=avatar style='background:{_cor_avatar(d['nome'])}'>"
        f"{e(d['nome'][:1].upper())}</span><div><strong>{e(d['nome'])}</strong><div class=estrelas aria-label='{int(d.get('estrelas', 5))} estrelas'>"
        f"{'★' * int(d.get('estrelas', 5))}</div></div></div><p>{e(d['texto'])}</p></article>" for d in dep["itens"])
    tag = "<span class=tag-exemplo>Depoimentos de exemplo</span>" if dep.get("exemplo") else ""
    return tag + cards


def _img(src: str | None) -> str:
    return f"<img src='{e(src)}' alt='' loading=lazy>" if src else ""


def _rodape(marca: str) -> str:
    return (f"<footer class=rodape><span>{e(marca)} · pagamento por Pix</span>"
            "<span>Seus dados servem só para entregar o seu acesso. Direito de arrependimento: art. 49 do CDC.</span></footer>")


# ---------------- comprador ----------------

def inicio(marca: str, produtos: list[dict]) -> str:
    cards = "".join(
        f"<a class=card-mod href='/v/{e(p['slug'])}'><img src='{e(p.get('capa') or p.get('banner') or '')}' alt='' loading=lazy>"
        f"<div><strong>{e(p['nome'])}</strong><span>{brl(p['preco'])}</span></div></a>" for p in produtos)
    corpo = (f"<div class=faixa-topo>{e(marca)}</div><main class=miolo><div class=vsl><h1>Nossos produtos</h1>"
             f"<div class=secao style='margin-top:0'><div class=cards-modulos>{cards}</div></div></div></main>{_rodape(marca)}")
    return documento(marca, corpo, tema="vsl")


def vsl(marca: str, p: dict) -> str:
    v = p.get("vsl", {})
    dias = int(p.get("garantia_dias", 7))
    mods = "".join(f"<div class=card-mod>{_img(m.get('capa'))}<div><strong>{e(m['titulo'])}</strong>"
                   f"<span>{len(m.get('aulas', []))} aula(s)</span></div></div>" for m in p.get("modulos", []))
    faq = "".join(f"<details><summary>{e(f['p'])}</summary><p>{e(f['r'])}</p></details>" for f in p.get("faq", []))
    depo = _depoimentos(p.get("depoimentos"))
    corpo = f"""<div class=faixa-topo>Assista ao vídeo até o final: a oferta aparece durante a aula</div>
<main class=miolo><div class=vsl>
<h1>{e(p['nome'])}</h1>
<p class=sub>{e(p.get('promessa', ''))}</p>
<div class=tela><video id=vsl data-cta="{int(v.get('cta_segundos', 0))}" src="{e(v.get('video', ''))}" controls playsinline preload=metadata></video></div>
<p class=credito>{e(v.get('credito_video', ''))}</p>
<p class=espera id=espera-cta>O botão de inscrição aparece durante o vídeo</p>
<div id=cta class=cta hidden><a class="bt gigante" href="/c/{e(p['slug'])}">{e(v.get('cta_texto', 'Quero comprar agora'))}</a>
<p class=sob>{brl(p['preco'])} no Pix · acesso imediato · garantia de {dias} dias</p></div>
<section class=secao><h2>O que você vai receber</h2><div class=cards-modulos>{mods}</div></section>
<section class=secao><div class=garantia-vsl>{selo_garantia(dias)}<div class=pilha style="gap:8px">
<h2 style="font:800 1.4rem var(--f-titulo)">Garantia incondicional de {dias} dias</h2>
<p class=suave>Entre, assista e aplique. Se não for para você, peça o reembolso em até {dias} dias e o valor volta inteiro, sem perguntas.</p></div></div></section>
{f"<section class=secao><h2>Quem já fez</h2><div class=depos-vsl>{depo}</div></section>" if depo else ""}
{f"<section class=secao><h2>Perguntas frequentes</h2><div class=faq>{faq}</div></section>" if faq else ""}
</div></main>{_rodape(marca)}"""
    return documento(p["nome"], corpo, tema="vsl", produto=p["slug"])


def checkout(marca: str, p: dict, bump: dict | None = None, erro: str = "") -> str:
    dias = int(p.get("garantia_dias", 7))
    banner = f"<div class=banner><img src='{e(p['banner'])}' alt='{e(p['nome'])}'></div>" if p.get("banner") else ""
    prazo = (f"<div class=prazo id=prazo data-ate='{e(p['oferta_ate'])}' hidden><span>Este preço vale até o fim da oferta</span>"
             "<span class=relogio id=relogio>--:--:--</span></div>") if p.get("oferta_ate") else ""
    capa = f"<img src='{e(p['capa'])}' alt=''>" if p.get("capa") else ""
    aulas = sum(len(m.get("aulas", [])) for m in p.get("modulos", []))
    cartao = (f"<a class=metodo href='{e(p['link_pagamento'])}'><strong>{icone('cartao')} Cartão</strong><span>em até 12x</span></a>"
              if p.get("link_pagamento") else "")
    caixa_bump = ""
    if bump:
        preco_bump = float(bump.get("preco_bump", bump["preco"]))
        caixa_bump = f"""<div class=bump><div class=chamada>Oferta única: adicione ao seu pedido</div>
<label><input type=checkbox name=bump value=1 id=bump data-valor="{preco_bump:.2f}">
{f"<img src='{e(bump['capa'])}' alt=''>" if bump.get('capa') else "<span></span>"}
<span><strong>{e(bump.get('chamada') or ('Adicionar ' + bump['nome']))}</strong>
<p>{e(bump.get('promessa', ''))} De {brl(bump['preco'])} por <b>{brl(preco_bump)}</b>.</p></span></label></div>"""
    depo = _depoimentos(p.get("depoimentos"))
    corpo = f"""<main class=miolo>{banner}{prazo}
<div class=grade-checkout>
<section class=cartao><form method=post action="/c/{e(p['slug'])}" class=pilha id=form-compra>
<div class=produto-linha>{capa}<div><h1>{e(p['nome'])}</h1><span class="suave pequeno">{aulas} aulas · acesso imediato no e-mail</span>
<div class=preco data-base="{float(p['preco']):.2f}">{brl(p['preco'])}</div></div></div>
{f"<p class=aviso role=alert>{e(erro)}</p>" if erro else ""}
<input type=hidden name=vid id=vid>
<div class=etapa-titulo><b>1</b> Seus dados</div>
<label class=campo><span>Nome completo</span><input name=nome required maxlength=120 autocomplete=name placeholder="Digite seu nome completo"></label>
<div class=duas-colunas>
<label class=campo><span>E-mail</span><input name=email type=email required maxlength=200 autocomplete=email placeholder="seu@email.com"></label>
<label class=campo><span>Confirme o e-mail</span><input name=email2 type=email required maxlength=200 autocomplete=email placeholder="Repita o e-mail"></label>
</div>
<label class=campo><span>Celular com WhatsApp</span><input name=telefone inputmode=tel maxlength=20 autocomplete=tel placeholder="(00) 00000-0000"><small>O acesso também chega por aqui.</small></label>
<div class=etapa-titulo><b>2</b> Pagamento</div>
<div class=metodos><div class="metodo ativo"><strong>{icone('pix')} Pix</strong><span>aprovação na hora</span></div>{cartao}</div>
{caixa_bump}
<div class=total><span class=suave>Total</span><strong class=num id=total>{brl(p['preco'])}</strong></div>
<button class="bt gigante cheio">{icone('cadeado')} Comprar agora</button>
<div class=confianca><span>{icone('escudo')} Compra segura</span><span>{icone('raio')} Acesso imediato</span><span>{icone('cadeado')} Dados protegidos</span></div>
<p class=legal>Ao comprar você concorda em receber o acesso e os avisos deste pedido. Garantia de {dias} dias: peça o reembolso pelo e-mail do acesso.</p>
</form></section>
<aside class=pilha>
<section class="cartao selo">{selo_garantia(dias)}<div><strong>Garantia de {dias} dias</strong><p class="suave pequeno">Não gostou? Devolvemos 100% do valor, sem perguntas.</p></div></section>
{depo}
</aside></div></main>{_rodape(marca)}"""
    return documento(f"Checkout · {p['nome']}", corpo, tema="checkout", produto=p["slug"])


def pix_pagina(marca: str, p: dict, ped: dict, codigo: str, link_telegram: str, nomes_itens: list[str]) -> str:
    pago = ped["status"] == "pago"
    situacao = ("<span id=situacao class='pilula ok'>Pagamento confirmado</span>" if pago else
                "<span id=situacao class='pilula espera vivo'>Aguardando pagamento</span>")
    tg = (f"<a class='bt sec cheio' href='{e(link_telegram)}'>{icone('aviao')} Receber o acesso também pelo Telegram</a>"
          if link_telegram else "")
    itens = "".join(f"<li>{e(nm)}</li>" for nm in nomes_itens)
    corpo = f"""<main class=miolo style="max-width:760px"><div class=pilha style="margin-top:20px" data-pedido="{e(ped['id'])}" data-status="{e(ped['status'])}">
<section class=cartao><div class=pilha>
<div class=pix-cabeca><span class=icone>{icone('pix')}</span><div><h1 style="font:800 1.4rem var(--f-titulo)">Pix gerado! Falta só pagar</h1>
<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:6px">{situacao}<strong class=num>{brl(ped['valor'])}</strong></div></div></div>
<p id=msg-pago class="aviso info" {"" if pago else "hidden"}>Pronto! O link da área de membros foi para {e(ped['email'])}.</p>
<div class=qr-area><div class=qr data-qr="{e(codigo)}" aria-label="QR Code do Pix"></div>
<ol class=passos><li><span>Abra o app do seu banco e entre em <strong>Pix</strong>.</span></li>
<li><span>Escolha <strong>pagar com QR Code</strong> e aponte a câmera, ou use o <strong>Pix copia e cola</strong> abaixo.</span></li>
<li><span>Confirme <strong class=num>{brl(ped['valor'])}</strong>. Esta página muda sozinha quando o pagamento cair.</span></li></ol></div>
<div class=copia><code id=codigo-pix>{e(codigo)}</code><button type=button class="bt gigante cheio" data-copiar=codigo-pix>Copiar código Pix</button></div>
{tg}
</div></section>
<section class=cartao><div class=pilha style="gap:8px"><strong>Seu pedido</strong><ul class=suave style="margin:0;padding-left:18px">{itens}</ul>
<p class="suave pequeno">Pedido <span class=mono>{e(ped['id'])}</span> · acesso enviado para {e(ped['email'])}</p></div></section>
</div></main>{_rodape(marca)}"""
    return documento("Pague com Pix", corpo, tema="checkout", produto=p["slug"], extra_head=f"<script src={estatico('qrcode.js')} defer></script>")


def _aulas(produtos: list[dict]) -> list[tuple[dict, dict, dict]]:
    return [(p, mod, a) for p in produtos for mod in p.get("modulos", []) for a in mod["aulas"]]


def membros(marca: str, m: dict, produtos: list[dict], feitas: set[str], token: str) -> str:
    todas = _aulas(produtos)
    vistas = sum(1 for *_, a in todas if a["id"] in feitas)
    proxima = next((a for *_, a in todas if a["id"] not in feitas), todas[0][2] if todas else None)
    pct_total = int(vistas / len(todas) * 100) if todas else 0
    p0 = produtos[0] if produtos else {}
    fundo = p0.get("banner") or p0.get("capa") or ""
    prateleiras = []
    for p in produtos:
        cards = []
        for mod in p.get("modulos", []):
            n_vistas = sum(1 for a in mod["aulas"] if a["id"] in feitas)
            largura = int(n_vistas / len(mod["aulas"]) * 100) if mod["aulas"] else 0
            alvo = next((a for a in mod["aulas"] if a["id"] not in feitas), mod["aulas"][0]) if mod["aulas"] else None
            img = f"<img src='{e(mod['capa'])}' alt='' loading=lazy>" if mod.get("capa") else ""
            if alvo:
                cards.append(f"<a class=capa-mod href='/m/{e(token)}/aula/{e(alvo['id'])}'>{img}<span class=rotulo-mod>"
                             f"<strong>{e(mod['titulo'])}</strong><small>{n_vistas}/{len(mod['aulas'])} aulas</small>"
                             f"<span class=progresso><i style='width:{largura}%'></i></span></span></a>")
        prateleiras.append(f"<section class=prateleira><h2>{e(p['nome'])}</h2><div class=fileira>{''.join(cards)}</div></section>")
    continuar = (f"<a class='bt branco' href='/m/{e(token)}/aula/{e(proxima['id'])}'>{icone('play')} "
                 f"{'Continuar assistindo' if vistas else 'Começar agora'}</a>") if proxima else ""
    corpo = f"""<header class=barra-membros><span class=marca>{e(marca)}</span><span class=ola>Olá, {e((m['nome'] or m['email']).split(' ')[0])}</span></header>
<section class=heroi>{f"<img src='{e(fundo)}' alt=''>" if fundo else ""}<div class=conteudo>
<span class="suave pequeno" style="text-transform:uppercase;letter-spacing:.08em;font-weight:700">Sua área de membros</span>
<h1>{e(p0.get('nome', 'Seus cursos'))}</h1>
<div class=progresso><i style="width:{pct_total}%"></i></div><span class="suave pequeno">{vistas} de {len(todas)} aulas concluídas</span>
<div>{continuar}</div></div></section>
{''.join(prateleiras) or "<p class=vazio style='margin:20px'>Nenhum produto liberado ainda.</p>"}"""
    return documento("Área de membros", corpo, tema="membros", tracker=False)


def aula(marca: str, m: dict, produtos: list[dict], aula_id: str, feitas: set[str], token: str) -> str | None:
    todas = _aulas(produtos)
    pos = next((i for i, (_, _, a) in enumerate(todas) if a["id"] == aula_id), None)
    if pos is None:
        return None
    p, mod, a = todas[pos]
    prox = todas[pos + 1][2] if pos + 1 < len(todas) else None
    vista = a["id"] in feitas
    player = (f"<video src='{e(a['video'])}' controls playsinline preload=metadata></video>" if a.get("video") else
              f"<div class=sem-video>{icone('play')}<strong>{e(a['titulo'])}</strong><span>Esta aula é de leitura.</span></div>")
    lista = "".join(f"<a href='/m/{e(token)}/aula/{e(x['id'])}'{' aria-current=page' if x['id'] == a['id'] else ''}>"
                    f"<span class='check{' ok' if x['id'] in feitas else ''}'></span><span>{e(x['titulo'])}</span></a>" for x in mod["aulas"])
    acao = ("<span class='pilula ok'>Aula concluída</span>" if vista else
            f"<form method=post action='/m/{e(token)}/feito'><input type=hidden name=aula value='{e(a['id'])}'>"
            "<button class=bt>Marcar como concluída</button></form>")
    seguinte = f"<a class='bt sec' href='/m/{e(token)}/aula/{e(prox['id'])}'>Próxima aula →</a>" if prox else ""
    corpo = f"""<header class=barra-membros><a class=marca href='/m/{e(token)}'>{e(marca)}</a><a class="bt sec mini" href='/m/{e(token)}'>← Todos os módulos</a></header>
<div class=aula-grade><div class=pilha><div class=player>{player}</div>
<div><span class="suave pequeno">{e(p['nome'])} · {e(mod['titulo'])}</span><h1 style="font:800 1.7rem var(--f-titulo);margin-top:6px">{e(a['titulo'])}</h1></div>
<p class=suave>{e(a.get('texto', ''))}</p>
<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">{acao}{seguinte}</div></div>
<aside class=lista-aulas><h3>{e(mod['titulo'])}</h3>{lista}</aside></div>"""
    return documento(a["titulo"], corpo, tema="membros", tracker=False)


# ---------------- dono ----------------

def _admin(titulo: str, ativo: str, corpo: str, extra_head: str = "") -> str:
    itens = (("painel", "/painel", "grafico", "Painel"), ("conexoes", "/painel/conexoes", "tomada", "Conexões"),
             ("sair", "/sair", "sair", "Sair"))
    nav = "".join(f"<a href='{h}'{' aria-current=page' if k == ativo else ''}>{icone(i)}<span>{n}</span></a>" for k, h, i, n in itens)
    casca = f"<div class=casca><aside class=lateral><span class=marca>Funil Aberto</span><nav>{nav}</nav></aside><main class=conteudo-admin>{corpo}</main></div>"
    return documento(titulo, casca, tema="admin", tracker=False, extra_head=extra_head)


def entrar(erro: str = "") -> str:
    corpo = f"""<main class=entrar><section class=cartao><form method=post action="/entrar" class=pilha>
<span class=marca>Funil Aberto</span><div class=pilha style="gap:4px"><h1 style="font:800 1.6rem var(--f-titulo)">Entrar no painel</h1>
<p class=suave>Use o token de administrador deste funil.</p></div>
{f"<p class=aviso role=alert>{e(erro)}</p>" if erro else ""}
<label class=campo><span>Token de administrador</span><input name=token type=password required autocomplete=current-password autofocus></label>
<button class="bt cheio">Entrar</button></form></section></main>"""
    return documento("Entrar · Funil Aberto", corpo, tema="admin", tracker=False)


def _pilula_pedido(status: str) -> str:
    return {"pago": "<span class='pilula ok'>pago</span>", "pendente": "<span class='pilula espera'>aguardando Pix</span>"}.get(
        status, f"<span class=pilula>{e(status)}</span>")


def _pilula_msg(status: str) -> str:
    return {"enviado": "<span class='pilula ok'>enviado</span>", "erro": "<span class='pilula erro'>erro</span>"}.get(
        status, f"<span class=pilula>{e(status)}</span>")


def grafico_vendas(dias: list[tuple[str, float]]) -> str:
    """Barras de receita por dia, desenhadas com uma escala só; o rótulo do topo é o maior valor do período."""
    if not dias:
        return ""
    lw, lh, base, topo, esq = 520, 210, 182, 24, 4
    maior = max(v for _, v in dias) or 1
    passo = (lw - esq) / len(dias)
    barras, rotulos = [], []
    for i, (d, v) in enumerate(dias):
        h = (base - topo) * v / maior
        x = esq + i * passo + passo * .18
        barras.append(f"<rect class=barra x='{x:.1f}' y='{base - h:.1f}' width='{passo * .64:.1f}' height='{max(h, 0):.1f}' rx='3'>"
                      f"<title>{d[8:]}/{d[5:7]}: {brl(v)}</title></rect>")
        if (len(dias) - 1 - i) % 2 == 0:  # um rótulo sim, outro não, contando de hoje: nenhum encavala
            rotulos.append(f"<text x='{x + passo * .32:.1f}' y='{base + 16}' text-anchor='middle'>{d[8:]}/{d[5:7]}</text>")
    return (f"<svg viewBox='0 0 {lw} {lh}' role=img aria-label='Receita por dia'><line class=eixo x1='{esq}' x2='{lw}' y1='{base}' y2='{base}'/>"
            f"<text x='{esq}' y='14'>máx. {brl(maior)}</text>{''.join(barras)}{''.join(rotulos)}</svg>")


def painel(resumo: dict, funil: list[dict], pedidos: list[dict], mensagens: list[dict], vendas_dia: list[tuple[str, float]]) -> str:
    kpis = (f"<div class='cartao kpi destaque'><span class=rotulo-kpi>Receita</span><span class=valor>{brl(resumo['receita'])}</span></div>"
            + "".join(f"<div class='cartao kpi'><span class=rotulo-kpi>{r}</span><span class=valor>{v}</span></div>" for r, v in (
                ("Vendas", resumo["vendas"]), ("Checkouts", resumo["checkouts"]), ("Visitantes", resumo["visitantes"]),
                ("Conversão", pct(resumo["vendas"], resumo["visitantes"])))))
    etapas_def = (("visita", "Visitaram"), ("vsl_play", "Deram play"), ("cta_visto", "Viram a oferta"),
                  ("checkout", "Checkout"), ("compra", "Compraram"))
    soma = {k: sum(r[k] for r in funil) for k, _ in etapas_def}
    topo = max(soma["visita"], 1)
    etapas = "".join(f"<div class=etapa><span>{n}</span><span class=trilho><i style='width:{soma[k] / topo * 100:.1f}%'></i></span>"
                     f"<span class=n>{soma[k]}</span></div>" for k, n in etapas_def)
    origens = "".join(
        f"<tr><td><strong>{e(r['src'])}</strong></td><td class=suave>{e(r['camp'])}</td><td class=n>{r['visita']}</td>"
        f"<td class=n>{r['compra']}</td><td class=n>{pct(r['compra'], r['visita'])}</td><td class=n>{brl(r['receita'])}</td></tr>" for r in funil)
    peds = "".join(
        f"<tr><td>{e(r['nome'] or r['email'])}<br><span class='mono suave'>{e(r['id'])}</span></td><td>{_pilula_pedido(r['status'])}</td>"
        f"<td class=n>{brl(r['valor'])}</td><td>"
        + (f"<form method=post action='/painel/pedido/{e(r['id'])}/pago'><button class='bt sec mini'>Pix recebido</button></form>"
           if r["status"] == "pendente" else "")
        + "</td></tr>" for r in pedidos)
    msgs = "".join(f"<tr><td>{e(m['canal'])}</td><td>{e(m['motivo'])}</td><td>{_pilula_msg(m['status'])}</td>"
                   f"<td class='mono suave'>{e(m['pedido'] or '')}</td></tr>" for m in mensagens)
    vazio = "<p class=vazio>{}</p>"
    corpo = f"""<div class=cabeca-admin><h1>Painel</h1><a class="bt sec mini" href="/painel/conexoes">{icone('tomada')} Conectar canais</a></div>
<div class=kpis>{kpis}</div>
<section class="cartao grafico"><div class=pilha style="gap:10px"><strong>Receita nos últimos 14 dias</strong>{grafico_vendas(vendas_dia)}</div></section>
<div class=dois-paineis>
<section class=cartao><div class=pilha><strong>Vendas por origem</strong>{f"<div class=tabela><table><tr><th>origem</th><th>campanha</th><th class=n>visitas</th><th class=n>vendas</th><th class=n>conv.</th><th class=n>receita</th></tr>{origens}</table></div>" if origens else vazio.format("Aparece quando o link do anúncio levar utm_source e utm_campaign.")}</div></section>
<section class=cartao><div class=pilha><strong>Funil</strong><div class=etapas>{etapas}</div></div></section>
</div>
<section class=cartao><div class=pilha><strong>Pedidos recentes</strong>{f"<div class=tabela><table><tr><th>comprador</th><th>situação</th><th class=n>valor</th><th></th></tr>{peds}</table></div>" if peds else vazio.format("Nenhum pedido ainda.")}</div></section>
<section class=cartao><div class=pilha><strong>Mensagens enviadas</strong>{f"<div class=tabela><table><tr><th>canal</th><th>motivo</th><th>situação</th><th>pedido</th></tr>{msgs}</table></div>" if msgs else vazio.format("Recuperação de carrinho, acessos e robô aparecem aqui.")}</div></section>"""
    return _admin("Painel · Funil Aberto", "painel", corpo)


def conexoes(wa: dict, tg: dict, composio_ligado: bool, toolkits: tuple[str, ...], ligados: set[str], teto: int, aviso: str = "") -> str:
    def pil(estado: str) -> str:
        nome, cls = NOMES_ESTADO.get(estado, (estado, ""))
        return f"<span class='pilula {cls}'>{e(nome)}</span>"

    if wa.get("via") == "maus":
        # O número é o que o dono já conectou no maus: trocar ou desconectar é lá, não aqui (um número, um lugar).
        wa_acao = ("<p class='aviso info'>Usando o WhatsApp que você já conectou no maus. Para trocar o número, abra "
                   "maus.genesisinnovation.io/_conexoes/.</p>")
    elif wa["estado"] == "open":
        wa_acao = "<form method=post action='/painel/conexoes/whatsapp/desconectar'><button class='bt sec'>Desconectar</button></form>"
    elif wa.get("configurado"):
        wa_acao = "<form method=post action='/painel/conexoes/whatsapp/qr'><button class='bt cheio'>Conectar pelo QR Code</button></form>"
    else:
        wa_acao = "<p class='aviso info'>Falta configurar a Evolution no servidor (EVOLUTION_URL e EVOLUTION_KEY).</p>"
    tg_acao = (f"<p>Bot <strong>@{e(tg.get('bot', ''))}</strong></p><form method=post action='/painel/conexoes/telegram/webhook'>"
               "<button class='bt sec cheio'>Ligar o robô no bot</button></form>" if tg["estado"] == "open" else
               "<p class='aviso info'>Crie um bot no @BotFather e entregue o token ao servidor (TELEGRAM_BOT_TOKEN).</p>")
    if composio_ligado:
        ok = "<span class='pilula ok'>conectado</span>"
        apps = "".join(f"<li><strong style='text-transform:capitalize'>{e(t)}</strong>{ok if t in ligados else ''}"
                       f"<form method=post action='/painel/conexoes/composio'><input type=hidden name=toolkit value='{e(t)}'>"
                       f"<button class='bt {'sec ' if t in ligados else ''}mini cheio'>{'Reconectar' if t in ligados else 'Conectar'}</button></form></li>"
                       for t in toolkits)
        cp = f"<ul class=apps>{apps}</ul>"
    else:
        cp = "<p class='aviso info'>Falta a chave da Composio no servidor (COMPOSIO_API_KEY).</p>"
    corpo = f"""<div class=cabeca-admin><h1>Conexões</h1></div>
{f"<p class=aviso role=alert>{e(aviso)}</p>" if aviso else ""}
<div class=conexoes>
<section class=cartao><div class=conexao-topo><span class=logo style="background:#22c55e">{icone('zap')}</span><h2>WhatsApp</h2>{pil(wa['estado'])}</div><div class=pilha>
<p class=suave>Recuperação de carrinho, acesso e robô saem deste número. Até {teto} mensagens por dia, para o número não ser bloqueado.</p>
{f"<p class='suave pequeno'>{e(wa.get('erro', ''))}</p>" if wa.get('erro') else ""}{wa_acao}</div></section>
<section class=cartao><div class=conexao-topo><span class=logo style="background:#229ed9">{icone('aviao')}</span><h2>Telegram</h2>{pil(tg['estado'])}</div><div class=pilha>
<p class=suave>O comprador abre o bot pelo botão da página do Pix e recebe o acesso e os avisos por lá.</p>{tg_acao}</div></section>
<section class=cartao style="grid-column:1/-1"><div class=conexao-topo><span class=logo style="background:#111827">{icone('blocos')}</span><h2>Apps</h2></div><div class=pilha>
<p class=suave>Conecte e diga no config.json o que fazer em cada evento. Exemplo: venda nova vira linha na planilha.</p>{cp}</div></section>
</div>"""
    return _admin("Conexões · Funil Aberto", "conexoes", corpo)


def qr_whatsapp(qr: dict) -> str:
    img = f"<div class=qr><img src='{e(qr['qr'])}' alt='QR do WhatsApp' width=220 height=220></div>" if qr.get("qr") else ""
    cod = (f"<p>Ou toque em <strong>Conectar com número de telefone</strong> e digite <strong class=mono>{e(qr['codigo'])}</strong>.</p>"
           if qr.get("codigo") else "")
    corpo = f"""<div class=cabeca-admin><h1>Conectar WhatsApp</h1></div>
<section class=cartao><div class=qr-area>{img}<div class=pilha>
<ol class=passos><li><span>No WhatsApp do número de vendas, abra <strong>Configurações</strong>.</span></li>
<li><span>Toque em <strong>Aparelhos conectados</strong> e depois em <strong>Conectar um aparelho</strong>.</span></li>
<li><span>Aponte a câmera para este QR. Ele vale por alguns segundos e a página se renova.</span></li></ol>
{cod}<a class="bt sec" href="/painel/conexoes">Já li o QR</a></div></div></section>"""
    return _admin("Conectar WhatsApp · Funil Aberto", "conexoes", corpo,
                  extra_head="<meta http-equiv=refresh content='25;url=/painel/conexoes'>")


def nao_encontrado() -> str:
    corpo = ("<main class=miolo><div class=vsl><h1>Página não encontrada</h1>"
             "<p class=sub>O endereço pode ter mudado. Confira o link que você recebeu.</p></div></main>")
    return documento("Página não encontrada", corpo, tema="vsl", tracker=False)
