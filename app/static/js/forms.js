document.addEventListener("DOMContentLoaded", () => {
  const typeRadios = document.querySelectorAll('input[name="type"]');
  const paperFields = document.getElementById("paper-fields");
  const realFields = document.getElementById("real-fields");

  function syncAccountTypeFields() {
    const selected = document.querySelector('input[name="type"]:checked');
    if (!selected) return;
    const isPaper = selected.value === "paper";
    if (paperFields) paperFields.hidden = !isPaper;
    if (realFields) realFields.hidden = isPaper;
  }

  typeRadios.forEach((el) => el.addEventListener("change", syncAccountTypeFields));
  syncAccountTypeFields();

  const orderType = document.getElementById("order_type");
  const limitField = document.getElementById("limit-field");
  const priceField = document.getElementById("price-field");

  function syncOrderType() {
    if (!orderType) return;
    const isLimit = orderType.value === "limit";
    if (limitField) limitField.hidden = !isLimit;
    if (priceField) priceField.hidden = orderType.value === "market" && !!document.body.dataset.paper;
  }

  if (orderType) {
    orderType.addEventListener("change", syncOrderType);
    syncOrderType();
  }

  const symbolInput = document.getElementById("symbol");
  const quoteHint = document.getElementById("quote-hint");
  if (symbolInput && quoteHint) {
    const update = () => Quotes.fillQuoteHint(symbolInput, quoteHint);
    symbolInput.addEventListener("blur", update);
    symbolInput.addEventListener("change", update);
  }

  const sellForm = document.getElementById("sell-form");
  if (sellForm) {
    const sharesInput = sellForm.querySelector('[name="shares"]');
    const priceInput = sellForm.querySelector('[name="price"]');
    const feesInput = sellForm.querySelector('[name="fees"]');
    const symbolSelect = sellForm.querySelector('[name="symbol"]');
    const estimateEl = document.getElementById("sell-estimate");
    const positions = JSON.parse(sellForm.dataset.positions || "[]");

    function updateEstimate() {
      if (!estimateEl) return;
      const symbol = (symbolSelect?.value || "").toUpperCase();
      const pos = positions.find((p) => p.symbol === symbol);
      const shares = Number(sharesInput?.value || 0);
      const price = Number(priceInput?.value || 0);
      const fees = Number(feesInput?.value || 0);
      if (!pos || !shares || !price) {
        estimateEl.textContent = "Select a position and enter exit details to estimate realized P&L.";
        return;
      }
      const proceeds = shares * price - fees;
      const cost = pos.avg_cost * shares;
      const pnl = proceeds - cost;
      estimateEl.innerHTML = `Est. realized P&L: <strong class="${Fmt.pnlClass(pnl)}">${Fmt.signedMoney(pnl)}</strong> on ${Fmt.number(shares, 4)} shares (avg cost ${Fmt.money(pos.avg_cost)}).`;
    }

    ["input", "change"].forEach((evt) => {
      sharesInput?.addEventListener(evt, updateEstimate);
      priceInput?.addEventListener(evt, updateEstimate);
      feesInput?.addEventListener(evt, updateEstimate);
      symbolSelect?.addEventListener(evt, updateEstimate);
    });
    updateEstimate();
  }

  document.querySelectorAll("[data-money]").forEach((el) => {
    el.textContent = Fmt.money(el.dataset.money);
  });
  document.querySelectorAll("[data-signed-money]").forEach((el) => {
    const v = el.dataset.signedMoney;
    el.textContent = Fmt.signedMoney(v);
    el.classList.add(Fmt.pnlClass(v));
  });
  document.querySelectorAll("[data-pct]").forEach((el) => {
    const v = el.dataset.pct;
    el.textContent = Fmt.pct(v);
    el.classList.add(Fmt.pnlClass(v));
  });
  document.querySelectorAll("[data-datetime]").forEach((el) => {
    el.textContent = Fmt.datetime(el.dataset.datetime);
  });
  document.querySelectorAll("[data-duration]").forEach((el) => {
    el.textContent = Fmt.duration(el.dataset.duration);
  });
});
