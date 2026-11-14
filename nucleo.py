"""Núcleo do funil-aberto: o único arquivo que toca SQL.

Uma operação de venda online (tracker, VSL, checkout, área de membros, recuperação,
robô de mensagens, biblioteca de anúncios) é uma sequência de eventos sobre a mesma pessoa.
Por isso tudo aqui gira em volta de duas tabelas: `visitante` (quem é, de onde veio) e
`evento` (o que fez). Pedido, membro e mensagem apontam para o visitante: a atribuição
(qual anúncio vendeu) sai de uma consulta, não de uma integração entre cinco ferramentas.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_LOCAL = threading.local()

SCHEMA = """
create table if not exists visitante(
  id text primary key, criado real, utm_source text, utm_medium text, utm_campaign text,
  utm_content text, utm_term text, fbclid text, gclid text, ttclid text, referrer text, landing text,
  ip text, ua text);
create table if not exists evento(
  id integer primary key, visitante text, nome text, produto text, valor real, dados text, criado real);
create index if not exists evento_nome on evento(nome, produto);
create table if not exists pedido(
  id text primary key, produto text, visitante text, nome text, email text, telefone text,
  valor real, status text, metodo text, criado real, pago_em real, etapa_recuperacao integer default 0);
create index if not exists pedido_status on pedido(status, criado);
create table if not exists membro(
  id text primary key, email text unique, nome text, token text unique, criado real);
create table if not exists acesso(membro text, produto text, primary key(membro, produto));
create table if not exists progresso(membro text, aula text, feito real, primary key(membro, aula));
create table if not exists mensagem(
  id integer primary key, canal text, para text, texto text, motivo text, pedido text,
  status text, criado real, erro text);
create table if not exists conversa(
  canal text, contato text, fluxo text, passo integer, atualizado real, primary key(canal, contato));
create table if not exists telegram(
  pedido text primary key, chat text, criado real);
create table if not exists anuncio(
  id integer primary key, fonte text, anunciante text, texto text, url text, nota text, criado real);
"""

UTM = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
CLIQUES = ("fbclid", "gclid", "ttclid")


def data_dir() -> Path:
    d = Path(os.environ.get("DATA_DIR", "./data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db() -> sqlite3.Connection:
    caminho = str(data_dir() / "funil.db")
    con = getattr(_LOCAL, "con", None)
    if con is None or getattr(_LOCAL, "caminho", None) != caminho:
        con = sqlite3.connect(caminho, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("pragma journal_mode=wal")
        con.executescript(SCHEMA)
        _migrar(con)
        _LOCAL.con, _LOCAL.caminho = con, caminho
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Colunas novas em banco que já existe: `create table if not exists` não altera tabela antiga em produção."""
    colunas = {r[1] for r in con.execute("pragma table_info(pedido)")}
    if "itens" not in colunas:
        con.execute("alter table pedido add column itens text default ''")


def novo_id(prefixo: str) -> str:
    return f"{prefixo}_{secrets.token_urlsafe(9)}"


# ---------- configuração (produtos, fluxos do robô, recuperação): dado, não código ----------

def config() -> dict:
    arq = Path(os.environ.get("FUNIL_CONFIG", AQUI / "config.json"))
    return json.loads(arq.read_text(encoding="utf-8"))


def produto(slug: str) -> dict | None:
    for p in config()["produtos"]:
        if p["slug"] == slug:
            return p
    return None


# ---------- tracker ----------

def visitante(vid: str | None, dados: dict, ip: str = "", ua: str = "") -> str:
    """Primeiro toque vence: a origem gravada é a da primeira visita (o anúncio que trouxe a pessoa)."""
    con = db()
    if vid and con.execute("select 1 from visitante where id=?", (vid,)).fetchone():
        return vid
    vid = vid if vid and len(vid) <= 40 else novo_id("v")
    campos = {k: str(dados.get(k, ""))[:200] for k in UTM + CLIQUES + ("referrer", "landing")}
    con.execute(
        "insert or ignore into visitante(id, criado, utm_source, utm_medium, utm_campaign, utm_content, utm_term,"
        " fbclid, gclid, ttclid, referrer, landing, ip, ua) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (vid, time.time(), *[campos[k] for k in UTM + CLIQUES + ("referrer", "landing")], ip[:64], ua[:300]),
    )
    return vid


