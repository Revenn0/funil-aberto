"""As telas do funil: as do comprador (VSL, checkout, Pix, área de membros) e as do dono (entrar, painel, conexões).

Só monta HTML: não toca banco nem rede (quem chama passa os dados). Todo texto que vem de fora passa por `e()`.
Estilo em static/estilo.css e comportamento em static/funil.js: nenhum script inline (CSP `script-src 'self'`).
"""
from __future__ import annotations

import html

e = html.escape

NOMES_ESTADO = {"open": ("conectado", "ok"), "connecting": ("aguardando leitura do QR", "espera vivo"),
                "close": ("desconectado", "erro"), "ausente": ("ainda não conectado", ""),
                "simulado": ("não configurado no servidor", ""), "erro": ("com erro", "erro")}


def brl(v: float | None) -> str:
    """R$ 1.234,56: o comprador brasileiro lê vírgula como decimal (R$ 97.00 parece outro número)."""
    s = f"{float(v or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def pct(parte: float, todo: float) -> str:
    return f"{(parte / todo * 100):.1f}%".replace(".", ",") if todo else "–"


def documento(titulo: str, corpo: str, *, produto: str = "", tracker: bool = True, extra_head: str = "") -> str:
    return (
        "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<title>{e(titulo)}</title><link rel=stylesheet href=/static/estilo.css>"
        "<link rel=preload href=/static/fontes/bricolage.woff2 as=font type=font/woff2 crossorigin>"
        f"{extra_head}</head><body data-produto='{e(produto)}'>{corpo}"
        + ("<script src=/t.js></script>" if tracker else "")
        + "<script src=/static/funil.js defer></script></body></html>"
    )


def _topo_comprador(marca: str) -> str:
    return (f"<header class=topo><span class=marca>{e(marca)}</span>"
            "<span class=selo-seguro>Pagamento por Pix · dados protegidos</span></header>")


def _rodape(marca: str) -> str:
    return (f"<footer class=rodape><span>{e(marca)}</span>"
            "<span>Seus dados servem só para entregar o seu acesso. Garantia de 7 dias (CDC, art. 49).</span></footer>")


# ---------------- comprador ----------------

def inicio(marca: str, produtos: list[dict]) -> str:
    cards = "".join(
        f"<a class='cartao' style='text-decoration:none;color:inherit' href='/v/{e(p['slug'])}'><div class=pilha>"
        f"<span class=rotulo>Produto</span><h2>{e(p['nome'])}</h2><p class=suave>{e(p.get('promessa', ''))}</p>"
        f"<strong class=num>{brl(p['preco'])}</strong></div></a>" for p in produtos)
    corpo = (f"{_topo_comprador(marca)}<main class=miolo><div class=pilha>"
             f"<h1>{e(marca)}</h1><div class=oferta>{cards}</div></div></main>{_rodape(marca)}")
    return documento(marca, corpo)


def vsl(marca: str, p: dict) -> str:
    v = p.get("vsl", {})
    total_aulas = sum(len(m.get("aulas", [])) for m in p.get("modulos", []))
    itens = "".join(f"<li><span><strong>{e(m['titulo'])}</strong><br><span class='suave pequeno'>"
                    f"{len(m.get('aulas', []))} aula(s)</span></span></li>" for m in p.get("modulos", []))
    corpo = f"""{_topo_comprador(marca)}<main class=miolo><div class=vsl>
<span class=rotulo>Assista até o fim</span>
<h1>{e(p['nome'])}</h1>
<p class=lead>{e(p.get('promessa', ''))}</p>
<div class=tela-video><video id=vsl data-cta="{int(v.get('cta_segundos', 0))}" src="{e(v.get('video', ''))}" controls playsinline preload=metadata></video></div>
<p class=credito>{e(v.get('credito_video', ''))}</p>
<p class=espera-cta id=espera-cta>A oferta aparece durante o vídeo.</p>
<div id=cta class=cta-bloco hidden><a class="bt grande" href="/c/{e(p['slug'])}">{e(v.get('cta_texto', 'Quero comprar'))}</a>
<p class=sob><strong class=num>{brl(p['preco'])}</strong> no Pix · acesso na hora · garantia de 7 dias</p></div>
<div class=oferta>
<section class=cartao><div class=pilha><span class=rotulo>O que você recebe</span><h2>{total_aulas} aulas em {len(p.get('modulos', []))} módulos</h2>
<ul class=lista-check>{itens}</ul></div></section>
<section class=cartao><div class=pilha><span class=rotulo>Sem risco</span><h2>Garantia de 7 dias</h2>
<p class=suave>Se não for para você, peça o reembolso em até 7 dias e o valor volta inteiro. É lei para compra online, e aqui é regra.</p></div></section>
</div></div></main>{_rodape(marca)}"""
    return documento(p["nome"], corpo, produto=p["slug"])


