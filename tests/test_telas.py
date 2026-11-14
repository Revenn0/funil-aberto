"""As telas: o que o comprador lê (preço, Pix) e o que a página carrega (só do próprio servidor, sem script inline)."""
import re
from pathlib import Path

from test_funil import comprar, req

import paginas as pg

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_preco_sai_no_formato_brasileiro():
    assert pg.brl(97) == "R$ 97,00" and pg.brl(1234.5) == "R$ 1.234,50" and pg.brl(None) == "R$ 0,00"


def test_checkout_mostra_o_preco_com_virgula_e_nao_com_ponto(srv):
    html = req(f"{srv}/c/metodo-demo")[2].decode()
    assert "R$ 97,00" in html and "R$ 97.00" not in html


def test_pagina_do_pix_entrega_o_codigo_ao_desenho_do_qr(srv):
    pid = comprar(srv)
    html = req(f"{srv}/c/metodo-demo?pedido={pid}")[2].decode()
    assert re.search(r'data-qr="0002012[^"]*br\.gov\.bcb\.pix', html) and "/static/qrcode.js" in html


def test_telas_do_comprador_nao_chamam_terceiros_nem_tem_script_inline(srv):
    # Fonte ou script de CDN no checkout entrega a visita do comprador a outra empresa; script inline quebra a CSP.
    pid = comprar(srv)
    for rota in ("/v/metodo-demo", "/c/metodo-demo", f"/c/metodo-demo?pedido={pid}", "/entrar"):
        st, h, corpo = req(f"{srv}{rota}")
        html = corpo.decode()
        assert st == 200, rota
        assert not re.search(r'(src|href)="?https?://', html.split("<video")[0]), rota
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html), rota
        assert "script-src 'self'" in h["Content-Security-Policy"], rota


def test_estatico_serve_com_tipo_certo_e_recusa_caminho_para_fora(srv):
    st, h, _ = req(f"{srv}/static/estilo.css")
    assert st == 200 and h["Content-Type"].startswith("text/css")
    assert req(f"{srv}/static/fontes/bricolage.woff2")[1]["Content-Type"] == "font/woff2"
    assert req(f"{srv}/static/../app.py")[0] == 404
    assert req(f"{srv}/static/CREDITOS.md")[0] == 404  # tipo fora da lista não é servido


def test_todo_arquivo_de_terceiro_tem_licenca_declarada():
    creditos = (STATIC / "CREDITOS.md").read_text()
    for arq in ("qrcode.js", "fontes/bricolage.woff2", "fontes/plex-400.woff2", "fontes/plex-mono.woff2"):
        assert (STATIC / arq).exists(), arq
    assert "qrcode.js" in creditos and "OFL" in creditos and "MIT" in creditos
    assert "MIT license" in (STATIC / "qrcode.js").read_text()[:600]
    for lic in ("OFL-bricolage.txt", "OFL-ibm-plex.txt"):
        assert "Open Font License" in (STATIC / "fontes" / lic).read_text()


def test_imagem_do_conteiner_leva_a_pasta_static():
    assert "COPY static ./static" in (STATIC.parent / "Dockerfile").read_text()


def test_toda_foto_de_demonstracao_tem_credito():
    creditos = (STATIC / "demo" / "CREDITOS.md").read_text()
    fotos = sorted(p.name for p in (STATIC / "demo").glob("*.webp"))
    assert fotos and all(f in creditos for f in fotos), [f for f in fotos if f not in creditos]


def test_video_responde_por_pedaco_como_o_safari_do_iphone_exige(srv):
    st, h, corpo = req(f"{srv}/static/demo/vsl-demo.mp4", cab={"Range": "bytes=0-99"})
    assert st == 206 and len(corpo) == 100 and h["Content-Type"] == "video/mp4"
    assert h["Content-Range"].startswith("bytes 0-99/") and h["Accept-Ranges"] == "bytes"
    total = int(h["Content-Range"].split("/")[1])
    assert req(f"{srv}/static/demo/vsl-demo.mp4", cab={"Range": f"bytes={total}-"})[0] == 416


def test_video_da_demo_e_do_proprio_servidor():
    import json
    cfg = json.loads((STATIC.parent / "config.json").read_text())
    assert cfg["produtos"][0]["vsl"]["video"] == "/static/demo/vsl-demo.mp4"
    # 24 s em 720p cabem em ~0,5 MB; um vídeo de 5 MB aqui já foi um render que saiu com 1 hora (zoom aplicado quadro a quadro).
    assert (STATIC / "demo" / "vsl-demo.mp4").stat().st_size < 2_000_000
