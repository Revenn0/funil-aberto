"""Evolution, Telegram e Composio de mentira: o que se prova é o que o funil pede a cada um e o que faz com a resposta."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_funil import ADMIN, assinar, comprar, req

import app
import conexoes as cx
import integracoes as ig
import nucleo as n


class Falso:
    """Um servidor que anota cada pedido e responde o que o teste mandar, por (método, caminho)."""

    def __init__(self):
        self.pedidos, self.respostas, self.estado = [], {}, "close"
        f = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _r(self):
                corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                caminho = self.path.split("?")[0]
                f.pedidos.append({"m": self.command, "p": caminho, "q": self.path, "h": {k.lower(): v for k, v in self.headers.items()},
                                  "b": json.loads(corpo) if corpo else None})
                st, obj = f.respostas.get((self.command, caminho), (200, {}))
                if callable(obj):
                    st, obj = obj()
                d = json.dumps(obj).encode()
                self.send_response(st)
                self.send_header("Content-Length", str(len(d)))
                self.end_headers()
                self.wfile.write(d)

            do_GET = do_POST = do_DELETE = _r

        self.s = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}"

    def de(self, m, p):
        return [x for x in self.pedidos if x["m"] == m and x["p"] == p]


@pytest.fixture()
def falso():
    f = Falso()
    yield f
    f.s.shutdown()


@pytest.fixture()
def evo(falso, monkeypatch):
    monkeypatch.setenv("EVOLUTION_URL", falso.url)
    monkeypatch.setenv("EVOLUTION_KEY", "chave-evo")
    monkeypatch.setenv("EVOLUTION_INSTANCIA", "funil")
    falso.respostas[("GET", "/instance/connectionState/funil")] = (404, {"erro": "nao existe"})
    falso.respostas[("GET", "/instance/connect/funil")] = (200, {"base64": "QUJD", "pairingCode": "WZYX1234"})
    return falso


def test_qr_cria_a_instancia_so_na_primeira_vez_e_devolve_imagem(srv, evo):
    qr = cx.whatsapp_qr()
    assert qr == {"qr": "data:image/png;base64,QUJD", "codigo": "WZYX1234"}
    assert evo.de("POST", "/instance/create")[0]["b"]["instanceName"] == "funil"
    evo.respostas[("GET", "/instance/connectionState/funil")] = (200, {"instance": {"state": "connecting"}})
    cx.whatsapp_qr()
    assert len(evo.de("POST", "/instance/create")) == 1


def test_envio_vai_pela_instancia_do_funil_com_a_chave_no_cabecalho(srv, evo):
    assert ig.enviar("whatsapp", "(48) 99999-0000", "oi") == "enviado"
    p = evo.de("POST", "/message/sendText/funil")[0]
    assert p["b"] == {"number": "5548999990000", "text": "oi"} and p["h"]["apikey"] == "chave-evo"


def test_teto_do_dia_recusa_antes_de_mandar(srv, evo, monkeypatch):
    monkeypatch.setattr(cx, "TETO_DIA", 2)
    ig.enviar("whatsapp", "48999990000", "1")
    ig.enviar("whatsapp", "48999990000", "2")
    assert ig.enviar("whatsapp", "48999990000", "3") == "erro"
    assert len(evo.de("POST", "/message/sendText/funil")) == 2
    assert "teto" in n.mensagens(1)[0]["erro"]


def test_erro_da_evolution_nao_vaza_o_corpo_da_resposta(srv, evo):
    evo.respostas[("POST", "/message/sendText/funil")] = (500, {"segredo": "nao-pode-aparecer"})
    assert ig.enviar("whatsapp", "48999990000", "oi") == "erro"
    assert "nao-pode-aparecer" not in n.mensagens(1)[0]["erro"]


@pytest.fixture()
def tg(falso, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_USUARIO", "funil_demo_bot")
    monkeypatch.setenv("TELEGRAM_API", falso.url)
    falso.respostas[("POST", "/bot123:abc/sendMessage")] = (200, {"ok": True, "result": {}})
    return falso


def test_webhook_do_telegram_com_segredo_errado_e_404(srv, tg):
    corpo = json.dumps({"message": {"chat": {"id": 7}, "text": "quero"}}).encode()
    assert req(f"{srv}/api/telegram/errado", corpo)[0] == 404
    assert tg.de("POST", "/bot123:abc/sendMessage") == []


def test_start_com_pedido_liga_o_chat_e_o_acesso_chega_no_telegram(srv, tg):
    pid = comprar(srv)
    _, _, pagina_pix = req(f"{srv}/c/metodo-demo?pedido={pid}")
    assert f"https://t.me/funil_demo_bot?start={pid}" in pagina_pix.decode()
    corpo = json.dumps({"message": {"chat": {"id": 777}, "text": f"/start {pid}"}}).encode()
    assert req(f"{srv}/api/telegram/{cx.telegram_segredo_webhook()}", corpo)[0] == 200
    assert n.telegram_do_pedido(pid) == "777"
    app.liberar(pid)
    textos = [p["b"]["text"] for p in tg.de("POST", "/bot123:abc/sendMessage") if p["b"]["chat_id"] == "777"]
    assert any("/m/" in t for t in textos)


def test_robo_responde_no_telegram(srv, tg):
    corpo = json.dumps({"message": {"chat": {"id": 9}, "text": "quero"}}).encode()
    req(f"{srv}/api/telegram/{cx.telegram_segredo_webhook()}", corpo)
    assert "maior desafio" in tg.de("POST", "/bot123:abc/sendMessage")[0]["b"]["text"]


@pytest.fixture()
def comp(falso, monkeypatch, tmp_path):
    monkeypatch.setenv("COMPOSIO_API_KEY", "ak_teste")
    monkeypatch.setenv("COMPOSIO_URL", falso.url)
    # Forma da resposta real (medida em 13/11): a sessão vem em `session_id`, não em `id`.
    falso.respostas[("POST", "/api/v3.1/tool_router/session")] = (201, {"session_id": "trs_1", "mcp": {}})
    falso.respostas[("POST", "/api/v3.1/tool_router/session/trs_1/link")] = (201, {"redirect_url": "https://connect.composio.dev/link/x"})
    falso.respostas[("POST", "/api/v3/tools/execute/GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND")] = (200, {"successful": True})
    cfg = json.loads((Path(n.AQUI) / "config.json").read_text())
    cfg["integracoes"] = [{"evento": "compra", "ferramenta": "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND",
                           "argumentos": {"spreadsheetId": "abc", "values": [["{pedido}", "{email}", "{valor}"]]}}]
    arq = tmp_path / "config.json"
    arq.write_text(json.dumps(cfg))
    monkeypatch.setenv("FUNIL_CONFIG", str(arq))
    return falso


def test_conectar_app_abre_o_link_da_composio_com_o_usuario_da_operacao(srv, comp):
    st, h, _ = req(f"{srv}/entrar", f"token={ADMIN}".encode(), {"Content-Type": "application/x-www-form-urlencoded"})
    cookie = h["Set-Cookie"].split(";")[0]
    st, h, _ = req(f"{srv}/painel/conexoes/composio", b"toolkit=gmail",
                   {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
    assert st == 303 and h["Location"] == "https://connect.composio.dev/link/x"
    assert comp.de("POST", "/api/v3.1/tool_router/session")[0]["b"]["user_id"].startswith("funil_")
    assert comp.de("POST", "/api/v3.1/tool_router/session/trs_1/link")[0]["b"] == {"toolkit": "gmail"}
    assert comp.pedidos[0]["h"]["x-api-key"] == "ak_teste"


def test_toolkit_invalido_nao_chega_na_composio(srv, comp):
    with pytest.raises(cx.ErroConexao):
        cx.composio_link("../../admin")
    assert comp.pedidos == []


def test_compra_dispara_a_integracao_uma_vez_com_os_dados_do_pedido(srv, comp):
    pid = comprar(srv)
    corpo = json.dumps({"pedido": pid, "status": "pago"}).encode()
    for _ in range(2):
        req(f"{srv}/api/webhook/pagamento", corpo, {"X-Assinatura": assinar(corpo)})
    feitos = comp.de("POST", "/api/v3/tools/execute/GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND")
    assert len(feitos) == 1
    assert feitos[0]["b"]["arguments"]["values"] == [[pid, "ana@exemplo.com", "97.00"]]


def test_integracao_sem_chave_fica_simulada(srv, comp, monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY")
    assert cx.disparar("compra", {"pedido": "x"}) == [{"ferramenta": "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND", "status": "simulado"}]
    assert comp.pedidos == []