EVENTOS = {"visita", "vsl_play", "vsl_25", "vsl_50", "vsl_75", "vsl_100", "cta_visto", "cta_clique",
           "checkout", "compra", "lead"}


def evento(vid: str, nome: str, produto: str = "", valor: float = 0, dados: dict | None = None) -> None:
    if nome not in EVENTOS:
        raise ValueError(f"evento desconhecido: {nome}")
    db().execute("insert into evento(visitante, nome, produto, valor, dados, criado) values(?,?,?,?,?,?)",
                 (vid, nome, produto[:80], valor, json.dumps(dados or {})[:2000], time.time()))


def funil(produto_slug: str | None = None) -> list[dict]:
    """Funil por origem: visitantes únicos em cada etapa, agrupados por utm_source/utm_campaign."""
    etapas = ["visita", "vsl_play", "cta_visto", "checkout", "compra"]
    filtro, args = ("and e.produto=?", [produto_slug]) if produto_slug else ("", [])
    # O que entra por f-string são os nomes fixos de `etapas`; o filtro do usuário vai por parâmetro (?).
    sql = ("select coalesce(nullif(v.utm_source,''),'(direto)') src, coalesce(nullif(v.utm_campaign,''),'-') camp, "  # noqa: S608
           + ", ".join(f"count(distinct case when e.nome='{e}' then e.visitante end) {e}" for e in etapas)
           + ", sum(case when e.nome='compra' then e.valor else 0 end) receita"
           f" from evento e join visitante v on v.id=e.visitante where 1=1 {filtro}"
           " group by src, camp order by receita desc, visita desc")
    return [dict(r) for r in db().execute(sql, args)]


def resumo() -> dict:
    """Os números do topo do painel: visitantes únicos, pedidos, vendas pagas e receita."""
    con = db()
    visitantes = con.execute("select count(distinct visitante) from evento where nome='visita'").fetchone()[0]
    checkouts, vendas, receita = con.execute(
        "select count(*), coalesce(sum(status='pago'),0), coalesce(sum(case when status='pago' then valor end),0) from pedido").fetchone()
    return {"visitantes": visitantes, "checkouts": checkouts, "vendas": vendas, "receita": receita}


def vendas_por_dia(dias: int = 14) -> list[tuple[str, float]]:
    """Receita paga por dia (data local do servidor), com os dias sem venda em zero: o gráfico não pula dia."""
    import datetime as dt
    hoje = dt.date(*time.localtime()[:3])  # mesma data local que o SQLite usa abaixo
    base = {(hoje - dt.timedelta(days=i)).isoformat(): 0.0 for i in range(dias - 1, -1, -1)}
    for d, v in db().execute("select date(pago_em,'unixepoch','localtime'), sum(valor) from pedido where status='pago'"
                             " and pago_em >= ? group by 1", (time.time() - dias * 86400,)):
        if d in base:
            base[d] = v
    return list(base.items())


def pedidos_recentes(limite: int = 30) -> list[dict]:
    return [dict(r) for r in db().execute("select * from pedido order by criado desc limit ?", (limite,))]


# ---------- checkout ----------

def order_bump(p: dict) -> dict | None:
    """O produto oferecido junto no checkout ("adicione também"), se o config.json declarar um que existe."""
    slug = (p.get("order_bump") or {}).get("produto")
    extra = produto(slug) if slug and slug != p["slug"] else None
    return {**extra, **{k: v for k, v in p["order_bump"].items() if k != "produto"}} if extra else None


