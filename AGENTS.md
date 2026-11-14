# AGENTS.md — funil-aberto

> Contexto para quem vai mexer aqui, gente ou agente (Claude Code, Codex, Cursor, Copilot…). O `CLAUDE.md` importa este
> arquivo; regra nova entra **aqui**, uma cópia só. *English speakers: the code and docs are in Brazilian Portuguese because the
> product is Brazilian (Pix, LGPD, WhatsApp-first sales). Issues and PRs in English are welcome.*

## O que é, em uma frase

A operação de venda online (digital/DR) inteira num processo só, de código aberto (MIT): tracker com UTM e Meta CAPI, página de VSL,
checkout com Pix direto na chave do vendedor (sem gateway), order bump, área de membros, recuperação de carrinho por WhatsApp/e-mail/Telegram,
robô por palavra-chave estilo Manychat, spy da Biblioteca de Anúncios e integrações pela Composio. **Python 3.10+ só com a biblioteca
padrão + SQLite.** Roda com `python3 app.py`.

No ar: https://funil.genesisinnovation.com.br/v/metodo-demo · conceito: https://funil.fabweb.io

## Comandos (os mesmos do CI)

    python3 app.py                                    # http://localhost:8080/v/metodo-demo (ADMIN_TOKEN e WEBHOOK_SECRET para o painel)
    python3 -m pip install pytest==8.4.2 ruff==0.14.2 # só para desenvolver; o app não tem dependência
    ruff check .                                      # lint (regras em ruff.toml)
    python3 -m pytest -q tests                        # ~60 testes, ~45 s: sobem o servidor de verdade e percorrem o funil
    docker build -t funil-aberto .                    # a imagem que roda em produção

Um PR só entra com os três verdes. O CI (`.github/workflows/ci.yml`) roda exatamente isto.

## Mapa do repositório

