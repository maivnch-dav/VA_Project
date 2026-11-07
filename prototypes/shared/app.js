// Shared prototype helpers: Tailwind theme, nav, verdict badges, Plotly defaults.
/* global tailwind, Plotly */
window.tailwind = window.tailwind || {};
tailwind.config = {
  theme: {
    extend: {
      colors: {
        page: "var(--page)", surface: "var(--surface)", surface2: "var(--surface-2)",
        ink: "var(--ink)", ink2: "var(--ink-2)", muted: "var(--muted)", grid: "var(--grid)",
        accent: "var(--accent)", axis: "var(--axis)",
      },
      fontFamily: { sans: ["Quicksand", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
                    mono: ["Inconsolata", "ui-monospace", "Menlo", "monospace"], display: ["Space Grotesk", "Quicksand", "sans-serif"] },
    },
  },
};

const SF = {
  verdicts: {
    gestuetzt: { cls: "supported", ico: "✓", label: "gestützt" },
    nicht_gestuetzt: { cls: "rejected", ico: "✕", label: "nicht gestützt" },
    unzureichende_daten: { cls: "unknown", ico: "?", label: "unzureichende Daten" },
  },
  badge(v, size = "") {
    const d = SF.verdicts[v];
    return `<span class="verdict ${d.cls} ${size}"><span class="ico" aria-hidden="true">${d.ico}</span>${d.label}</span>`;
  },
  // Plotly mirrors app/components/palette.py. Chart colours come from the active theme (themes/<id>.css, --chart-*,
  // --cat-*, --seq-*), read once on first use — themes load before any chart script runs (theme.js).
  get C() {
    const v = SF.cssVar;
    return (SF._C ||= {
      ink: v("--chart-ink"), ink2: v("--chart-ink2"), muted: v("--chart-muted"), grid: v("--chart-grid"), axis: v("--chart-axis"),
      surface: v("--chart"), hover: v("--chart-hover"), empty: v("--chart-empty"),
      cat: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--cat-${i}`)),
      other: v("--other"),
      // sequential on dark: low values recede toward the surface, high values are light
      seq: [700, 600, 500, 400, 300, 200, 100].map((i) => v(`--seq-${i}`)),
      accent: v("--chart-accent"), winter: v("--season-winter-bg"), divNeg: v("--div-neg"), divMid: v("--div-mid"), divPos: v("--div-pos"),
    });
  },
  cssVar: (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim(),
  layout(extra = {}) {
    const C = SF.C;
    const axis = { gridcolor: C.grid, linecolor: C.axis, zerolinecolor: C.axis, tickfont: { size: 11, color: C.ink2 },
                   title: { font: { size: 12, color: C.ink2 } }, automargin: true };
    return Object.assign({
      paper_bgcolor: C.surface, plot_bgcolor: C.surface,
      font: { family: "Inconsolata, ui-monospace, Menlo, monospace", size: 12, color: C.ink },
      margin: { l: 48, r: 12, t: 8, b: 36 }, hoverlabel: { bgcolor: C.hover, bordercolor: C.axis, font: { color: C.ink, size: 12 } },
      xaxis: { ...axis }, yaxis: { ...axis }, showlegend: false,
    }, extra);
  },
  // Dark chart chrome for the overview "screen" cards (UI-SPEC §4, dark steps)
  get D() {
    const C = SF.C;
    return (SF._D ||= { bg: SF.cssVar("--chart-screen"), ink: C.ink, ink2: C.ink2, muted: C.muted, grid: C.grid, axis: C.axis,
                        hover: C.hover, cat: C.cat.slice(0, 3), other: C.other });
  },
  darkLayout(extra = {}) {
    const D = SF.D;
    const axis = { gridcolor: D.grid, linecolor: D.axis, zerolinecolor: D.axis, tickfont: { size: 10, color: D.muted },
                   title: { font: { size: 10, color: D.muted } }, automargin: true };
    return Object.assign({
      paper_bgcolor: D.bg, plot_bgcolor: D.bg, height: 150,
      font: { family: "Inconsolata, ui-monospace, Menlo, monospace", size: 10, color: D.ink2 },
      margin: { l: 34, r: 10, t: 10, b: 26 }, showlegend: false,
      hoverlabel: { bgcolor: D.hover, bordercolor: D.axis, font: { color: D.ink, size: 11 } },
      xaxis: { ...axis }, yaxis: { ...axis },
    }, extra);
  },
  miniConfig: { displayModeBar: false, responsive: true },
  config(name) {
    return { displaylogo: false, responsive: true,
             modeBarButtons: [["toImage"]],
             toImageButtonOptions: { filename: `${name}_${new Date().toISOString().slice(0, 10)}`, scale: 2 } };
  },
  nav(current) {
    const H = window.NAV_STATUS || {};
    const items = [["00-overview.html", "Daten", null], ["00-hypothesen.html", "Hypothesen", null], ["01-h1.html", "H1", H.H1], ["02-h2.html", "H2", H.H2],
                   ["03-h3.html", "H3", H.H3], ["04-h4.html", "H4", H.H4], ["05-h5.html", "H5", H.H5], ["#quality", "Datenqualität", null]];
    const link = ([href, label, v]) => {
      const dot = v ? `<span class="dot ${SF.verdicts[v].cls}" aria-label="${SF.verdicts[v].label}"></span>` : "";
      return `<a class="nav-link" href="${href}" ${label === current ? 'aria-current="page"' : ""}>${dot}${label}</a>`;
    };
    return `
    <header class="navy-scope sticky top-0 z-40 border-b" style="background:var(--nav-bg);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-color:var(--border)">
      <div class="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-3">
        <a href="00-overview.html" class="flex items-center gap-2 font-bold text-ink no-underline"><span class="brand-mark">+</span><span class="display text-lg">SwissFlow&nbsp;VA</span></a>
        <nav class="hidden lg:flex items-center gap-1 ml-4" aria-label="Seiten">${items.map(link).join("")}</nav>
        <span class="ml-auto hidden md:inline text-xs" style="color:var(--muted)">Daten bis 30.09.2026</span>
        ${SF.themePicker()}
        <button class="lg:hidden ml-auto icon-btn" aria-label="Menü" aria-expanded="false"
          onclick="const m=document.getElementById('mnav');m.hidden=!m.hidden;this.setAttribute('aria-expanded',!m.hidden)">☰</button>
      </div>
      <nav id="mnav" hidden class="navy-scope lg:hidden border-t px-4 py-2 flex flex-col" style="border-color:var(--border)">${items.map(link).join("")}</nav>
    </header>`;
  },
  // Prototype only: switch colour theme (theme.js); not part of the app
  themePicker() {
    const T = window.SF_THEME;
    if (!T) return "";
    const opts = T.list.map((t) => `<option value="${t.id}" ${t.id === T.current ? "selected" : ""}>${t.label}</option>`).join("");
    return `<label class="hidden md:inline-flex items-center gap-1 text-xs" style="color:var(--muted)">Farbschema
      <select class="input" style="width:auto;min-height:28px;padding:2px 6px" onchange="SF_THEME.set(this.value)">${opts}</select></label>`;
  },
  toast(msg, actionLabel, action) {
    document.querySelectorAll(".toast").forEach((t) => t.remove());
    const t = document.createElement("div");
    t.className = "toast"; t.setAttribute("role", "status");
    t.innerHTML = `<span>${msg}</span>${actionLabel ? `<button>${actionLabel}</button>` : ""}`;
    if (actionLabel) t.querySelector("button").onclick = () => { action(); t.remove(); };
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 5000);
  },
  fmtPct: (x, d = 0) => `${(x * 100).toFixed(d)} %`,
  fmtDate: (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; },
};
window.SF = SF;