def checkout(marca: str, p: dict, erro: str = "") -> str:
    aulas = sum(len(m.get("aulas", [])) for m in p.get("modulos", []))
    corpo = f"""{_topo_comprador(marca)}<main class=miolo><div class=compra>
<section class=cartao><form method=post action="/c/{e(p['slug'])}" class=pilha>
<div class=pilha style="gap:6px"><span class=rotulo>Passo 1 de 2</span><h1 style="font-size:clamp(1.6rem,4vw,2.2rem)">Seus dados</h1>
<p class=suave>O acesso chega no e-mail e no WhatsApp que você informar.</p></div>
{f"<p class=aviso role=alert>{e(erro)}</p>" if erro else ""}
<input type=hidden name=vid id=vid>
<label class=campo><span>Nome completo</span><input name=nome required maxlength=120 autocomplete=name placeholder="Como está no seu documento"></label>
<label class=campo><span>E-mail</span><input name=email type=email required maxlength=200 autocomplete=email placeholder="voce@exemplo.com"></label>
<label class=campo><span>WhatsApp</span><input name=telefone inputmode=tel maxlength=20 autocomplete=tel placeholder="(48) 99999-0000"><small>Opcional. Usado só para avisos deste pedido.</small></label>
<button class="bt grande cheio">Gerar Pix de {brl(p['preco'])}</button>
<p class="suave pequeno">Ao continuar você concorda em receber o acesso e os avisos deste pedido. Nada é compartilhado com terceiros.</p>
</form></section>
<aside class="cartao resumo"><div class=pilha>
<span class=rotulo>Resumo do pedido</span>
<div class=produto-resumo><span class=capa aria-hidden=true>{e(p['nome'][:1].upper())}</span>
<div><strong>{e(p['nome'])}</strong><br><span class="suave pequeno">{aulas} aulas · acesso imediato</span></div></div>
<ul class=lista-check><li><span>Acesso liberado assim que o Pix cair</span></li><li><span>Garantia de 7 dias</span></li>
<li><span>Pix direto, sem cadastro em site de pagamento</span></li></ul>
<div class=linha-preco><span class=suave>Total</span><span class="preco num">{brl(p['preco'])}</span></div>
</div></aside></div></main>{_rodape(marca)}"""
    return documento(f"Checkout · {p['nome']}", corpo, produto=p["slug"])


