window.Fmt = {
  money(value, opts = {}) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "—";
    }
    const n = Number(value);
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: opts.digits ?? 2,
      maximumFractionDigits: opts.digits ?? 2,
    }).format(n);
  },

  number(value, digits = 2) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "—";
    }
    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    }).format(Number(value));
  },

  pct(value) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "—";
    }
    const n = Number(value);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(2)}%`;
  },

  signedMoney(value) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "—";
    }
    const n = Number(value);
    const sign = n > 0 ? "+" : "";
    return `${sign}${this.money(n)}`;
  },

  pnlClass(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "";
    }
    const n = Number(value);
    if (n > 0) return "pos";
    if (n < 0) return "neg";
    return "";
  },

  duration(seconds) {
    if (seconds === null || seconds === undefined || seconds === "") return "—";
    const s = Math.max(0, Number(seconds));
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    if (days > 0) return `${days}d ${hours}h`;
    const mins = Math.floor((s % 3600) / 60);
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  },

  datetime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  },
};
