"""Order bump: o produto extra entra no preço e no acesso, e o preço nunca vem do formulário."""
import sqlite3

from test_funil import ADMIN, req

import app
import nucleo as n

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _comprar(srv, extra=b""):
    corpo = b"nome=Ana+Souza&email=ana@exemplo.com&email2=ana@exemplo.com&telefone=48999990000" + extra
    st, h, _ = req(f"{srv}/c/metodo-demo", corpo, FORM)
    assert st == 303, st
    return h["Location"].split("pedido=")[1]


def test_bump_marcado_soma_o_preco_do_bump_e_libera_os_dois_produtos(srv):
    pid = _comprar(srv, b"&bump=1")
    assert n.pedido(pid)["valor"] == round(97.0 + 19.9, 2)
    app.liberar(pid)
    mid = n.membro_por_email("ana@exemplo.com")["id"]
    assert set(n.produtos_do_membro(mid)) == {"metodo-demo", "planilha-metas"}


def test_sem_bump_o_pedido_e_so_o_produto_principal(srv):
    pid = _comprar(srv)
    assert n.pedido(pid)["valor"] == 97.0
    app.liberar(pid)
    assert n.produtos_do_membro(n.membro_por_email("ana@exemplo.com")["id"]) == ["metodo-demo"]


def test_valor_inventado_no_formulario_nao_muda_o_preco(srv):
    pid = _comprar(srv, b"&valor=1&preco=1&bump=1")
    assert n.pedido(pid)["valor"] == 116.9


def test_emails_diferentes_nao_criam_pedido(srv):
    corpo = b"nome=Ana&email=ana@exemplo.com&email2=outra@exemplo.com"
    st, _, b = req(f"{srv}/c/metodo-demo", corpo, FORM)
    assert st == 400 and "não são iguais" in b.decode()
    assert n.db().execute("select count(*) from pedido").fetchone()[0] == 0


def test_banco_antigo_sem_coluna_de_itens_ganha_a_coluna_sem_perder_pedido(tmp_path, monkeypatch):
    # O banco que já está no ar foi criado antes do order bump: abrir com o código novo não pode quebrar nem apagar pedido.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    velho = sqlite3.connect(tmp_path / "funil.db")
    velho.execute("create table pedido(id text primary key, produto text, visitante text, nome text, email text, telefone text,"
                  " valor real, status text, metodo text, criado real, pago_em real, etapa_recuperacao integer default 0)")
    velho.execute("insert into pedido(id, produto, valor, status) values('ped_velho','metodo-demo',97,'pendente')")
    velho.commit()
    velho.close()
    n._LOCAL.__dict__.clear()
    ped = n.pedido("ped_velho")
    assert ped["valor"] == 97 and n.itens_do_pedido(ped) == ["metodo-demo"]


def test_painel_mostra_o_grafico_de_receita(srv):
    app.liberar(_comprar(srv))
    html = req(f"{srv}/painel", cab={"Authorization": f"Bearer {ADMIN}"})[2].decode()
    assert "Receita nos últimos 14 dias" in html and "<svg" in html and "R$ 97,00" in html