def pix_pagina(marca: str, p: dict, ped: dict, codigo: str, link_telegram: str) -> str:
    pago = ped["status"] == "pago"
    situacao = "<span id=situacao class='pilula ok'>Pagamento confirmado</span>" if pago else \
        "<span id=situacao class='pilula espera vivo'>Aguardando pagamento</span>"
    tg = (f"<a class='bt sec cheio' href='{e(link_telegram)}'>Receber o acesso também pelo Telegram</a>"
          if link_telegram else "")
    corpo = f"""{_topo_comprador(marca)}<main class="miolo estreito"><div class=pilha data-pedido="{e(ped['id'])}" data-status="{e(ped['status'])}">
<div class=pilha style="gap:8px"><span class=rotulo>Passo 2 de 2</span><h1 style="font-size:clamp(1.6rem,4vw,2.2rem)">Pague com Pix</h1>
<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">{situacao}<strong class=num style="font-size:1.2rem">{brl(ped['valor'])}</strong></div></div>
<p id=msg-pago class="aviso info" {"" if pago else "hidden"}>Pronto! O link da área de membros foi para {e(ped['email'])}.</p>
<section class=cartao><div class=pix-grade>
<div class=qr data-qr="{e(codigo)}" aria-label="QR Code do Pix"></div>
<ol class=passos><li><span>Abra o app do seu banco e escolha <strong>Pix</strong>.</span></li>
<li><span>Aponte a câmera para o QR Code ou use <strong>Pix copia e cola</strong>.</span></li>
<li><span>Confira o valor de <strong class=num>{brl(ped['valor'])}</strong> e confirme. Esta página atualiza sozinha.</span></li></ol>
</div></section>
<section class="cartao liso"><div class=pilha style="gap:10px"><strong>Pix copia e cola</strong>
<div class=copia><code id=codigo-pix>{e(codigo)}</code><button type=button class=bt data-copiar=codigo-pix>Copiar código</button></div></div></section>
{tg}
<p class="suave pequeno">Pedido <span class=mono>{e(ped['id'])}</span> · {e(p['nome'])}</p>
</div></main>{_rodape(marca)}"""
    return documento("Pague com Pix", corpo, produto=p["slug"], extra_head="<script src=/static/qrcode.js defer></script>")


def membros(marca: str, m: dict, produtos: list[dict], feitas: set[str], token: str) -> str:
    total = sum(len(mod["aulas"]) for p in produtos for mod in p.get("modulos", []))
    vistas = sum(1 for p in produtos for mod in p.get("modulos", []) for a in mod["aulas"] if a["id"] in feitas)
    blocos = []
    for p in produtos:
        mods = []
        for mod in p.get("modulos", []):
            aulas = []
            for a in mod["aulas"]:
                vista = a["id"] in feitas
                botao = "" if vista else (f"<form method=post action='/m/{e(token)}/feito'><input type=hidden name=aula value='{e(a['id'])}'>"
                                          "<button class='bt sec mini'>Marcar como vista</button></form>")
                video = f"<video src='{e(a['video'])}' controls preload=none></video>" if a.get("video") else ""
                aulas.append(f"<div class='aula{' vista' if vista else ''}'><span class=marca-aula aria-label="
                             f"'{'vista' if vista else 'não vista'}'></span><div><strong>{e(a['titulo'])}</strong>"
                             f"<p class='suave pequeno'>{e(a.get('texto', ''))}</p>{video}</div>{botao}</div>")
            feitas_mod = sum(1 for a in mod["aulas"] if a["id"] in feitas)
            mods.append(f"<details class=modulo open><summary><span>{e(mod['titulo'])}</span>"
                        f"<span class='suave pequeno num'>{feitas_mod}/{len(mod['aulas'])}</span></summary>{''.join(aulas)}</details>")
        blocos.append(f"<section class=pilha><h2>{e(p['nome'])}</h2>{''.join(mods)}</section>")
    largura = int(vistas / total * 100) if total else 0
    corpo = f"""<header class=topo><span class=marca>{e(marca)}</span><span class="suave pequeno">Área de membros</span></header>
<main class="miolo estreito"><div class=pilha>
<h1>Olá, {e((m['nome'] or m['email']).split(' ')[0])}</h1>
<div class=cartao><div class=pilha style="gap:10px"><div style="display:flex;justify-content:space-between;gap:12px">
<strong>Seu progresso</strong><span class="suave num">{vistas} de {total} aulas</span></div>
<div class=progresso role=progressbar aria-valuenow="{largura}" aria-valuemin=0 aria-valuemax=100><i style="width:{largura}%"></i></div></div></div>
{''.join(blocos) or "<p class=vazio>Nenhum produto liberado ainda.</p>"}
</div></main>"""
    return documento("Área de membros", corpo, tracker=False)


