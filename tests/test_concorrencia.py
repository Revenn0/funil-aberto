"""Carga e concorrência: os três defeitos medidos em 15/11 com 64 clientes juntos, cada um com o seu teste."""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from test_funil import comprar

import app
import integracoes as ig
import nucleo as n

RAIZ = Path(__file__).resolve().parents[1]


def test_schema_rodando_em_toda_conexao_trava_o_banco_a_cada_visitante_novo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    n._LOCAL.__dict__.clear()
    chamadas = []
    original = n._migrar
    monkeypatch.setattr(n, "_migrar", lambda con: (chamadas.append(1), original(con)))
    n.db()
    threads = [threading.Thread(target=lambda: n.db().execute("select count(*) from pedido").fetchone()) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(chamadas) == 1, f"schema rodou {len(chamadas)} vezes para 9 conexões"


def test_duas_rodadas_de_recuperacao_cruzadas_mandam_a_mensagem_duas_vezes(srv, monkeypatch):
    pid = comprar(srv)
    n.db().execute("update pedido set criado = criado - 86400 where id=?", (pid,))
    retrato = n.recuperacao_pendente()          # o que duas rodadas leriam ao mesmo tempo
    assert [p["id"] for p, _ in retrato] == [pid]
    monkeypatch.setattr(n, "recuperacao_pendente", lambda: retrato)
    ig.rodar_recuperacao("http://x")
    ig.rodar_recuperacao("http://x")             # a 2ª rodada chega com a mesma leitura
    msgs = n.db().execute("select count(*) from mensagem where pedido=? and motivo='recuperacao'", (pid,)).fetchone()[0]
    etapa = n.pedido(pid)["etapa_recuperacao"]
    assert msgs == 1 and etapa == 1, f"{msgs} mensagens, etapa {etapa}"


def test_fila_de_espera_do_socket_curta_recusa_conexao_e_atrasa_o_cliente_em_segundos():
    assert app.Servidor.request_queue_size >= 128
    assert app.Servidor.daemon_threads is True


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_workers_2_atende_em_dois_processos_e_os_filhos_morrem_com_o_pai(tmp_path):
    if not hasattr(os, "fork"):
        return
    porta = _porta_livre()
    env = {**os.environ, "PORT": str(porta), "BIND": "127.0.0.1", "DATA_DIR": str(tmp_path), "WORKERS": "2",
           "ADMIN_TOKEN": "t", "WEBHOOK_SECRET": "t", "FUNIL_RECUPERACAO_LACO": "0"}
    pai = subprocess.Popen([sys.executable, "app.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        vistos = set()
        fim = time.time() + 10
        while time.time() < fim and len(vistos) < 2:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1) as r:
                    vistos.add(__import__("json").loads(r.read())["processo"])
            except OSError:
                time.sleep(0.05)
        assert len(vistos) == 2 and pai.pid not in vistos, vistos
    finally:
        pai.send_signal(signal.SIGTERM)
        pai.wait(timeout=10)
    time.sleep(0.3)
    for filho in vistos:
        try:
            os.kill(filho, 0)
            vivo = True
        except ProcessLookupError:
            vivo = False
        assert not vivo, f"filho {filho} ficou vivo depois do pai"