def criar_pedido(slug: str, vid: str, nome: str, email: str, telefone: str, metodo: str, com_bump: bool = False) -> dict:
    p = produto(slug)
    if not p:
        raise KeyError("produto não existe")
    email = email.strip().lower()
    if "@" not in email or len(email) > 200:
        raise ValueError("e-mail inválido")
    # O preço vem sempre do config, nunca do formulário: o comprador não escolhe quanto paga.
    itens, valor = [slug], float(p["preco"])
    bump = order_bump(p) if com_bump else None
    if bump:
        itens.append(bump["slug"])
        valor = round(valor + float(bump.get("preco_bump", bump["preco"])), 2)
    pid = novo_id("ped")
    db().execute("insert into pedido(id, produto, visitante, nome, email, telefone, valor, status, metodo, criado, itens)"
                 " values(?,?,?,?,?,?,?,?,?,?,?)",
                 (pid, slug, vid, nome.strip()[:120], email, so_digitos(telefone)[:20], valor,
                  "pendente", metodo, time.time(), json.dumps(itens)))
    evento(vid, "checkout", slug, valor)
    return pedido(pid)


def itens_do_pedido(ped: dict) -> list[str]:
    try:
        itens = json.loads(ped.get("itens") or "[]")
    except ValueError:
        itens = []
    return itens or [ped["produto"]]


def pedido(pid: str) -> dict | None:
    r = db().execute("select * from pedido where id=?", (pid,)).fetchone()
    return dict(r) if r else None


def marcar_pago(pid: str) -> dict:
    """Idempotente: o webhook do gateway pode chegar duas vezes; só a primeira libera acesso e conta venda."""
    con = db()
    con.execute("begin immediate")
    try:
        ped = pedido(pid)
        if not ped:
            raise KeyError("pedido não existe")
        if ped["status"] == "pago":
            con.execute("commit")
            return {"pedido": ped, "novo": False, "membro": membro_por_email(ped["email"])}
        con.execute("update pedido set status='pago', pago_em=? where id=?", (time.time(), pid))
        mem = _garantir_membro(ped["email"], ped["nome"])
        for item in itens_do_pedido(ped):  # o order bump libera junto
            con.execute("insert or ignore into acesso(membro, produto) values(?,?)", (mem["id"], item))
        con.execute("insert into evento(visitante, nome, produto, valor, dados, criado) values(?,?,?,?,?,?)",
                    (ped["visitante"], "compra", ped["produto"], ped["valor"], json.dumps({"pedido": pid}), time.time()))
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return {"pedido": pedido(pid), "novo": True, "membro": mem}


def so_digitos(t: str) -> str:
    return "".join(c for c in (t or "") if c.isdigit())


# ---------- área de membros ----------

def _garantir_membro(email: str, nome: str) -> dict:
    con = db()
    m = membro_por_email(email)
    if m:
        return m
    con.execute("insert into membro(id, email, nome, token, criado) values(?,?,?,?,?)",
                (novo_id("m"), email, nome, secrets.token_urlsafe(24), time.time()))
    return membro_por_email(email)


def visitante_por_id(vid: str) -> dict | None:
    r = db().execute("select * from visitante where id=?", (vid,)).fetchone()
    return dict(r) if r else None


def mensagens_enviadas_desde(canal: str, desde: float) -> int:
    return db().execute("select count(*) from mensagem where canal=? and status='enviado' and criado>?",
                        (canal, desde)).fetchone()[0]


def membro_por_email(email: str) -> dict | None:
    r = db().execute("select * from membro where email=?", (email.strip().lower(),)).fetchone()
    return dict(r) if r else None


def membro_por_token(token: str) -> dict | None:
    if not token or len(token) > 64:
        return None
    r = db().execute("select * from membro where token=?", (token,)).fetchone()
    return dict(r) if r else None


def produtos_do_membro(mid: str) -> list[str]:
    return [r[0] for r in db().execute("select produto from acesso where membro=?", (mid,))]


def marcar_aula(mid: str, aula: str) -> None:
    db().execute("insert or ignore into progresso(membro, aula, feito) values(?,?,?)", (mid, aula[:80], time.time()))


def aulas_feitas(mid: str) -> set[str]:
    return {r[0] for r in db().execute("select aula from progresso where membro=?", (mid,))}


# ---------- remarketing: recuperação de checkout abandonado ----------

