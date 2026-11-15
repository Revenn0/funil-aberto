import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
import integracoes as ig
import nucleo as n
import pix

SEGREDO = "segredo-de-teste"
ADMIN = "admin-de-teste"


class SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def req(url, dados=None, cab=None, metodo=None, json_=True):
    corpo = dados if isinstance(dados, (bytes, type(None))) else json.dumps(dados).encode()
    r = urllib.request.Request(url, data=corpo, headers=cab or {}, method=metodo)
    abre = urllib.request.build_opener(SemRedirect())
    try:
        resp = abre.open(r)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def assinar(corpo: bytes) -> str:
    return hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()


def comprar(srv, vid=None, email="ana@exemplo.com"):
    form = f"vid={vid or ''}&nome=Ana+Souza&email={email}&telefone=48999990000".encode()
    st, h, _ = req(f"{srv}/c/metodo-demo", form, {"Content-Type": "application/x-www-form-urlencoded"})
    assert st == 303
    return h["Location"].split("pedido=")[1]


def test_pix_bate_com_o_exemplo_do_manual_do_banco_central():
    codigo = pix.copia_e_cola("123e4567-e12b-12d1-a456-426655440000", "Fulano de Tal", "BRASILIA")
    assert codigo == ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR"
                      "5913Fulano de Tal6008BRASILIA62070503***63041D3D")


def test_pix_tira_acento_e_respeita_tamanho_do_nome_e_da_cidade():
    c = pix.copia_e_cola("x@y.com", "Joao Sao Jose da Conceicao Silva", "Florianópolis Centro", 97)
    assert "Florianopolis C" in c and "5925Joao Sao Jose da Conceica6015" in c and "540597.00" in c


def test_venda_atribuida_ao_anuncio_do_primeiro_toque(srv):
    _, _, b = req(f"{srv}/t", {"nome": "visita", "utm_source": "facebook", "utm_campaign": "lancamento"})
    vid = json.loads(b)["vid"]
    req(f"{srv}/t", {"vid": vid, "nome": "vsl_play", "produto": "metodo-demo", "utm_source": "google"})
    pid = comprar(srv, vid)
    corpo = json.dumps({"pedido": pid, "status": "pago"}).encode()
    st, _, _ = req(f"{srv}/api/webhook/pagamento", corpo, {"X-Assinatura": assinar(corpo)})
    assert st == 200
    _, _, b = req(f"{srv}/api/admin/funil", cab={"Authorization": f"Bearer {ADMIN}"})
    linha = json.loads(b)[0]
    assert (linha["src"], linha["camp"], linha["compra"], linha["receita"]) == ("facebook", "lancamento", 1, 97.0)


def test_webhook_sem_assinatura_valida_nao_libera_acesso(srv):
    pid = comprar(srv)
    corpo = json.dumps({"pedido": pid, "status": "pago"}).encode()
    st, _, _ = req(f"{srv}/api/webhook/pagamento", corpo, {"X-Assinatura": "0" * 64})
    assert st == 401 and n.pedido(pid)["status"] == "pendente"


def test_webhook_repetido_conta_uma_venda_e_manda_um_acesso(srv):
    pid = comprar(srv)
    corpo = json.dumps({"pedido": pid, "status": "pago"}).encode()
    for _ in range(3):
        req(f"{srv}/api/webhook/pagamento", corpo, {"X-Assinatura": assinar(corpo)})
    assert n.db().execute("select count(*) from evento where nome='compra'").fetchone()[0] == 1
    assert n.db().execute("select count(*) from mensagem where motivo='acesso'").fetchone()[0] == 2  # e-mail + WhatsApp


def test_comprador_entra_na_area_de_membros_e_marca_aula(srv):
    pid = comprar(srv)
    app.liberar(pid)
    token = n.membro_por_email("ana@exemplo.com")["token"]
    st, _, b = req(f"{srv}/m/{token}")
    assert st == 200 and "Módulo 1: a oferta" in b.decode() and f"/m/{token}/aula/m1a1" in b.decode()
    st, _, b = req(f"{srv}/m/{token}/aula/m1a1")
    assert st == 200 and "Quem compra e por quê" in b.decode()
    st, h, _ = req(f"{srv}/m/{token}/feito", b"aula=m1a1", {"Content-Type": "application/x-www-form-urlencoded"})
    assert st == 303 and h["Location"] == f"/m/{token}/aula/m1a1"
    assert n.aulas_feitas(n.membro_por_email("ana@exemplo.com")["id"]) == {"m1a1"}


def test_aula_de_produto_que_o_membro_nao_comprou_nao_abre(srv):
    pid = comprar(srv)
    app.liberar(pid)
    token = n.membro_por_email("ana@exemplo.com")["token"]
    assert req(f"{srv}/m/{token}/aula/pl1")[0] == 404  # aula da planilha, que só vem com o order bump


