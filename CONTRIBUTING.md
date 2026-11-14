# Contribuir com o funil-aberto

Obrigado. O contexto completo (mapa do código, regras, como fazer as mudanças comuns, o que falta) está no [`AGENTS.md`](AGENTS.md).
O caminho curto:

1. **Escolha o que fazer.** A seção "O que ainda não tem" do `AGENTS.md` está em ordem de impacto. Comente na issue (ou abra uma)
   antes de começar.
2. **Rode local:**

       python3 -m pip install pytest==8.4.2 ruff==0.14.2
       ruff check . && python3 -m pytest -q tests
       ADMIN_TOKEN=dev WEBHOOK_SECRET=dev python3 app.py     # http://localhost:8080/v/metodo-demo

3. **Faça a mudança com um teste que falha sem ela.** Produto, preço e fluxo são dados (`config.json`), não código.
4. **Abra o PR** preenchendo o modelo. O CI roda testes em Python 3.10, 3.12 e 3.13, o lint e a imagem Docker; os três precisam passar.

Segurança: vulnerabilidade vai pelo [aviso privado do GitHub](https://github.com/thiagopatzdorf/funil-aberto/security/advisories/new),
não por issue pública.
