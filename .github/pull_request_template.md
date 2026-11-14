## O que muda e por quê

<!-- Uma mudança por PR. Liga a uma issue: "Closes #N". -->

## Como validei

```
ruff check .
python3 -m pytest -q tests     # cole a última linha: "N passed in ..."
```

- [ ] Teste novo que **falha sem** esta mudança (nome descreve a falha)
- [ ] Mexi em página? Print em 390 px de largura (celular) aqui embaixo
- [ ] Variável de ambiente nova está no `README.md`; arquivo ou pasta nova está no mapa do `AGENTS.md`
- [ ] Nada de dependência externa, script inline ou SQL fora do `nucleo.py` (o CI cobra)

## O que ficou de fora