def recuperacao_pendente(agora: float | None = None) -> list[tuple[dict, dict]]:
    """Pedidos pendentes cuja próxima etapa da sequência já venceu. A sequência mora no config.json."""
    agora = agora or time.time()
    seq = config().get("recuperacao", [])
    saida = []
    for r in db().execute("select * from pedido where status='pendente' and etapa_recuperacao < ?", (len(seq),)):
        ped = dict(r)
        etapa = seq[ped["etapa_recuperacao"]]
        if agora - ped["criado"] >= etapa["apos_minutos"] * 60:
            saida.append((ped, etapa))
    return saida


def avancar_recuperacao(pid: str) -> None:
    db().execute("update pedido set etapa_recuperacao = etapa_recuperacao + 1 where id=? and status='pendente'", (pid,))


def registrar_mensagem(canal: str, para: str, texto: str, motivo: str, pedido_id: str, status: str, erro: str = "") -> None:
    db().execute("insert into mensagem(canal, para, texto, motivo, pedido, status, criado, erro) values(?,?,?,?,?,?,?,?)",
                 (canal, para, texto[:4000], motivo, pedido_id, status, time.time(), erro[:500]))


def mensagens(limite: int = 50) -> list[dict]:
    return [dict(r) for r in db().execute("select * from mensagem order by id desc limit ?", (limite,))]


def publico_hash(status: str = "pendente") -> list[dict]:
    """Público para remarketing (Custom Audience da Meta): só e-mail e telefone em sha256, nunca em claro."""
    out = []
    for r in db().execute("select distinct email, telefone from pedido where status=?", (status,)):
        out.append({"email_sha256": sha(r["email"]), "phone_sha256": sha(telefone_e164(r["telefone"])) if r["telefone"] else ""})
    return out


def sha(t: str) -> str:
    return hashlib.sha256(t.strip().lower().encode()).hexdigest()


def telefone_e164(t: str) -> str:
    d = so_digitos(t)
    return d if d.startswith("55") and len(d) >= 12 else "55" + d


# ---------- robô de mensagens (estilo Manychat): estado da conversa ----------

def conversa(canal: str, contato: str) -> dict | None:
    r = db().execute("select * from conversa where canal=? and contato=?", (canal, contato)).fetchone()
    return dict(r) if r else None


def gravar_conversa(canal: str, contato: str, fluxo: str | None, passo: int) -> None:
    if fluxo is None:
        db().execute("delete from conversa where canal=? and contato=?", (canal, contato))
        return
    db().execute("insert into conversa(canal, contato, fluxo, passo, atualizado) values(?,?,?,?,?)"
                 " on conflict(canal, contato) do update set fluxo=excluded.fluxo, passo=excluded.passo,"
                 " atualizado=excluded.atualizado", (canal, contato, fluxo, passo, time.time()))


# ---------- espionagem: biblioteca de anúncios salvos (swipe file) ----------

def salvar_anuncio(fonte: str, anunciante: str, texto: str, url: str, nota: str = "") -> int:
    cur = db().execute("insert into anuncio(fonte, anunciante, texto, url, nota, criado) values(?,?,?,?,?,?)",
                       (fonte[:40], anunciante[:200], texto[:5000], url[:500], nota[:1000], time.time()))
    return cur.lastrowid


def anuncios(q: str = "") -> list[dict]:
    like = f"%{q}%"
    return [dict(r) for r in db().execute(
        "select * from anuncio where anunciante like ? or texto like ? order by id desc limit 200", (like, like))]


# ---------- Telegram: o chat do comprador ligado ao pedido pelo /start <pedido> ----------

def ligar_telegram(pedido_id: str, chat: str) -> bool:
    if not pedido(pedido_id):
        return False
    db().execute("insert into telegram(pedido, chat, criado) values(?,?,?) on conflict(pedido) do update set chat=excluded.chat",
                 (pedido_id, str(chat)[:40], time.time()))
    return True


def telegram_do_pedido(pedido_id: str) -> str | None:
    r = db().execute("select chat from telegram where pedido=?", (pedido_id,)).fetchone()
    return r[0] if r else None
