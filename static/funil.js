// Comportamento das telas do comprador, sem nada inline: VSL (botão no segundo certo e retenção por quartil),
// checkout (visitante do tracker no formulário), Pix (QR desenhado aqui a partir do copia e cola, copiar, e a página
// que se atualiza sozinha quando o pagamento cai).
(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var ev = function (nome) { if (window.fa) window.fa(nome); };

  var vi = $("#vsl");
  if (vi) {
    var cta = $("#cta"), espera = $("#espera-cta"), seg = parseInt(vi.dataset.cta || "0", 10), f = {};
    var mostra = function () { if (cta.hidden) { cta.hidden = false; if (espera) espera.hidden = true; ev("cta_visto"); } };
    if (seg <= 0) mostra();
    vi.addEventListener("play", function () { if (!f.p) { f.p = 1; ev("vsl_play"); } });
    vi.addEventListener("timeupdate", function () {
      var t = vi.currentTime, d = vi.duration || 1;
      if (t >= seg) mostra();
      [25, 50, 75, 100].forEach(function (x) { if (!f[x] && t / d * 100 >= x - 0.5) { f[x] = 1; ev("vsl_" + x); } });
    });
    var bt = $("#cta a");
    if (bt) bt.addEventListener("click", function () { ev("cta_clique"); });
  }

  var vid = $("#vid"), m = document.cookie.match(/fa_vid=([^;]+)/);
  if (vid && m) vid.value = m[1];

  var alvo = $("[data-qr]");
  if (alvo && window.qrcode) {
    // Desenho próprio em SVG com viewBox: escala sem borrar e sem depender do formato de saída da biblioteca.
    var q = window.qrcode(0, "M"); q.addData(alvo.dataset.qr); q.make();
    var n = q.getModuleCount(), r = [];
    for (var y = 0; y < n; y++) for (var x = 0; x < n; x++) if (q.isDark(y, x)) r.push("M" + x + " " + y + "h1v1h-1z");
    alvo.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + n + " " + n + '" shape-rendering="crispEdges" role="img" aria-label="QR Code do Pix"><path fill="#0b1510" d="' + r.join("") + '"/></svg>';
  }

  document.querySelectorAll("[data-copiar]").forEach(function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById(b.dataset.copiar), txt = el.textContent.trim(), rot = b.textContent;
      var feito = function () { b.textContent = "Copiado!"; setTimeout(function () { b.textContent = rot; }, 2200); };
      var selecionar = function () { var s = window.getSelection(), rg = document.createRange(); rg.selectNodeContents(el); s.removeAllRanges(); s.addRange(rg); };
      if (navigator.clipboard) navigator.clipboard.writeText(txt).then(feito, selecionar); else selecionar();
    });
  });

  var ped = $("[data-pedido]");
  if (ped && ped.dataset.status !== "pago") {
    var timer = setInterval(function () {
      fetch("/api/pedido/" + ped.dataset.pedido).then(function (r) { return r.json(); }).then(function (j) {
        if (j.status !== "pago") return;
        clearInterval(timer);
        var p = $("#situacao"); p.className = "pilula ok"; p.textContent = "Pagamento confirmado";
        var msg = $("#msg-pago"); if (msg) msg.hidden = false;
      }).catch(function () {});
    }, 5000);
  }
})();