def test_token_de_membro_inventado_nao_abre_area(srv):
    st, _, _ = req(f"{srv}/m/inventado")
    assert st == 404


def test_painel_sem_login_manda_para_entrar_e_token_na_url_nao_abre(srv):
    st, h, _ = req(f"{srv}/painel")
    assert st == 303 and h["Location"] == "/entrar"
    assert req(f"{srv}/painel?token={ADMIN}")[0] == 303


def test_login_abre_o_painel_e_o_cookie_nao_e_o_token(srv):
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    assert req(f"{srv}/entrar", b"token=errado", form)[0] == 401
    st, h, _ = req(f"{srv}/entrar", f"token={ADMIN}".encode(), form)
    cookie = h["Set-Cookie"].split(";")[0]
    assert st == 303 and "HttpOnly" in h["Set-Cookie"] and "SameSite=Strict" in h["Set-Cookie"] and ADMIN not in cookie
    assert req(f"{srv}/painel", cab={"Cookie": cookie})[0] == 200
    assert req(f"{srv}/painel/conexoes", cab={"Cookie": cookie})[0] == 200


def test_sem_admin_token_configurado_nada_abre_o_painel(srv, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    assert req(f"{srv}/entrar", b"token=", {"Content-Type": "application/x-www-form-urlencoded"})[0] == 401
    assert req(f"{srv}/api/admin/funil", cab={"Authorization": "Bearer "})[0] == 401


def test_recuperacao_segue_a_sequencia_e_para_quando_paga(srv):
    pid = comprar(srv)
    criado = n.pedido(pid)["criado"]
    n.db().execute("update pedido set criado=? where id=?", (criado - 16 * 60, pid))
    assert [f["canal"] for f in ig.rodar_recuperacao("http://x")] == ["whatsapp"]
    assert ig.rodar_recuperacao("http://x") == []  # etapa 2 só depois de 4 h
    app.liberar(pid)
    n.db().execute("update pedido set criado=? where id=?", (criado - 3 * 86400, pid))
    assert ig.rodar_recuperacao("http://x") == []


def test_mensagem_sem_credencial_fica_simulada_e_nao_enviada(srv):
    assert ig.enviar("whatsapp", "48999990000", "oi") == "simulado"
    assert n.mensagens(1)[0]["status"] == "simulado"


def test_robo_abre_fluxo_pela_palavra_e_avanca_passo_a_passo(srv):
    def fala(t):
        corpo = json.dumps({"canal": "whatsapp", "de": "5548999990000", "texto": t}).encode()
        return json.loads(req(f"{srv}/api/bot/entrada", corpo, {"X-Assinatura": assinar(corpo)})[2])["respostas"]
    assert "maior desafio" in fala("EU QUERO")[0]
    assert "/v/metodo-demo" in fala("vender mais")[0] and "{base}" not in fala("ok")[0]


def test_publico_de_remarketing_sai_so_em_hash(srv):
    comprar(srv)
    pub = n.publico_hash()
    assert pub[0]["email_sha256"] == hashlib.sha256(b"ana@exemplo.com").hexdigest()
    assert "ana@" not in json.dumps(pub)


def test_evento_capi_nao_leva_email_em_claro_e_tem_fbc():
    ped = {"id": "ped_1", "email": "Ana@Exemplo.com", "telefone": "48999990000", "valor": 97.0, "produto": "x"}
    ev = ig.evento_capi("Purchase", ped, {"fbclid": "abc", "criado": 1700000000.0}, "http://x")
    assert "Ana@" not in json.dumps(ev) and ev["user_data"]["fbc"] == "fb.1.1700000000000.abc"
    assert ev["user_data"]["ph"] == [hashlib.sha256(b"5548999990000").hexdigest()]


def test_evento_desconhecido_no_tracker_e_recusado(srv):
    assert req(f"{srv}/t", {"nome": "drop table"})[0] == 400


def test_paginas_do_funil_abrem(srv):
    for rota in ("/", "/v/metodo-demo", "/c/metodo-demo", "/t.js", "/saude"):
        assert req(f"{srv}{rota}")[0] == 200, rota
    pid = comprar(srv)
    _, _, b = req(f"{srv}/c/metodo-demo?pedido={pid}")
    assert "br.gov.bcb.pix" in b.decode()


def test_sonda_do_cluster_em_health_sem_resposta_reinicia_o_pod_em_loop(srv):
    # O sistema_novo.py gera readiness e liveness em /health; sem a rota o pod nunca fica pronto.
    st, _, corpo = req(f"{srv}/health", json_=False)
    assert st == 200 and b'"ok": true' in corpo