# ---------------- dono ----------------

def _admin(titulo: str, ativo: str, corpo: str, extra_head: str = "") -> str:
    abas = "".join(f"<a href='{h}'{' aria-current=page' if k == ativo else ''}>{n}</a>"
                   for k, h, n in (("painel", "/painel", "Painel"), ("conexoes", "/painel/conexoes", "Conexões"),
                                   ("sair", "/sair", "Sair")))
    topo = f"<div class=admin-topo><div class=topo><span class=marca>Funil Aberto</span><nav class=abas>{abas}</nav></div></div>"
    return documento(titulo, f"{topo}<main class=miolo>{corpo}</main>", tracker=False, extra_head=extra_head)


def entrar(erro: str = "") -> str:
    corpo = f"""<header class=topo><span class=marca>Funil Aberto</span></header><main class="miolo entrar"><section class=cartao>
<form method=post action="/entrar" class=pilha><div class=pilha style="gap:6px"><h1 style="font-size:1.8rem">Entrar no painel</h1>
<p class=suave>Use o token de administrador deste funil.</p></div>
{f"<p class=aviso role=alert>{e(erro)}</p>" if erro else ""}
<label class=campo><span>Token de administrador</span><input name=token type=password required autocomplete=current-password autofocus></label>
<button class="bt cheio">Entrar</button></form></section></main>"""
    return documento("Entrar · Funil Aberto", corpo, tracker=False)


def _pilula_pedido(status: str) -> str:
    return {"pago": "<span class='pilula ok'>pago</span>", "pendente": "<span class='pilula espera'>aguardando Pix</span>"}.get(
        status, f"<span class=pilula>{e(status)}</span>")


def _pilula_msg(status: str) -> str:
    return {"enviado": "<span class='pilula ok'>enviado</span>", "erro": "<span class='pilula erro'>erro</span>"}.get(
        status, f"<span class=pilula>{e(status)}</span>")


