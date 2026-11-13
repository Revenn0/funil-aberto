const PASSOS = [
  {mod:"tracker", acao:"Clica no anúncio do Facebook", tempo:"T+0s",
   texto:"A Ana chega pela campanha black-friday. O /t.js lê a URL e grava a origem no primeiro toque: se ela voltar depois pelo Google, a venda continua sendo do anúncio que a trouxe.",
   codigo:"visitante  v_8Kp2…  utm_source=facebook\n                     utm_campaign=black-friday\n                     fbclid=IwAR3…\nevento     visita   produto=metodo-demo",
   subs:"Substitui o <b>tracker de atribuição</b>.", conta:{visita:1}},
  {mod:"vsl", acao:"Dá play e assiste metade do vídeo", tempo:"T+2min",
   texto:"A página de VSL manda um evento no play e em cada quartil assistido. A retenção vira número por campanha, não um gráfico em outra ferramenta.",
   codigo:"evento  vsl_play\nevento  vsl_25\nevento  vsl_50",
   subs:"Substitui o <b>player de VSL</b> com métricas.", conta:{visita:1,play:1}},
  {mod:"vsl", acao:"O botão aparece no segundo 20", tempo:"T+20s de vídeo",
   texto:"O botão fica escondido até o segundo definido em cta_segundos. Quando aparece, grava cta_visto; quando ela clica, cta_clique.",
   codigo:"\"vsl\": { \"cta_segundos\": 20,\n         \"cta_texto\": \"Quero garantir minha vaga\" }\n\nevento  cta_visto\nevento  cta_clique",
   subs:"O <b>CTA atrasado</b> é configuração, não código.", conta:{visita:1,play:1,cta:1}},
  {mod:"checkout", acao:"Preenche nome, e-mail e WhatsApp", tempo:"T+6min",
   texto:"O pedido nasce pendente e ligado ao mesmo visitante. A Meta recebe InitiateCheckout pelo servidor, com e-mail e telefone em sha256.",
   codigo:"pedido   ped_aB7e…  R$ 97,00  pendente\nevento   checkout\nCAPI  →  InitiateCheckout\n         em=[sha256(ana@exemplo.com)]\n         fbc=fb.1.1763060000000.IwAR3…",
   subs:"Substitui o <b>checkout</b> e o <b>pixel server-side</b>.", conta:{visita:1,play:1,cta:1,checkout:1}},
  {mod:"checkout", acao:"Vê o Pix e não paga", tempo:"T+7min", abandono:true,
   texto:"O código Pix sai para a chave do vendedor, com o número do pedido dentro. A Ana fecha a aba. O pedido continua pendente.",
   codigo:"pix.copia_e_cola(chave, nome, cidade,\n                 valor=97.00, txid=\"pedaB7e…\")\n→ 000201…540597.00…6304 + CRC16",
   subs:"Sem gateway e sem taxa por venda.", conta:{visita:1,play:1,cta:1,checkout:1}},
  {mod:"recuperação", acao:"Recebe um WhatsApp 15 minutos depois", tempo:"T+22min",
   texto:"A cada minuto o laço de recuperação procura pedidos pendentes cuja próxima etapa venceu. A primeira etapa é WhatsApp aos 15 minutos, com o link do mesmo Pix.",
   codigo:"\"recuperacao\": [\n  {\"apos_minutos\": 15,   \"canal\": \"whatsapp\"},\n  {\"apos_minutos\": 240,  \"canal\": \"email\"},\n  {\"apos_minutos\": 1440, \"canal\": \"whatsapp\"} ]\n\nmensagem  whatsapp  recuperacao  enviado",
   subs:"Substitui a <b>recuperação de carrinho</b> e a régua de remarketing.", conta:{visita:1,play:1,cta:1,checkout:1}},
  {mod:"robô", acao:"Responde “quero” no WhatsApp", tempo:"T+25min",
   texto:"A resposta chega ao robô. A palavra quero abre um fluxo; cada nova mensagem avança um passo. O fluxo é um objeto no config.json.",
   codigo:"POST /api/bot/entrada  {\"texto\": \"quero\"}\n→ \"Que bom! Antes do link: qual é hoje\n   o seu maior desafio para vender online?\"",
   subs:"Substitui o <b>Manychat</b>.", conta:{visita:1,play:1,cta:1,checkout:1}},
  {mod:"pagamento", acao:"Paga o Pix", tempo:"T+31min",
   texto:"O banco avisa por webhook assinado. A liberação é idempotente: se o aviso chegar três vezes, conta uma venda e manda um acesso. A sequência de recuperação para sozinha.",
   codigo:"POST /api/webhook/pagamento\n     X-Assinatura: hmac_sha256(segredo, corpo)\npedido   ped_aB7e…  pago\nevento   compra  R$ 97,00\nCAPI  →  Purchase  value=97.00 BRL",
   subs:"A venda volta para a Meta e otimiza a campanha certa.", conta:{visita:1,play:1,cta:1,checkout:1,compra:1}},
  {mod:"membros", acao:"Abre a área de membros", tempo:"T+32min",
   texto:"O link de acesso chega por e-mail e WhatsApp. A área mostra os módulos do produto comprado e guarda a aula que ela marcou como vista.",
   codigo:"membro    m_Q2…  token=UkOa…\nacesso    metodo-demo\nprogresso m1a1  “Quem compra e por quê”",
   subs:"Substitui a <b>área de membros</b>.", conta:{visita:1,play:1,cta:1,checkout:1,compra:1}},
  {mod:"painel", acao:"O dono vê de onde veio a venda", tempo:"no painel",
   texto:"Uma consulta junta visitante e evento: visitas, plays, CTAs, checkouts, compras e receita por origem e campanha. Quem abandonou vira público de remarketing em hash.",
   codigo:"origem    campanha       visita play CTA ckout compra receita\nfacebook  black-friday     1     1    1    1     1   97,00\ngoogle    pesquisa         1     0    0    1     0    0,00",
   subs:"Substitui o <b>dashboard</b> e exporta o <b>público de remarketing</b>.", conta:{visita:1,play:1,cta:1,checkout:1,compra:1}}
];
const ETAPAS = [["visita","visita"],["play","play"],["cta","CTA"],["checkout","checkout"],["compra","compra"]];
let atual = 0;
const lista = document.getElementById("passos");
PASSOS.forEach((p, i) => {
  const li = document.createElement("li");
  if (p.abandono) li.classList.add("abandono");
  const b = document.createElement("button");
  b.type = "button";
  b.innerHTML = `<span class="ponto">${i + 1}</span><span><span class="mod">${p.mod}</span><br><span class="acao">${p.acao}</span></span>`;
  b.addEventListener("click", () => mostrar(i));
  li.appendChild(b);
  lista.appendChild(li);
});
function mostrar(i) {
  atual = Math.max(0, Math.min(PASSOS.length - 1, i));
  const p = PASSOS[atual];
  [...lista.children].forEach((li, k) => {
    li.classList.toggle("feito", k < atual);
    li.classList.toggle("atual", k === atual);
  });
  document.getElementById("d-tempo").textContent = `Passo ${atual + 1} de ${PASSOS.length} · ${p.tempo}`;
  document.getElementById("d-titulo").textContent = p.acao;
  document.getElementById("d-texto").textContent = p.texto;
  document.getElementById("d-codigo").textContent = p.codigo;
  document.getElementById("d-subs").innerHTML = p.subs;
  document.getElementById("placar").innerHTML = ETAPAS.map(([k, n]) =>
    `<div class="${p.conta[k] ? "on" : ""}"><b>${p.conta[k] || 0}</b><span>${n}</span></div>`).join("");
  document.getElementById("ant").disabled = atual === 0;
  document.getElementById("prox").textContent = atual === PASSOS.length - 1 ? "Recomeçar" : "Próximo passo →";
}
document.getElementById("ant").addEventListener("click", () => mostrar(atual - 1));
document.getElementById("prox").addEventListener("click", () => mostrar(atual === PASSOS.length - 1 ? 0 : atual + 1));
mostrar(0);
