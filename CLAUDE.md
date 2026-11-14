# CLAUDE.md — funil-aberto

As regras, o mapa do repositório e os comandos estão no `AGENTS.md`, importado aqui para não haver duas cópias:

@AGENTS.md

Para o Claude Code, além disso:

- Antes de dar uma tarefa por pronta, rode `ruff check .` e `python3 -m pytest -q tests` e cite a contagem de testes.
- Mexeu em página? Suba `python3 app.py` e olhe a tela em 390 px de largura (celular) antes de dizer que ficou bom.
- Não invente credencial para "testar de verdade": sem variável de ambiente o envio fica `simulado`, e é isso que os testes esperam.