def painel(resumo: dict, funil: list[dict], pedidos: list[dict], mensagens: list[dict]) -> str:
    kpis = "".join(f"<div class='cartao kpi'><div class=rotulo-kpi>{r}</div><div class=valor>{v}</div></div>" for r, v in (
        ("Visitantes", resumo["visitantes"]), ("Checkouts", resumo["checkouts"]), ("Vendas", resumo["vendas"]),
        ("Receita", brl(resumo["receita"])), ("Conversão", pct(resumo["vendas"], resumo["visitantes"]))))
    etapas_def = (("visita", "Visitaram"), ("vsl_play", "Deram play"), ("cta_visto", "Viram a oferta"),
                  ("checkout", "Foram ao checkout"), ("compra", "Compraram"))
    soma = {k: sum(r[k] for r in funil) for k, _ in etapas_def}
    topo = max(soma["visita"], 1)
    etapas = "".join(f"<div class=etapa><span>{n}</span><span class=trilho><i style='width:{soma[k] / topo * 100:.1f}%'></i></span>"
                     f"<span class=n>{soma[k]}</span></div>" for k, n in etapas_def)
    origens = "".join(
        f"<tr><td>{e(r['src'])}</td><td class=suave>{e(r['camp'])}</td><td class=n>{r['visita']}</td><td class=n>{r['checkout']}</td>"
        f"<td class=n>{r['compra']}</td><td class=n>{pct(r['compra'], r['visita'])}</td><td class=n>{brl(r['receita'])}</td></tr>"
        for r in funil)
    peds = "".join(
        f"<tr><td class=mono>{e(r['id'])}</td><td>{e(r['nome'] or r['email'])}</td><td>{_pilula_pedido(r['status'])}</td>"
        f"<td class=n>{brl(r['valor'])}</td><td>"
        + (f"<form method=post action='/painel/pedido/{e(r['id'])}/pago'><button class='bt sec mini'>Pix recebido</button></form>"
           if r["status"] == "pendente" else "")
        + "</td></tr>" for r in pedidos)
    msgs = "".join(f"<tr><td>{e(m['canal'])}</td><td>{e(m['motivo'])}</td><td>{_pilula_msg(m['status'])}</td>"
                   f"<td class='mono suave'>{e(m['pedido'] or '')}</td></tr>" for m in mensagens)
    vazio = "<p class=vazio>{}</p>"
    corpo = f"""<div class=titulo-pagina><div><span class=rotulo>Visão geral</span><h1 style="font-size:2rem">Painel</h1></div>
<a class="bt sec mini" href="/painel/conexoes">Conectar WhatsApp, Telegram e apps</a></div>
<div class=pilha style="gap:16px">
<div class=kpis>{kpis}</div>
<div class=duas>
<section class=cartao><div class=pilha><h2>Funil</h2><div class=etapas>{etapas}</div>
<p class="suave pequeno">Pessoas únicas em cada etapa, de todas as origens.</p></div></section>
<section class=cartao><div class=pilha><h2>Por origem</h2>{f"<div class=tabela><table><tr><th>origem</th><th>campanha</th><th class=n>visitas</th><th class=n>checkouts</th><th class=n>vendas</th><th class=n>conversão</th><th class=n>receita</th></tr>{origens}</table></div>" if origens else vazio.format("As visitas aparecem aqui quando o link do anúncio levar utm_source e utm_campaign.")}</div></section>
</div>
<section class=cartao><div class=pilha><h2>Pedidos</h2>{f"<div class=tabela><table><tr><th>pedido</th><th>comprador</th><th>situação</th><th class=n>valor</th><th></th></tr>{peds}</table></div>" if peds else vazio.format("Nenhum pedido ainda.")}
<p class="suave pequeno">“Pix recebido” libera o acesso e conta a venda, igual ao aviso automático do banco.</p></div></section>
<section class=cartao><div class=pilha><h2>Mensagens</h2>{f"<div class=tabela><table><tr><th>canal</th><th>motivo</th><th>situação</th><th>pedido</th></tr>{msgs}</table></div>" if msgs else vazio.format("Recuperação de carrinho, acessos e robô aparecem aqui.")}</div></section>
</div>"""
    return _admin("Painel · Funil Aberto", "painel", corpo)


