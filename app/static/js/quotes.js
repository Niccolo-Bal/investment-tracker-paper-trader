window.Quotes = {
  async fetch(symbols) {
    const list = [...new Set((symbols || []).map((s) => String(s).trim().toUpperCase()).filter(Boolean))];
    if (!list.length) return {};
    const data = await Api.get(`/api/quotes?symbols=${encodeURIComponent(list.join(","))}`);
    return data.quotes || {};
  },

  async fillQuoteHint(symbolInput, targetEl) {
    if (!symbolInput || !targetEl) return;
    const symbol = symbolInput.value.trim().toUpperCase();
    if (!symbol) {
      targetEl.textContent = "Enter a symbol to preview the latest price.";
      return;
    }
    targetEl.textContent = "Fetching quote…";
    try {
      const quotes = await this.fetch([symbol]);
      const q = quotes[symbol];
      if (!q || q.price == null) {
        targetEl.textContent = q?.error || "No quote available.";
        return;
      }
      const changeClass = Fmt.pnlClass(q.change);
      targetEl.innerHTML = `Last: <strong>${Fmt.money(q.price)}</strong> · Day: <span class="${changeClass}">${Fmt.signedMoney(q.change)} (${Fmt.pct(q.change_pct)})</span>`;
    } catch (err) {
      targetEl.textContent = err.message || "Quote failed.";
    }
  },
};