| Arquivo | O que mora nele | Não ponha aqui |
|---|---|---|
| `app.py` | servidor HTTP (`http.server`), rotas, login do painel, CSP, `liberar()` (o que acontece quando um pedido é pago) e o laço de recuperação | SQL, HTML |
| `nucleo.py` | **o único arquivo com SQL**: tabelas, migração (`_migrar`), pedidos, membros, eventos, funil, conversas | rede, HTML |
| `paginas.py` | todo o HTML (funções que devolvem string), um tema por área: `t-checkout`, `t-vsl`, `t-membros`, `t-admin` | `<script>` inline (a CSP bloqueia) |
| `integracoes.py` | Meta CAPI, envio por canal (`enviar`), e-mail (SMTP ou Gmail pela Composio), recuperação, robô (`responder`), spy | chave em código |
| `conexoes.py` | os provedores: WhatsApp (maus-conexoes, Evolution própria ou Cloud API), Telegram Bot API, Composio (link, execução, `disparar`) | lógica de negócio |
| `pix.py` | BR Code estático (copia e cola) com CRC16 do Banco Central | — |
| `config.json` | **o negócio como dado**: produtos, preços, VSL, order bump, depoimentos, FAQ, sequência de recuperação, fluxos do robô, integrações | — |
| `static/` | `estilo.css`, `funil.js` (CTA da VSL, cronômetro, QR, Pix), `qrcode.js` (MIT), fontes OFL, `demo/` (imagens e vídeo da demo, com créditos) | biblioteca por CDN |
| `docs/` | banners do README (claro e escuro) e `telas/` com os prints; refaça os prints quando a tela mudar | imagem de terceiro sem licença |
| `site/` | a página de conceito (https://funil.fabweb.io), estática | o app |
| `tests/` | `test_funil.py` (o funil inteiro), `test_conexoes.py` (provedores falsos em HTTP), `test_telas.py` (CSP, formato BRL, vídeo com Range), `test_bump.py`, `test_regras_do_repo.py` (as regras deste arquivo que dá para conferir) | rede de verdade |
| `.github/` | CI, modelos de PR e de issue | — |

## Regras que o código cobra (e por quê)

Cada uma tem teste. Se o teste reclamar, conserte o código; não afrouxe o teste.

1. **Sem dependência externa.** Só biblioteca padrão (`test_app_importa_so_biblioteca_padrao_sem_dependencia_externa`). Quem baixa roda com
   `python3 app.py` numa VPS de R$ 20. Precisa de algo grande (ex.: Postgres)? Abra uma issue antes: a resposta costuma ser "atrás de
   uma variável de ambiente, opcional".
2. **SQL só no `nucleo.py`** (`test_sql_fora_do_nucleo_quebra_a_troca_de_banco`). Trocar SQLite por outro banco tem de ser um arquivo só.
   Coluna nova entra pela `_migrar()`, que adiciona sem apagar: o banco que está no ar é anterior ao seu código (`test_banco_antigo_...`).
3. **Toda variável de ambiente lida pelo código está no README** (`test_toda_variavel_de_ambiente_...`).
4. **Preço nunca vem do formulário.** O valor do pedido sai do `config.json` (`test_valor_inventado_no_formulario_nao_muda_o_preco`).
5. **Sem script inline nem CDN de terceiro.** A CSP é `script-src 'self'`; fonte e biblioteca ficam em `static/` com a licença ao lado.
6. **"Simulado" nunca aparece como "enviado".** Sem credencial nada sai da máquina e o status gravado é `simulado`. Envio que pode ter
   saído mas não confirmou é erro, não sucesso.
7. **Segredo não vai para log, HTML nem mensagem de erro.** Erro de provedor não ecoa o corpo da resposta. O painel abre por login, e o
   cookie guarda um HMAC derivado do `ADMIN_TOKEN`, nunca o token.
8. **Webhook só com assinatura** (`X-Assinatura` = HMAC-SHA256 do corpo com `WEBHOOK_SECRET`), e marcar pago é idempotente.
9. **Dado pessoal mínimo (LGPD).** A Meta recebe só hash (sha256). O `log_message` do servidor não grava IP nem caminho.
10. **O mapa acima cita todo arquivo `.py` e toda pasta** (`test_mapa_do_agents_md_...`). Criou módulo? Ponha uma linha na tabela.

## Como fazer as coisas comuns

- **Produto novo, preço, VSL, order bump, depoimento, FAQ:** só `config.json`. Nenhuma linha de código. Depoimento de exemplo leva
  `"exemplo": true` (a página mostra o selo); depoimento real precisa de autorização da pessoa.
- **Passo novo na recuperação de carrinho:** item em `recuperacao` no `config.json` (`apos_minutos`, `canal`, `texto` com `{nome}`, `{link}`).
- **Fluxo novo do robô:** item em `fluxos` (palavra-chave → passos).
- **Integração nova (planilha, CRM, Slack…):** item em `integracoes` no `config.json` com o `evento` (`checkout` ou `compra`) e a ferramenta da
  Composio. Só vira código se a Composio não tiver a ferramenta.
- **Canal novo de mensagem (ex.: SMS, Instagram Direct):** função de envio em `conexoes.py` com o mesmo contrato (devolve `enviado`,
  `simulado` ou levanta erro), um ramo em `integracoes.enviar`, o estado em `/painel/conexoes`, e um teste com servidor falso em
  `test_conexoes.py` (veja a classe `Falso` lá). Sem credencial, o canal fica `simulado`.
- **Banco/gateway novo que confirma Pix:** adapte o corpo dele para `POST /api/webhook/pagamento` (`{"pedido","status":"pago"}`, assinado).
  Se ele não assina com HMAC, escreva um adaptador com a verificação que ele oferece e teste a recusa de assinatura errada.
- **Tela nova:** função em `paginas.py` usando `documento(...)` com o tema da área; JS vai em `static/funil.js`. Confira em 390 px de largura
  (celular): é onde o comprador está.

## O que ainda não tem (bom lugar para começar)

Em ordem de quanto destrava a operação de alguém. Antes de começar, comente na issue (ou abra uma) para ninguém fazer em dobro.

1. **Pix dinâmico com confirmação automática** (cobrança com `txid` pelo PSP: Efí, Inter, Mercado Pago, Asaas). Hoje o Pix é estático e a
   confirmação vem de webhook seu ou de um clique no painel.
2. **Cartão nativo** (hoje só por `link_pagamento` para Stripe/Mercado Pago).
3. **Upsell de um clique depois da compra** e **cupom de desconto**.
4. **Editar produto pelo painel** (hoje é o `config.json` e reiniciar).
5. **Teste A/B** de headline/preço na VSL e no checkout, medido pelo próprio funil.
6. **Templates aprovados da Cloud API do WhatsApp** para recuperação fora da janela de 24 h.
7. **LGPD de ponta a ponta:** exportar e apagar os dados de um titular pelo painel.
8. **Postgres opcional** para várias réplicas (só o `nucleo.py` muda).
9. **Certificado de conclusão** e comentários nas aulas da área de membros.
10. **Tradução** (es/en) das páginas do comprador.

## Pull request

- Uma mudança por PR, pequena (mire em até ~300 linhas). Refatoração que ninguém pediu vira outra issue.
- **Teste que falha sem a sua mudança**, com nome que descreve a falha (`test_valor_inventado_no_formulario_nao_muda_o_preco`, não `test_preco`).
- No corpo: o que mudou, por quê, o comando que você rodou e o resultado (contagem de testes), e print da tela se mexeu em página.
- Commit em português no formato `tipo(escopo): descrição` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`).
- Não desligue, pule nem afrouxe teste ou regra de lint para o CI passar.

## De onde vem este repositório

O código nasce no monorepo da Genesis (`apps/sistemas/funil-aberto` em `thiagopatzdorf/fabrica-de-sites`, privado) e é espelhado aqui.
PRs **são bem-vindos aqui**: depois do merge, um mantenedor leva a mudança para o monorepo, e o espelho **recusa** publicar enquanto houver
mudança deste repositório que ainda não foi levada (nada que entra aqui se perde na próxima publicação). Por isso o CI deste repositório
roda em runner do GitHub, não nos da Genesis: runner próprio em repositório público executaria código de PR de qualquer pessoa numa
máquina nossa.