def conexoes(wa: dict, tg: dict, composio_ligado: bool, toolkits: tuple[str, ...], ligados: set[str], teto: int, aviso: str = "") -> str:
    def pil(estado: str) -> str:
        nome, cls = NOMES_ESTADO.get(estado, (estado, ""))
        return f"<span class='pilula {cls}'>{e(nome)}</span>"

    if wa["estado"] == "open":
        wa_acao = "<form method=post action='/painel/conexoes/whatsapp/desconectar'><button class='bt sec'>Desconectar</button></form>"
    elif wa.get("configurado"):
        wa_acao = "<form method=post action='/painel/conexoes/whatsapp/qr'><button class=bt>Conectar pelo QR</button></form>"
    else:
        wa_acao = "<p class='aviso info'>Falta configurar a Evolution no servidor (EVOLUTION_URL e EVOLUTION_KEY).</p>"
    tg_estado = "open" if tg["estado"] == "open" else tg["estado"]
    tg_acao = (f"<p>Bot <strong>@{e(tg.get('bot', ''))}</strong></p><form method=post action='/painel/conexoes/telegram/webhook'>"
               "<button class='bt sec'>Ligar o robô no bot</button></form>" if tg["estado"] == "open" else
               "<p class='aviso info'>Crie um bot no @BotFather e entregue o token ao servidor (TELEGRAM_BOT_TOKEN).</p>")
    if composio_ligado:
        ok = "<span class='pilula ok'>conectado</span>"
        apps = "".join(f"<li><strong>{e(t)}</strong>{ok if t in ligados else ''}"
                       f"<form method=post action='/painel/conexoes/composio'><input type=hidden name=toolkit value='{e(t)}'>"
                       f"<button class='bt {'sec ' if t in ligados else ''}mini cheio'>{'Reconectar' if t in ligados else 'Conectar'}</button></form></li>"
                       for t in toolkits)
        cp = f"<ul class=apps>{apps}</ul>"
    else:
        cp = "<p class='aviso info'>Falta a chave da Composio no servidor (COMPOSIO_API_KEY).</p>"
    corpo = f"""<div class=titulo-pagina><div><span class=rotulo>Canais e integrações</span><h1 style="font-size:2rem">Conexões</h1></div></div>
{f"<p class=aviso role=alert>{e(aviso)}</p>" if aviso else ""}
<div class=conexoes>
<section class=cartao><div class=conexao-topo><h2>WhatsApp</h2>{pil(wa['estado'])}</div><div class=pilha>
<p class=suave>Recuperação de carrinho, acesso e robô saem deste número. Até {teto} mensagens por dia, para o número não ser bloqueado.</p>
{f"<p class='suave pequeno'>{e(wa.get('erro', ''))}</p>" if wa.get('erro') else ""}{wa_acao}</div></section>
<section class=cartao><div class=conexao-topo><h2>Telegram</h2>{pil(tg_estado)}</div><div class=pilha>
<p class=suave>O comprador abre o bot pelo botão da página do Pix e recebe o acesso e os avisos por lá.</p>{tg_acao}</div></section>
<section class=cartao style="grid-column:1/-1"><div class=conexao-topo><h2>Apps (Composio)</h2></div><div class=pilha>
<p class=suave>Conecte o app e diga no config.json o que fazer em cada evento, por exemplo: venda nova vira linha na planilha.</p>{cp}</div></section>
</div>"""
    return _admin("Conexões · Funil Aberto", "conexoes", corpo)


def qr_whatsapp(qr: dict) -> str:
    img = f"<div class=qr><img src='{e(qr['qr'])}' alt='QR do WhatsApp' width=232 height=232></div>" if qr.get("qr") else ""
    cod = (f"<p>Ou toque em <strong>Conectar com número de telefone</strong> e digite <strong class=mono>{e(qr['codigo'])}</strong>.</p>"
           if qr.get("codigo") else "")
    corpo = f"""<div class=titulo-pagina><div><span class=rotulo>WhatsApp</span><h1 style="font-size:2rem">Leia o QR com o celular</h1></div></div>
<section class=cartao><div class=pix-grade>{img}<div class=pilha>
<ol class=passos><li><span>No WhatsApp do número de vendas, abra <strong>Configurações</strong>.</span></li>
<li><span>Toque em <strong>Aparelhos conectados</strong> e depois em <strong>Conectar um aparelho</strong>.</span></li>
<li><span>Aponte a câmera para este QR. Ele vale por alguns segundos e a página se renova.</span></li></ol>
{cod}<a class="bt sec" href="/painel/conexoes">Já li o QR</a></div></div></section>"""
    return _admin("Conectar WhatsApp · Funil Aberto", "conexoes", corpo,
                  extra_head="<meta http-equiv=refresh content='25;url=/painel/conexoes'>")


def nao_encontrado() -> str:
    corpo = ("<header class=topo><span class=marca>Funil Aberto</span></header><main class='miolo estreito'><div class=pilha>"
             "<h1>Página não encontrada</h1><p class=suave>O endereço pode ter mudado. Confira o link que você recebeu.</p></div></main>")
    return documento("Página não encontrada", corpo, tracker=False)
