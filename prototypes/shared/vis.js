// Visualisation techniques chosen on 06.11.2026 (UI-SPEC §2.9) — one source for the catalogue (10-vis-optionen.html) and the pages.
// Needs app.js (SF), data.js (PROTO), stats.js (Stats) and Plotly; net.js (PROTO_NET) for the station charts (D1, D3, A1, N1, N2, O2).
// Load after theme.js: colours are read from the theme tokens once (SF.C).
/* global SF, Stats, Plotly */
(function () {
  const P = window.PROTO, NET = window.PROTO_NET || { nodes: [], months: {} }, C = SF.C, H1 = P.h1, TOTAL = "Herkunftsland - Total";
  const mobile = () => window.innerWidth < 640;
  const seqScale = C.seq.map((c, i) => [i / (C.seq.length - 1), c]);
  const blueHigh = [[0, C.divPos], [0.5, C.divMid], [1, C.divNeg]];   // positive = blue (Schweiz-dominiert, as on /h1)
  const hexA = (h, a) => { const n = parseInt(h.replace("#", ""), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };
  const L = (extra) => SF.layout(extra);
  const AX = (extra = {}) => ({ ...SF.layout().xaxis, ...extra });
  const HIDE = { showgrid: false, showticklabels: false, zeroline: false, showline: false, ticks: "" };
  const cfg = (id) => SF.config(`Option_${id}`);
  const sfx = (i) => (i > 1 ? i : "");
  function gridAxes(n, xo = {}, yo = {}) {
    const o = {};
    for (let i = 1; i <= n; i++) { o[`xaxis${sfx(i)}`] = AX(typeof xo === "function" ? xo(i) : xo); o[`yaxis${sfx(i)}`] = AX(typeof yo === "function" ? yo(i) : yo); }
    return o;
  }
  const ptitle = (i, text, color = C.ink2) => ({ text, xref: `x${sfx(i)} domain`, yref: `y${sfx(i)} domain`, x: 0, y: 1.02, xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 11, color } });
  function months(from, to) {
    const out = []; let [y, m] = from.split("-").map(Number); const [ty, tm] = to.split("-").map(Number);
    while (y < ty || (y === ty && m <= tm)) { out.push(`${y}-${String(m).padStart(2, "0")}`); if (++m > 12) { m = 1; y++; } }
    return out;
  }
  const MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const mlab = (ym) => `${MON[+ym.slice(5) - 1]} ${ym.slice(2, 4)}`;
  const isWinter = (ym) => [11, 12, 1, 2, 3, 4].includes(+ym.slice(5));

  const REGN = P.dash.regions;
  const ABBR = { 1: "GR", 2: "OST", 3: "ZH", 4: "LU", 5: "BS", 6: "BE", 8: "JU", 9: "VD", 10: "GE", 11: "VS", 12: "TI", 13: "FR", 14: "AG" };
  const SHORTN = (c) => REGN[c].replace(" / Vierwaldstättersee", "").replace(" Region", "").replace(" und Solothurn", "/SO").replace(" & Drei-Seen-Land", "/3-Seen");
  const ORDER = ["10", "9", "13", "8", "5", "14", "6", "11", "4", "3", "2", "12", "1"];   // roughly west → east
  // tile grid: [column, row] ≈ geographic position (Folie 23)
  const TILE = { 8: [1, 0], 5: [2, 0], 14: [3, 0], 3: [4, 0], 2: [5, 0], 9: [0, 1], 13: [1, 1], 6: [2, 1], 4: [3, 1], 1: [5, 1], 10: [0, 2], 11: [2, 2], 12: [4, 2] };
  const STATIONS = NET.nodes.map((r, i) => ({ i, name: r[1], lat: r[2], lon: r[3], reg: r[4], alt: r[5] || 0, spd: r[6] }));
  const realShare = (ym) => { const m = new Map(); (NET.months[ym] || []).forEach(([i, n, na, late]) => { if (na >= 50) m.set(i, late / na); }); return m; };

  /* ------------------------------------------------------------------ charts ------------------------------------------------------------------ */

  // D1 — pixel matrix stations × days (sample daily values; real station list and base level from Ist-Daten 01/2025)
  function drawD1(el, s) {
    const CTX = P.dash.ctx_days, days = CTX.map((d) => d.date), loaded = new Set(["2025-01", "2026-09"]);
    const all = STATIONS.filter((x) => x.spd >= 300 && ORDER.includes(x.reg)).sort((a, b) => ORDER.indexOf(a.reg) - ORDER.indexOf(b.reg) || b.alt - a.alt);
    const rows = all.filter((_, k) => k % 2 === 0), base = realShare("2025-01"), rnd = Stats.rng(11);
    const bad = days.map(() => (rnd() < 0.022 ? 0.08 + rnd() * 0.1 : 0));
    const snow = days.map((_, k) => Math.max(CTX[k].hn_dav || 0, k ? CTX[k - 1].hn_dav || 0 : 0));
    const wk = days.map((d) => ([0, 6].includes(new Date(`${d}T12:00:00Z`).getUTCDay()) ? -0.035 : 0));
    const seen = new Map();
    const names = rows.map((r) => { const c = (seen.get(r.name) || 0) + 1; seen.set(r.name, c); return c > 1 ? `${r.name} (${c})` : r.name; });
    const z = rows.map((r) => {
      const b0 = base.get(r.i) ?? 0.1, mtn = (r.alt > 900 ? (r.alt - 900) / 1100 : 0) + (["1", "11"].includes(r.reg) ? 0.35 : 0);
      return days.map((d, k) => {
        const v = Math.max(0, Math.min(0.6, b0 + wk[k] + bad[k] + (snow[k] >= 5 ? 0.13 * mtn * Math.min(2, snow[k] / 10) : 0) + (rnd() - 0.5) * 0.05));
        return s.mode === "today" && !loaded.has(d.slice(0, 7)) ? null : v;
      });
    });
    const tickv = [], tickt = [], shapes = [];
    ORDER.forEach((c) => {
      const idx = rows.map((r, k) => (r.reg === c ? k : -1)).filter((k) => k >= 0);
      if (!idx.length) return;
      tickv.push(names[idx[Math.floor(idx.length / 2)]]); tickt.push(ABBR[c]);
      shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: idx[0] - 0.5, y1: idx[0] - 0.5, line: { color: C.axis, width: 1 } });
    });
    Plotly.react(el, [{
      type: "heatmap", x: days, y: names, z, colorscale: seqScale, zmin: 0, zmax: 0.4, hoverongaps: false,
      colorbar: { title: { text: "≥ 3 min", side: "right", font: { size: 11, color: C.ink2 } }, tickformat: ".0%", thickness: 10, len: 0.8, tickfont: { size: 10, color: C.ink2 } },
      hovertemplate: "%{y}<br>%{x|%d.%m.%Y}<br>Anteil ≥ 3 min %{z:.0%}<extra></extra>",
    }], L({ height: mobile() ? 380 : 470, margin: { l: 44, r: 8, t: 8, b: 30 }, plot_bgcolor: C.empty, shapes,
      xaxis: AX({ type: "date", tickformat: "%b %y", showgrid: false }),
      yaxis: AX({ type: "category", tickvals: tickv, ticktext: tickt, autorange: "reversed", showgrid: false, tickfont: { size: 10, color: C.ink2 } }) }), cfg("D1"));
  }

  // D2 — brushing & linking: real HESTA nights (CH) and real fresh-snow days (CH) per month
  function drawD2(el) {
    const ms = months("2025-01", "2026-07");
    const nights = ms.map((m) => P.dash.nights_month.find((r) => r.reg === "8100" && r.month === m)?.nights ?? null);
    const snow = ms.map((m) => P.dash.snow_month.find((r) => r.reg === "CH" && r.month === m)?.snow_days ?? null);
    el.innerHTML = `<div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_200px]"><div class="min-w-0"><div class="d2a"></div><div class="d2b"></div></div>
      <div class="card p-3 self-start" style="background:var(--surface-2)"><div class="section-title mb-2">Auswahl</div><div class="d2k text-sm grid gap-2"></div></div></div>`;
    const a = el.querySelector(".d2a"), b = el.querySelector(".d2b"), k = el.querySelector(".d2k");
    const bar = (y, col, ht) => ({ type: "bar", x: ms.map(mlab), y, marker: { color: col }, unselected: { marker: { opacity: 0.22 } }, hovertemplate: ht });
    const lay = (h, title) => L({ height: h, dragmode: "select", selectdirection: "h", margin: { l: 56, r: 8, t: 22, b: 30 }, bargap: 0.25,
      xaxis: AX({ fixedrange: true }), yaxis: AX({ fixedrange: true }),
      annotations: [{ text: title, xref: "paper", yref: "paper", x: 0, y: 1.08, xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 11, color: C.ink2 } }] });
    Plotly.react(a, [bar(nights, C.seq[3], "%{x}: %{y:,.0f} Logiernächte<extra></extra>")], lay(180, "Logiernächte Schweiz pro Monat"), { ...cfg("D2"), modeBarButtons: [["select2d", "toImage"]] });
    Plotly.react(b, [bar(snow, C.seq[5], "%{x}: %{y:.1f} Neuschneetage<extra></extra>")], lay(150, "Ø Neuschneetage pro Station (ΔHS ≥ 5 cm)"), { ...cfg("D2b"), modeBarButtons: [["select2d"]] });
    const kpi = (idx) => {
      const ii = idx ?? ms.map((_, i) => i), sum = ii.reduce((t, i) => t + (nights[i] || 0), 0), sn = ii.reduce((t, i) => t + (snow[i] || 0), 0);
      k.innerHTML = `<div><span class="num text-xl font-bold">${(sum / 1e6).toFixed(1)} Mio</span><div class="text-xs text-ink2">Logiernächte</div></div>
        <div><span class="num text-xl font-bold">${sn.toFixed(1)}</span><div class="text-xs text-ink2">Neuschneetage (Summe)</div></div>
        <div class="text-xs text-ink2">${idx ? `${mlab(ms[ii[0]])} – ${mlab(ms[ii[ii.length - 1]])} · ${ii.length} Monate` : "ganzer Zeitraum · Rechteck ziehen"}</div>`;
    };
    const link = (ev) => {
      const idx = ev && ev.points && ev.points.length ? [...new Set(ev.points.map((p) => p.pointIndex))].sort((x, y) => x - y) : null;
      [a, b].forEach((g) => Plotly.restyle(g, { selectedpoints: [idx] }));
      kpi(idx);
    };
    [a, b].forEach((g) => { g.on("plotly_selected", link); g.on("plotly_deselect", () => link(null)); });
    kpi(null);
  }

  // D3 — small-multiple maps: real 01/2025 and 09/2026, other months SAMPLE derived from 01/2025
  function drawD3(el) {
    const st = STATIONS.filter((x) => x.spd >= 300), r25 = realShare("2025-01"), r26 = realShare("2026-09"), rnd = Stats.rng(5);
    const panels = [["2025-01", "echt"], ["2025-04", "Beispiel"], ["2025-07", "Beispiel"], ["2025-10", "Beispiel"], ["2026-01", "Beispiel"], ["2026-09", "echt"]];
    const shift = { "2025-04": -0.02, "2025-07": 0.005, "2025-10": -0.025, "2026-01": 0.01 };
    const cols = mobile() ? 2 : 3, rowsN = Math.ceil(panels.length / cols), traces = [], ann = [];
    const CLS = [["pünktlicher", C.divNeg], ["ähnlich (± 2 pp)", C.muted], ["unpünktlicher", C.divPos]];
    panels.forEach(([ym, kind], p) => {
      const i = p + 1, vals = new Map();
      st.forEach((x) => {
        if (ym === "2026-09") { if (r26.has(x.i)) vals.set(x.i, r26.get(x.i)); return; }
        const b0 = r25.get(x.i); if (b0 === undefined) return;
        if (ym === "2025-01") { vals.set(x.i, b0); return; }
        const mtn = x.alt > 900 ? 1 : 0, sum = ["2025-07"].includes(ym) && ["4", "6", "11"].includes(x.reg) ? 0.03 : 0;
        vals.set(x.i, Math.max(0, b0 + shift[ym] + (ym === "2026-01" ? 0.05 * mtn : -0.02 * mtn) + sum + (rnd() - 0.5) * 0.05));
      });
      const mean = Stats.mean([...vals.values()]);
      const by = [[], [], []]; st.forEach((x) => { if (!vals.has(x.i)) return; const d = vals.get(x.i) - mean; by[d <= -0.02 ? 0 : d >= 0.02 ? 2 : 1].push(x); });
      by.forEach((arr, c) => traces.push({ type: "scatter", mode: "markers", x: arr.map((x) => x.lon), y: arr.map((x) => x.lat), xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`,
        name: CLS[c][0], legendgroup: CLS[c][0], showlegend: p === 0, marker: { size: 3.5, color: CLS[c][1] }, text: arr.map((x) => x.name),
        hovertemplate: `%{text}<br>${mlab(ym)}: ${CLS[c][0]}<extra></extra>` }));
      ann.push(ptitle(i, `${mlab(ym)} · ${kind}`, kind === "echt" ? C.ink : C.muted));
    });
    const ax = gridAxes(panels.length, { ...HIDE, range: [5.9, 10.5] }, (i) => ({ ...HIDE, range: [45.8, 47.85], scaleanchor: `x${sfx(i)}`, scaleratio: 1.46 }));
    Plotly.react(el, traces, L({ ...ax, height: mobile() ? 520 : 440, margin: { l: 4, r: 4, t: 24, b: 4 }, annotations: ann, showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.02, yanchor: "top", font: { size: 11, color: C.ink2 } },
      grid: { rows: rowsN, columns: cols, pattern: "independent", xgap: 0.04, ygap: 0.1 } }), cfg("D3"));
  }

  // D4 — treemap region → origin country (real HESTA, 01/2025–07/2026)
  function drawD4(el) {
    const cells = H1.cells.all, ch = cells["8100"];
    const top = Object.keys(ch).filter((c) => c !== TOTAL).sort((a, b) => ch[b] - ch[a]).slice(0, 5);
    const nice = (c) => ({ "Vereinigte Staaten": "USA", "Vereinigtes Königreich": "UK" }[c] || c);
    const ids = [], labels = [], parents = [], values = [], colors = [];
    ORDER.forEach((r) => {
      const t = cells[r][TOTAL]; ids.push(r); labels.push(SHORTN(r)); parents.push(""); values.push(t); colors.push(C.grid);
      let rest = t;
      top.forEach((c, k) => { const v = cells[r][c] || 0; rest -= v; ids.push(`${r}|${c}`); labels.push(nice(c)); parents.push(r); values.push(v); colors.push(C.cat[k]); });
      ids.push(`${r}|rest`); labels.push("Übrige"); parents.push(r); values.push(Math.max(0, rest)); colors.push(C.other);
    });
    Plotly.react(el, [{ type: "treemap", ids, labels, parents, values, branchvalues: "total", marker: { colors, line: { color: C.surface, width: 2 } },
      textinfo: "label+percent parent", textfont: { color: C.ink, size: 12 }, tiling: { pad: 2 }, pathbar: { visible: true, textfont: { color: C.ink2 } },
      hovertemplate: "%{label}<br>%{value:,.0f} Logiernächte<br>%{percentParent:.0%} der Region<extra></extra>" }],
    L({ height: mobile() ? 420 : 460, margin: { l: 4, r: 4, t: 28, b: 4 } }), cfg("D4"));
  }

  // D5 — hour profile region × hour, small multiples by month (SAMPLE: real aggregate is station × month × hour)
  function drawD5(el) {
    const hrs = Array.from({ length: 19 }, (_, i) => i + 5), panels = ["2025-01", "2025-04", "2025-07", "2025-10"], rnd = Stats.rng(3);
    const pk = (h, c, w) => Math.exp(-((h - c) ** 2) / (2 * w * w));
    const cols = mobile() ? 2 : 4, traces = panels.map((ym, p) => {
      const wint = isWinter(ym), sum = ym === "2025-07";
      const z = ORDER.map((r) => hrs.map((h) => {
        const mtn = ["1", "11"].includes(r), tour = ["4", "6", "11"].includes(r), city = ["3", "10", "5"].includes(r);
        return Math.max(0, 0.05 + 0.06 * pk(h, 7.5, 1.1) * (city ? 1.6 : 1) + 0.08 * pk(h, 17.5, 1.4) * (city ? 1.4 : 1)
          + (wint && mtn ? 0.12 * pk(h, 16.5, 1) : 0) + (sum && tour ? 0.06 * pk(h, 15, 2) : 0) + (rnd() - 0.5) * 0.02);
      }));
      return { type: "heatmap", x: hrs, y: ORDER.map((r) => ABBR[r]), z, coloraxis: "coloraxis", xaxis: `x${sfx(p + 1)}`, yaxis: `y${sfx(p + 1)}`, xgap: 1, ygap: 1,
        hovertemplate: `${mlab(ym)} · %{y} · %{x}:00<br>Anteil ≥ 3 min %{z:.0%}<extra></extra>` };
    });
    const ax = gridAxes(panels.length, { showgrid: false, tickvals: [6, 9, 12, 15, 18, 21], ticksuffix: "h" }, (i) => ({ showgrid: false, matches: "y", showticklabels: i === 1 || (mobile() && i === 3) }));
    Plotly.react(el, traces, L({ ...ax, height: mobile() ? 520 : 330, margin: { l: 40, r: 8, t: 24, b: 30 }, annotations: panels.map((ym, p) => ptitle(p + 1, mlab(ym))),
      coloraxis: { colorscale: seqScale, cmin: 0, cmax: 0.3, colorbar: { tickformat: ".0%", thickness: 10, tickfont: { size: 10, color: C.ink2 } } },
      grid: { rows: panels.length / cols, columns: cols, pattern: "independent", xgap: 0.05, ygap: 0.14 } }), cfg("D5"));
  }

  /* ---- H1 PCA, recomputed from real HESTA cells (same as 01-h1.html) ---- */
  const REGIONS = Object.keys(H1.names).filter((c) => c !== "8100").sort((a, b) => +a - +b);
  const GROUPS = { 1: "s", 11: "s", 2: "s", 4: "i", 10: "i", 3: "i" };
  function pcaFor(period, topN = 15, regions = REGIONS) {
    const cells = H1.cells[period], ch = cells["8100"];
    const top = Object.keys(ch).filter((c) => c !== TOTAL).sort((a, b) => ch[b] - ch[a]).slice(0, topN), cols = [...top, "Übrige"];
    const M = regions.map((a) => { const t = cells[a][TOTAL], row = top.map((c) => (cells[a][c] || 0) / t); return [...row, 1 - row.reduce((s, x) => s + x, 0)]; });
    const mu = cols.map((_, j) => Stats.mean(M.map((r) => r[j]))), sd = cols.map((_, j) => Stats.std(M.map((r) => r[j])) || 1);
    const res = Stats.pca(M.map((r) => r.map((x, j) => (x - mu[j]) / sd[j])), 2), iCH = cols.indexOf("Schweiz");
    if (res.comps[0][iCH] < 0) { res.comps[0] = res.comps[0].map((x) => -x); res.scores.forEach((s) => { s[0] = -s[0]; }); }
    return { regions, ...res };
  }
  const groupOk = (pc) => pc.regions.every((a, i) => !GROUPS[a] || (GROUPS[a] === "s") === (pc.scores[i][0] > 0));
  const GSTYLE = { s: [C.cat[0], "circle", "Schweiz-dominiert"], i: [C.cat[1], "diamond", "international"], "-": [C.other, "circle", "übrige"] };

  // SPLOM as a lower-triangle grid of SVG scatter plots (Plotly's splom needs WebGL). Row r = dims[r + 1] on y, column c = dims[c] on x.
  // groups: [{ name, color, symbol, rows, text: (row) => string }]
  function splomSvg(el, id, dims, groups, height) {
    const k = dims.length - 1, traces = [], ax = {};
    for (let r = 0; r < k; r++) for (let c = 0; c < k; c++) {
      const i = r * k + c + 1, on = c <= r, xd = dims[c], yd = dims[r + 1];
      ax[`xaxis${sfx(i)}`] = on ? AX({ tickfont: { size: 9, color: C.ink2 }, nticks: 4, showticklabels: r === k - 1, title: r === k - 1 ? { text: xd.label, font: { size: 10, color: C.ink2 } } : undefined }) : { visible: false };
      ax[`yaxis${sfx(i)}`] = on ? AX({ tickfont: { size: 9, color: C.ink2 }, nticks: 4, showticklabels: c === 0, title: c === 0 ? { text: yd.label, font: { size: 10, color: C.ink2 } } : undefined }) : { visible: false };
      if (!on) continue;
      groups.forEach((g, gi) => traces.push({ type: "scatter", mode: "markers", xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`, name: g.name, legendgroup: g.name, showlegend: i === 1,
        x: g.rows.map(xd.get), y: g.rows.map(yd.get), text: g.rows.map(g.text),
        marker: { color: g.color, symbol: g.symbol, size: g.size || 6, opacity: 0.9, line: { color: C.surface, width: 1 } },
        hovertemplate: `%{text}<br>${xd.label}: %{x:.2f}<br>${yd.label}: %{y:.2f}<extra></extra>` }));
    }
    Plotly.react(el, traces, L({ ...ax, height, margin: { l: 56, r: 8, t: 8, b: 48 }, showlegend: true,
      legend: { orientation: "v", x: 0.62, y: 1, xanchor: "left", font: { size: 11, color: C.ink2 } },
      grid: { rows: k, columns: k, pattern: "independent", xgap: 0.04, ygap: 0.05 } }), cfg(id));
  }

  // P1 — stability as small multiples (15 real PCA runs)
  function drawP1(el) {
    const runs = [["2025", "2025", REGIONS], ["2026", "2026 (01–07)", REGIONS], ...REGIONS.map((d) => ["all", `ohne ${ABBR[d]}`, REGIONS.filter((r) => r !== d)])];
    const cols = mobile() ? 3 : 5, traces = [], ann = [];
    runs.forEach(([per, label, regs], p) => {
      const i = p + 1, pc = pcaFor(per, 15, regs), ok = groupOk(pc);
      Object.entries(GSTYLE).forEach(([g, [col, sym, name]]) => {
        const k = pc.regions.map((a, j) => ((GROUPS[a] || "-") === g ? j : -1)).filter((j) => j >= 0);
        traces.push({ type: "scatter", mode: "markers", x: k.map((j) => pc.scores[j][0]), y: k.map((j) => pc.scores[j][1]), xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`,
          name, legendgroup: g, showlegend: p === 0, marker: { color: col, symbol: sym, size: g === "-" ? 5 : 7, line: { color: C.surface, width: 1 } },
          text: k.map((j) => REGN[pc.regions[j]]), hovertemplate: `%{text}<br>${label}: PC1 %{x:.2f}<extra></extra>` });
      });
      const w = pc.regions.indexOf("11");
      if (w >= 0) traces.push({ type: "scatter", mode: "markers+text", x: [pc.scores[w][0]], y: [pc.scores[w][1]], xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`, showlegend: false,
        text: ["VS"], textposition: "top center", textfont: { size: 10, color: C.accent }, hoverinfo: "skip", marker: { size: 14, color: "rgba(0,0,0,0)", line: { color: C.accent, width: 1.5 } } });
      ann.push(ptitle(i, `${label} ${ok ? "✓" : "✕"}`, ok ? C.ink : C.divPos));
    });
    const ax = gridAxes(runs.length, { ...HIDE, zeroline: true, zerolinecolor: C.axis }, { ...HIDE });
    Plotly.react(el, traces, L({ ...ax, height: mobile() ? 640 : 470, margin: { l: 6, r: 6, t: 22, b: 6 }, annotations: ann, showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.01, yanchor: "top", font: { size: 11, color: C.ink2 } },
      grid: { rows: Math.ceil(runs.length / cols), columns: cols, pattern: "independent", xgap: 0.03, ygap: 0.12 } }), cfg("P1"));
  }

  // P2 — SPLOM of the 6 largest source-market shares, 13 regions (real HESTA)
  function drawP2(el) {
    const cells = H1.cells.all, ch = cells["8100"];
    const top = Object.keys(ch).filter((c) => c !== TOTAL).sort((a, b) => ch[b] - ch[a]).slice(0, mobile() ? 4 : 6);
    const nice = (c) => ({ "Vereinigte Staaten": "USA", "Vereinigtes Königreich": "UK" }[c] || c);
    const dims = top.map((c) => ({ label: `${nice(c)} %`, get: (a) => (cells[a][c] || 0) / cells[a][TOTAL] * 100 }));
    const groups = Object.entries(GSTYLE).map(([g, [color, symbol, name]]) => ({ name, color, symbol, size: 7, rows: REGIONS.filter((a) => (GROUPS[a] || "-") === g), text: (a) => REGN[a] }));
    splomSvg(el, "P2", dims, groups, mobile() ? 420 : 560);
  }

  // tile-grid helper (P3, S1)
  function tileTrace(vals, i, size, extra = {}) {
    const codes = Object.keys(TILE);
    return { type: "scatter", mode: "markers+text", x: codes.map((c) => TILE[c][0]), y: codes.map((c) => -TILE[c][1]), xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`,
      marker: { symbol: "square", size, color: codes.map((c) => vals[c]), line: { color: C.surface, width: 2 } }, cliponaxis: false, showlegend: false, ...extra, _codes: codes };
  }
  const tileAxes = (n) => gridAxes(n, { ...HIDE, range: [-0.6, 5.6], fixedrange: true }, { ...HIDE, range: [-2.6, 0.6], fixedrange: true });

  // P3 — PC1 on a tile map (real)
  function drawP3(el) {
    const sc = Object.fromEntries(H1.scores.map((s) => [s.code, s.pc1])), size = Math.min(70, (el.clientWidth - 30) / 6.6);
    const t = tileTrace(sc, 1, size);
    const wrong = (c) => GROUPS[c] && (GROUPS[c] === "s") !== (sc[c] > 0);
    t.marker = { ...t.marker, colorscale: blueHigh, cmid: 0, colorbar: { title: { text: "PC1", font: { size: 11, color: C.ink2 } }, thickness: 10, tickfont: { size: 10, color: C.ink2 } },
      line: { color: t._codes.map((c) => (wrong(c) ? C.accent : C.surface)), width: t._codes.map((c) => (wrong(c) ? 3 : 2)) } };
    t.text = t._codes.map((c) => `<b>${ABBR[c]}</b><br>${sc[c] > 0 ? "+" : ""}${sc[c].toFixed(1)}${GROUPS[c] ? `<br>${GROUPS[c] === "s" ? "erw. CH" : "erw. Int."}` : ""}`);
    t.textfont = { size: size > 50 ? 11 : 9, color: C.ink };
    t.hovertext = t._codes.map((c) => `${REGN[c]}<br>PC1 ${sc[c].toFixed(2)}${wrong(c) ? "<br>falsche Seite!" : ""}`);
    t.hovertemplate = "%{hovertext}<extra></extra>";
    Plotly.react(el, [t], L({ ...tileAxes(1), height: Math.max(240, size * 3.4 + 40), margin: { l: 4, r: 4, t: 8, b: 8 } }), cfg("P3"));
  }

  // S1 — LQ tile maps 3 countries × 2 seasons (real HESTA)
  function drawS1(el) {
    const CN = [["China", "China"], ["Deutschland", "Deutschland"], ["Vereinigtes Königreich", "Grossbritannien"]], SE = [["S2025", "Sommer 2025"], ["W2025/26", "Winter 2025/26"]];
    const NAMED = { "S2025|China": ["4", "6"], "W2025/26|Deutschland": ["1", "11"], "W2025/26|Vereinigtes Königreich": ["1", "11"] };
    const cols = mobile() ? 1 : 3, pw = (el.clientWidth - 20) / cols, size = Math.min(48, pw / 6.8), traces = [], ann = [];
    let i = 0;
    SE.forEach(([s, sl]) => CN.forEach(([c, cl]) => {
      i++;
      const lq = {}; P.h2.shares.filter((r) => r.season === s && r.country === c).forEach((r) => { lq[r.code] = r.lq; });
      const named = NAMED[`${s}|${c}`] || [], t = tileTrace(Object.fromEntries(Object.entries(lq).map(([k, v]) => [k, Math.log2(Math.max(0.05, v))])), i, size);
      t.marker = { ...t.marker, coloraxis: "coloraxis", line: { color: t._codes.map((k) => (named.includes(k) ? C.accent : C.surface)), width: t._codes.map((k) => (named.includes(k) ? 3 : 2)) } };
      t.text = t._codes.map((k) => (named.includes(k) ? `<b>${ABBR[k]}</b><br>${lq[k].toFixed(2)}` : ABBR[k]));
      t.textfont = { size: 9, color: t._codes.map((k) => (lq[k] < 0.8 ? C.surface : C.ink)) };
      t.hovertext = t._codes.map((k) => `${REGN[k]}<br>${cl}, ${sl}<br>LQ ${lq[k].toFixed(2)}`); t.hovertemplate = "%{hovertext}<extra></extra>";
      traces.push(t); ann.push(ptitle(i, `${cl} · ${sl}`, named.length ? C.ink : C.ink2));
    }));
    Plotly.react(el, traces, L({ ...tileAxes(6), height: mobile() ? 6 * (size * 3.4 + 30) : 2 * (size * 3.4 + 34) + 30, margin: { l: 4, r: 4, t: 22, b: 8 }, annotations: ann,
      // as on /h2: light = low LQ, dark = high LQ (UI-SPEC §2.4)
      coloraxis: { colorscale: [...C.seq].reverse().map((c, j) => [j / (C.seq.length - 1), c]), cmin: Math.log2(0.35), cmax: Math.log2(2.8),
        colorbar: { title: { text: "LQ", font: { size: 11, color: C.ink2 } }, tickvals: [-1, 0, 1], ticktext: ["0.5", "1", "2"], thickness: 10, tickfont: { size: 10, color: C.ink2 } } },
      grid: { rows: 6 / cols, columns: cols, pattern: "independent", xgap: 0.04, ygap: 0.12 } }), cfg("S1"));
  }

  // S2 — interleaved flow graph origin country → region per month (real HESTA monthly nights)
  function drawS2(el, s) {
    const ms = months("2025-01", "2026-07"), CN = [["China", "China", 10.5], ["Deutschland", "Deutschland", 6], ["Vereinigtes Königreich", "Grossbritannien", 1.5]];
    const V = {}; for (const [ym, a, c, v] of P.h2.monthly_all) V[`${ym}|${a}|${c}`] = v;
    const span = s.layout === "inter" ? 2.6 : 0.72, W = [0.6, 1.3, 2.4, 4], OP = s.layout === "inter" ? [0.12, 0.22, 0.38, 0.6] : [0.25, 0.4, 0.6, 0.85];
    // edge weight = share of the country's guests that month going to the region (the distribution H2 is about); < 3 % hidden
    const share = (m, r, c) => { const v = V[`${m}|${r}|${c}`]; if (!v) return 0; const t = ORDER.reduce((s2, q) => s2 + (V[`${m}|${q}|${c}`] || 0), 0); return t ? v / t : 0; };
    const q = [0.03, 0.08, 0.15, 0.3];
    const traces = [];
    CN.forEach(([c, cl, yc], ci) => {
      W.forEach((w, b) => {
        const x = [], y = [];
        ms.forEach((m, k) => ORDER.forEach((r, ri) => {
          const v = share(m, r, c); if (v < q[b] || (b < 3 && v >= q[b + 1])) return;
          x.push(k, k + span, null); y.push(yc, ri, null);
        }));
        traces.push({ type: "scatter", mode: "lines", x, y, line: { color: C.cat[ci], width: w }, opacity: OP[b], hoverinfo: "skip", showlegend: false });
      });
      traces.push({ type: "scatter", mode: "lines", x: [null], y: [null], line: { color: C.cat[ci], width: 3 }, name: cl, showlegend: true });
    });
    const hx = [], hy = [], ht = [];
    ms.forEach((m, k) => CN.forEach(([c, cl]) => ORDER.forEach((r, ri) => { const v = share(m, r, c); if (v >= q[0]) { hx.push(k + span); hy.push(ri); ht.push(`${mlab(m)} · ${cl} → ${SHORTN(r)}: ${Math.round(v * 100)} % der Gäste`); } })));
    traces.push({ type: "scatter", mode: "markers", x: hx, y: hy, text: ht, marker: { size: 6, color: "rgba(0,0,0,0)" }, hovertemplate: "%{text}<extra></extra>", showlegend: false });
    const shapes = ms.map((m, k) => (isWinter(m) ? { type: "rect", xref: "x", yref: "paper", x0: k - 0.15, x1: k + 0.85, y0: 0, y1: 1, fillcolor: C.winter, line: { width: 0 }, layer: "below" } : null)).filter(Boolean);
    const ann = CN.map(([, cl, yc]) => ({ text: { China: "CN", Deutschland: "DE", Grossbritannien: "GB" }[cl], x: -0.05, y: yc, xref: "x", yref: "y", xanchor: "right", showarrow: false, font: { size: 10, color: C.ink2 } }));
    Plotly.react(el, traces, L({ height: mobile() ? 420 : 470, margin: { l: 34, r: 70, t: 30, b: 40 }, shapes, annotations: ann, showlegend: true, hovermode: "closest",
      legend: { orientation: "h", x: 0, y: 1.08, font: { size: 11, color: C.ink2 } },
      xaxis: AX({ tickvals: ms.map((_, k) => k + (s.layout === "inter" ? 0 : span / 2)), ticktext: ms.map(mlab), showgrid: false, range: [-0.4, ms.length - 1 + span + 0.2] }),
      yaxis: AX({ side: "right", tickvals: ORDER.map((_, i) => i), ticktext: ORDER.map((r) => ABBR[r]), showgrid: false, range: [-0.8, 12.8] }) }), cfg("S2"));
  }

  // S3 — horizon graph vs. line chart: nights per month relative to the region's mean (real HESTA)
  function drawS3(el, s) {
    const ms = months("2025-01", "2026-07"), x = ms.map((m) => `${m}-15`);
    const series = ORDER.map((r) => { const v = ms.map((m) => P.dash.nights_month.find((q) => q.reg === r && q.month === m)?.nights ?? null), mu = Stats.mean(v.filter((t) => t !== null)); return v.map((t) => (t === null ? null : t / mu - 1)); });
    if (s.form === "line") {
      Plotly.react(el, series.map((v, i) => ({ type: "scatter", mode: "lines", x, y: v, line: { color: hexA(C.muted, 0.7), width: 1.5 }, name: SHORTN(ORDER[i]),
        hovertemplate: `${SHORTN(ORDER[i])} · %{x|%b %y}: %{y:+.0%}<extra></extra>` })),
      L({ height: 460, margin: { l: 48, r: 8, t: 8, b: 30 }, xaxis: AX({ type: "date", tickformat: "%b %y" }), yaxis: AX({ tickformat: "+.0%", title: { text: "vs. Mittel der Region" } }) }), cfg("S3"));
      return;
    }
    const b = 0.4, n = series.length, gap = 0.012, traces = [];
    const lay = { height: 460, margin: { l: 90, r: 8, t: 8, b: 30 }, hovermode: "x", xaxis: AX({ type: "date", tickformat: "%b %y", anchor: `y${sfx(n)}`, showgrid: false }), annotations: [] };
    const cl = (v) => Math.max(0, Math.min(b, v));
    const POS = [C.seq[2], C.seq[5]], NEG = [hexA(C.divPos, 0.55), C.divPos];
    series.forEach((v, i) => {
      const ya = `y${sfx(i + 1)}`, top = 1 - i / n, bot = 1 - (i + 1) / n + gap;
      lay[`yaxis${sfx(i + 1)}`] = { domain: [bot, top], range: [0, b], visible: false, fixedrange: true };
      [0, 1].forEach((k) => {
        traces.push({ type: "scatter", mode: "lines", x, y: v.map((t) => (t === null ? null : cl(t - k * b))), yaxis: ya, fill: "tozeroy", fillcolor: POS[k], line: { width: 0, shape: "spline" }, hoverinfo: "skip" });
        traces.push({ type: "scatter", mode: "lines", x, y: v.map((t) => (t === null ? null : cl(-t - k * b))), yaxis: ya, fill: "tozeroy", fillcolor: NEG[k], line: { width: 0, shape: "spline" }, hoverinfo: "skip" });
      });
      traces.push({ type: "scatter", mode: "lines", x, y: v.map(() => b / 2), yaxis: ya, line: { width: 0, color: "rgba(0,0,0,0)" }, customdata: v, hovertemplate: `${ABBR[ORDER[i]]} %{customdata:+.0%}<extra></extra>` });
      lay.annotations.push({ text: SHORTN(ORDER[i]), xref: "paper", yref: "paper", x: -0.01, y: (top + bot) / 2, xanchor: "right", showarrow: false, font: { size: 10, color: C.ink2 } });
    });
    Plotly.react(el, traces, L(lay), cfg("S3"));
  }

  // A1 — pixel matrix GR stations × winter days, aligned with real Davos ΔHS (delays SAMPLE)
  function drawA1(el) {
    const days = P.h3.days, dates = days.map((d) => d.date), base = realShare("2025-01"), rnd = Stats.rng(21);
    const gr = STATIONS.filter((x) => x.reg === "1" && x.spd >= 40).sort((a, b) => b.alt - a.alt), step = Math.max(1, Math.ceil(gr.length / 140)), rows = gr.filter((_, k) => k % step === 0);
    const mshare = Stats.mean(days.map((d) => d.share));
    const snowD = days.map((d, k) => Math.max(d.hn || 0, k ? days[k - 1].hn || 0 : 0));
    const z = rows.map((r) => { const b0 = (base.get(r.i) ?? 0.15) * 0.8, af = Math.max(0, (r.alt - 600) / 1400);
      return days.map((d, k) => Math.max(0, Math.min(0.7, b0 + (snowD[k] >= 5 ? 0.16 * af + 0.04 : 0) + (d.share - mshare) * 0.45 + (rnd() - 0.5) * 0.08))); });
    const heavy = days.filter((d) => d.share >= 0.5).map((d) => d.date), hmax = Math.max(...days.map((d) => d.hn || 0));
    const text = rows.map((r) => dates.map(() => `${r.name} · ${r.alt} m`));
    const tv = [], tt = []; rows.forEach((r, k) => { if (k % Math.ceil(rows.length / 6) === 0) { tv.push(k); tt.push(`${r.alt} m`); } });
    el.innerHTML = `<div class="a1c"></div><p class="detail a1d mt-1">Klick auf einen Tag → stärkste Stationen</p>`;
    const g = el.querySelector(".a1c"), det = el.querySelector(".a1d");
    Plotly.react(g, [
      { type: "bar", x: dates, y: days.map((d) => d.hn), yaxis: "y2", marker: { color: days.map((d) => ((d.hn || 0) >= 5 ? C.seq[3] : C.seq[1])) }, hovertemplate: "%{x|%d.%m.%Y}: ΔHS Davos %{y} cm<extra></extra>" },
      { type: "scatter", mode: "markers", x: heavy, y: heavy.map(() => hmax * 1.12), yaxis: "y2", marker: { symbol: "triangle-down", size: 7, color: C.accent }, hovertemplate: "%{x|%d.%m.%Y}: Starkverspätungstag<extra></extra>" },
      { type: "heatmap", x: dates, y: rows.map((_, k) => k), z, text, colorscale: seqScale, zmin: 0, zmax: 0.5, hovertemplate: "%{text}<br>%{x|%d.%m.%Y}: %{z:.0%} ≥ 3 min<extra></extra>",
        colorbar: { tickformat: ".0%", thickness: 10, len: 0.75, y: 0.4, tickfont: { size: 10, color: C.ink2 } } },
    ], L({ height: mobile() ? 420 : 480, margin: { l: 52, r: 8, t: 8, b: 30 }, bargap: 0.1,
      xaxis: AX({ type: "date", tickformat: "%d.%m.", showgrid: false }),
      yaxis: AX({ domain: [0, 0.8], tickvals: tv, ticktext: tt, autorange: "reversed", showgrid: false }),
      yaxis2: AX({ domain: [0.84, 1], title: { text: "ΔHS cm", font: { size: 10, color: C.ink2 } }, rangemode: "tozero", showgrid: false }) }), cfg("A1"));
    g.on("plotly_click", (ev) => {
      const d = ev.points[0].x.slice(0, 10), k = dates.indexOf(d); if (k < 0) return;
      const best = rows.map((r, j) => [r, z[j][k]]).sort((a, b) => b[1] - a[1]).slice(0, 5);
      det.textContent = `${SF.fmtDate(d)} · ΔHS ${days[k].hn ?? "–"} cm · ${heavy.includes(d) ? "Starkverspätungstag · " : ""}Top: ${best.map(([r, v]) => `${r.name} ${Math.round(v * 100)} %`).join(", ")}`;
    });
  }

  // A2 — overview + detail via range slider (share SAMPLE, ΔHS real)
  function drawA2(el) {
    const days = P.h3.days, x = days.map((d) => d.date);
    Plotly.react(el, [
      { type: "scatter", mode: "lines", x, y: days.map((d) => d.share), line: { color: C.cat[0], width: 2 }, name: "Anteil Stationen", hovertemplate: "%{x|%d.%m.%Y}: %{y:.0%}<extra></extra>" },
      { type: "scatter", mode: "markers", x: days.filter((d) => d.share >= 0.5).map((d) => d.date), y: days.filter((d) => d.share >= 0.5).map((d) => d.share), marker: { size: 8, color: C.accent, line: { color: C.surface, width: 2 } }, hoverinfo: "skip" },
    ], L({ height: 300, margin: { l: 48, r: 8, t: 8, b: 20 }, shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.5, y1: 0.5, line: { color: C.ink2, width: 1, dash: "dash" } }],
      xaxis: AX({ type: "date", tickformat: "%d.%m.", range: ["2025-12-01", "2026-01-31"], rangeslider: { visible: true, thickness: 0.14, bgcolor: C.empty, bordercolor: C.axis } }),
      yaxis: AX({ tickformat: ".0%", range: [0, 1], title: { text: "Anteil Stationen" } }) }), cfg("A2"));
  }

  /* ---- mountain stations (real names, altitudes, positions; delays SAMPLE) ---- */
  const MTN = STATIONS.filter((x) => x.alt >= 1000 && x.spd >= 40);
  function mtnSample() {
    const rnd = Stats.rng(9), g = () => { let s = 0; for (let k = 0; k < 6; k++) s += rnd(); return s - 3; };
    return MTN.map((x) => { const nd = 8 + Math.floor(rnd() * 22), mu = 0.5 + (x.alt - 1000) / 2000 + rnd() * 0.3, eff = 0.15 + rnd() * 0.7 * (x.alt / 2000);
      const kein = Array.from({ length: 60 }, () => Math.max(0, mu + g() * 0.35)), neu = Array.from({ length: nd }, () => Math.max(0, mu + eff + g() * 0.5));
      return { ...x, nd, kein, neu, mk: Stats.quantile([...kein].sort((a, b) => a - b), 0.5), mn: Stats.quantile([...neu].sort((a, b) => a - b), 0.5) }; });
  }

  // N1 — small multiples per mountain station, compact boxplots, shared y
  function drawN1(el) {
    // one stop per place (busiest), so the panels show 12 different resorts rather than 12 St. Moritz bus stops
    const place = new Map(); mtnSample().forEach((x) => { const k = x.name.split(/[,(]/)[0].trim(); if (!place.has(k) || place.get(k).spd < x.spd) place.set(k, x); });
    const ms = [...place.values()].sort((a, b) => b.spd - a.spd).slice(0, 12).sort((a, b) => b.alt - a.alt), cols = mobile() ? 2 : 4, traces = [], ann = [];
    const lastRow = (i) => i > ms.length - cols;
    ms.forEach((x, p) => {
      const i = p + 1, ax = { xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}` };
      traces.push({ type: "box", y: x.kein, name: "kein", ...ax, marker: { color: C.muted }, line: { width: 1.5 }, fillcolor: hexA(C.muted, 0.18), boxpoints: false, hovertemplate: "kein Neuschnee<br>Median %{median:.2f} min<extra></extra>" });
      traces.push({ type: "box", y: x.neu, name: "Neuschnee", ...ax, marker: { color: C.cat[0] }, line: { width: 1.5 }, fillcolor: hexA(C.cat[0], 0.28), boxpoints: false, hovertemplate: "Neuschnee<br>Median %{median:.2f} min<extra></extra>" });
      ann.push(ptitle(i, `${x.name.slice(0, 20)} · ${x.alt} m · n=${x.nd}`));
    });
    const axs = gridAxes(ms.length, (i) => ({ showgrid: false, tickfont: { size: 9, color: C.ink2 }, showticklabels: lastRow(i) }),
      (i) => ({ matches: "y", showticklabels: (i - 1) % cols === 0, rangemode: "tozero", title: i === 1 ? { text: "Ø Verspätung (min)", font: { size: 10, color: C.ink2 } } : undefined }));
    Plotly.react(el, traces, L({ ...axs, height: mobile() ? 760 : 520, margin: { l: 44, r: 8, t: 22, b: 24 }, annotations: ann,
      grid: { rows: Math.ceil(ms.length / cols), columns: cols, pattern: "independent", xgap: 0.05, ygap: 0.2 } }), cfg("N1"));
  }

  // N2 — linking box plot ↔ map (click a box → its upper quartile lights up on the map)
  function drawN2(el) {
    const ms = mtnSample(), ctx = STATIONS.filter((x) => x.spd >= 300);
    el.innerHTML = `<div class="grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]"><div class="n2b"></div><div class="n2m min-w-0"></div></div><p class="detail n2d mt-1">Klick auf eine Box → obere 25 % dieser Gruppe werden auf der Karte markiert</p>`;
    const bx = el.querySelector(".n2b"), mp = el.querySelector(".n2m"), det = el.querySelector(".n2d");
    Plotly.react(bx, [
      { type: "box", y: ms.map((x) => x.mk), name: "kein", marker: { color: C.muted }, fillcolor: hexA(C.muted, 0.18), boxpoints: false, hovertemplate: "Median je Station<extra>kein Neuschnee</extra>" },
      { type: "box", y: ms.map((x) => x.mn), name: "Neuschnee", marker: { color: C.cat[0] }, fillcolor: hexA(C.cat[0], 0.28), boxpoints: false, hovertemplate: "Median je Station<extra>Neuschnee</extra>" },
    ], L({ height: 340, margin: { l: 40, r: 8, t: 8, b: 30 }, yaxis: AX({ title: { text: "Median Ø Verspätung (min)" }, rangemode: "tozero" }) }), { ...cfg("N2"), modeBarButtons: [[]] });
    const map = (hi) => Plotly.react(mp, [
      { type: "scatter", mode: "markers", x: ctx.map((x) => x.lon), y: ctx.map((x) => x.lat), marker: { size: 2.5, color: hexA(C.muted, 0.35) }, hoverinfo: "skip" },
      { type: "scatter", mode: "markers", x: ms.map((x) => x.lon), y: ms.map((x) => x.lat), text: ms.map((x) => `${x.name} · ${x.alt} m`),
        marker: { size: ms.map((_, k) => (hi && hi.has(k) ? 9 : 5)), color: ms.map((_, k) => (hi && hi.has(k) ? C.accent : C.seq[3])), line: { color: C.surface, width: 1 } },
        hovertemplate: "%{text}<extra></extra>" },
    ], L({ height: 340, margin: { l: 4, r: 4, t: 8, b: 4 }, xaxis: AX({ ...HIDE, range: [5.9, 10.5] }), yaxis: AX({ ...HIDE, range: [45.8, 47.85], scaleanchor: "x", scaleratio: 1.46 }) }), cfg("N2map"));
    map(null);
    bx.on("plotly_click", (ev) => {
      const key = ev.points[0].curveNumber === 0 ? "mk" : "mn", v = ms.map((x) => x[key]), q3 = Stats.quantile([...v].sort((a, b) => a - b), 0.75);
      const hi = new Set(v.map((t, k) => (t >= q3 ? k : -1)).filter((k) => k >= 0));
      map(hi);
      det.textContent = `${key === "mn" ? "Neuschnee" : "kein Neuschnee"}: ${hi.size} von ${ms.length} Bergstationen im oberen Quartil (≥ ${q3.toFixed(2)} min) – markiert`;
    });
  }

  /* ---- H5 rows: nights real, delay SAMPLE, snow days real (region of the unit), cancellations SAMPLE ---- */
  const UNIT_REG = { GR: "1", Zürich: "3", Bern: "6", Genève: "10", Basel: "5", Luzern: "4", Lausanne: "9", "St. Gallen": "2" };
  const H5 = (() => { const rnd = Stats.rng(4); return P.h5.map((r) => ({ ...r,
    snow: P.dash.snow_month.find((q) => q.reg === UNIT_REG[r.unit] && q.month === r.ym)?.snow_days ?? null,
    cancel: Math.max(0, 0.4 + (r.season === "W" ? 0.25 : 0) * (r.unit === "GR" ? 2 : 1) + (rnd() - 0.5) * 0.3) })); })();
  const SEAS = [["W", "Winter", C.cat[0], "circle"], ["S", "Sommer", C.cat[1], "diamond"]];

  // I1 — SPLOM month × unit
  function drawI1(el) {
    const dims = [["nights", "Logiernächte", (v) => v / 1000], ["delay_min", "Ø Verspätung", (v) => v], ["snow", "Neuschneetage", (v) => v], ["cancel", "Ausfälle %", (v) => v]];
    const groups = SEAS.map(([s, name, color, symbol]) => ({ name, color, symbol, rows: H5.filter((r) => r.season === s), text: (r) => `${r.unit} · ${mlab(r.ym)}` }));
    splomSvg(el, "I1", dims.map(([k, label, f]) => ({ label: k === "nights" ? "Tsd. Logiernächte" : label, get: (r) => (r[k] === null ? null : f(r[k])) })), groups, mobile() ? 420 : 540);
  }

  // I2 — brushing & linking across three scatter plots (GR, Zürich, Bern)
  function drawI2(el) {
    const units = ["GR", "Zürich", "Bern"], data = units.map((u) => H5.filter((r) => r.unit === u)), ymax = Math.max(...H5.map((r) => r.delay_min)) * 1.08;
    el.innerHTML = `<div class="grid gap-2 sm:grid-cols-3">${units.map(() => '<div class="i2 min-w-0"></div>').join("")}</div><p class="detail i2d mt-1">Rechteck in einem Panel ziehen → dieselben Monate leuchten in allen Panels</p>`;
    const divs = [...el.querySelectorAll(".i2")], det = el.querySelector(".i2d");
    divs.forEach((d, j) => Plotly.react(d, [{ type: "scatter", mode: "markers", x: data[j].map((r) => r.nights / 1000), y: data[j].map((r) => r.delay_min), text: data[j].map((r) => mlab(r.ym)),
      marker: { size: 8, color: data[j].map((r) => (r.season === "W" ? C.cat[0] : C.cat[1])), symbol: data[j].map((r) => (r.season === "W" ? "circle" : "diamond")), line: { color: C.surface, width: 1 } },
      selected: { marker: { size: 11 } }, unselected: { marker: { opacity: 0.15 } }, hovertemplate: "%{text}<br>%{x:.0f} Tsd. Nächte · %{y:.2f} min<extra></extra>" }],
    L({ height: 260, dragmode: "select", margin: { l: 40, r: 8, t: 22, b: 36 }, xaxis: AX({ title: { text: "Tsd. Logiernächte" } }), yaxis: AX({ range: [0, ymax] }),
      annotations: [{ text: units[j], xref: "paper", yref: "paper", x: 0, y: 1.02, xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 12, color: C.ink } }] }),
    { ...cfg(`I2_${j}`), modeBarButtons: [["select2d", "lasso2d"]] }));
    const link = (j, ev) => {
      const yms = ev && ev.points && ev.points.length ? new Set(ev.points.map((p) => data[j][p.pointIndex].ym)) : null;
      divs.forEach((d, k) => Plotly.restyle(d, { selectedpoints: [yms ? data[k].map((r, i) => (yms.has(r.ym) ? i : -1)).filter((i) => i >= 0) : null] }));
      det.textContent = yms ? `Ausgewählt: ${[...yms].sort().map(mlab).join(", ")}` : "Rechteck in einem Panel ziehen → dieselben Monate leuchten in allen Panels";
    };
    divs.forEach((d, j) => { d.on("plotly_selected", (ev) => link(j, ev)); d.on("plotly_deselect", () => link(j, null)); });
  }

  // I3 — small multiples for all units, ordered by mean nights
  function drawI3(el) {
    const units = [...new Set(H5.map((r) => r.unit))].map((u) => ({ u, rows: H5.filter((r) => r.unit === u) })).map((o) => ({ ...o, m: Stats.mean(o.rows.map((r) => r.nights)) })).sort((a, b) => b.m - a.m);
    const cols = mobile() ? 2 : 4, traces = [], ann = [];
    units.forEach((o, p) => {
      const i = p + 1, r = Stats.spearman(o.rows.map((q) => q.nights), o.rows.map((q) => q.delay_min));
      SEAS.forEach(([s, name, col, sym]) => { const rows = o.rows.filter((q) => q.season === s);
        traces.push({ type: "scatter", mode: "markers", x: rows.map((q) => q.nights / 1000), y: rows.map((q) => q.delay_min), xaxis: `x${sfx(i)}`, yaxis: `y${sfx(i)}`, name, legendgroup: s, showlegend: p === 0,
          marker: { color: col, symbol: sym, size: 6, line: { color: C.surface, width: 1 } }, text: rows.map((q) => mlab(q.ym)), hovertemplate: `${o.u} · %{text}<br>%{x:.0f} Tsd. · %{y:.2f} min<extra></extra>` }); });
      ann.push(ptitle(i, `${o.u} · r = ${r.toFixed(2)}${["GR", "Zürich", "Bern"].includes(o.u) ? " · Hypothese" : ""}`, ["GR", "Zürich", "Bern"].includes(o.u) ? C.ink : C.ink2));
    });
    const ax = gridAxes(units.length, { tickfont: { size: 9, color: C.ink2 }, nticks: 4 }, (i) => ({ matches: "y", showticklabels: (i - 1) % cols === 0 }));
    Plotly.react(el, traces, L({ ...ax, height: mobile() ? 640 : 420, margin: { l: 36, r: 8, t: 22, b: 28 }, annotations: ann, showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.06, yanchor: "top", font: { size: 11, color: C.ink2 } },
      grid: { rows: Math.ceil(units.length / cols), columns: cols, pattern: "independent", xgap: 0.05, ygap: 0.16 } }), cfg("I3"));
  }

  // O1 — data-status strip per source × month (real load state)
  function drawO1(el) {
    const ms = months("2025-01", "2026-09"), cov = Object.fromEntries(P.coverage.map((c) => [c.ym, c]));
    const LAB = ["nicht publiziert", "fehlt", "teilweise", "geladen"];
    const z = [ms.map((m) => (cov[m]?.complete ? 3 : cov[m]?.loaded ? 2 : 1)), ms.map(() => 3), ms.map((m) => (m <= "2026-07" ? 3 : 0))];
    Plotly.react(el, [{ type: "heatmap", x: ms.map(mlab), y: ["Ist-Daten", "MeteoSchweiz", "HESTA"], z, zmin: 0, zmax: 3, xgap: 2, ygap: 2, showscale: false,
      colorscale: [[0, C.empty], [0.25, C.empty], [0.25, C.divPos], [0.5, C.divPos], [0.5, C.seq[2]], [0.75, C.seq[2]], [0.75, C.seq[5]], [1, C.seq[5]]],
      text: z.map((r) => r.map((v) => LAB[v])), hovertemplate: "%{y} · %{x}: %{text}<extra></extra>" }],
    L({ height: 170, margin: { l: 96, r: 8, t: 8, b: 40 }, xaxis: AX({ showgrid: false, tickangle: -45, tickfont: { size: 9, color: C.ink2 } }), yaxis: AX({ showgrid: false, autorange: "reversed" }) }), cfg("O1"));
  }

  // O2 — share of stops with actual times, region × month (real Ist-Daten aggregates)
  function drawO2(el) {
    const ms = months("2025-01", "2026-09");
    const z = ORDER.map((r) => ms.map((m) => { const rows = NET.months[m]; if (!rows) return null; let n = 0, na = 0;
      rows.forEach(([i, nn, a]) => { if (NET.nodes[i][4] === r) { n += nn; na += a; } }); return n ? na / n : null; }));
    Plotly.react(el, [{ type: "heatmap", x: ms.map(mlab), y: ORDER.map((r) => SHORTN(r)), z, colorscale: seqScale, zmin: 0.9, zmax: 1, xgap: 2, ygap: 2, hoverongaps: false,
      colorbar: { tickformat: ".0%", thickness: 10, tickfont: { size: 10, color: C.ink2 } }, hovertemplate: "%{y} · %{x}: %{z:.1%} mit Ist-Zeit<extra></extra>" }],
    L({ height: 340, plot_bgcolor: C.empty, margin: { l: 110, r: 8, t: 8, b: 40 }, xaxis: AX({ showgrid: false, tickangle: -45, tickfont: { size: 9, color: C.ink2 } }), yaxis: AX({ showgrid: false, autorange: "reversed" }) }), cfg("O2"));
  }


  /* ------------------------------------------------------------------ page helpers ------------------------------------------------------------------ */
  // A page lists its charts as specs: { id, title, cls?, tech, prio: "S"|"C", note, source, sample?, links?, rail?, seg?: { key, def, label, opts: [[value, label]] },
  // draw(el, state) }. sections(specs) → HTML (one viz-card per chart, works as hpage evidence steps); mount(specs) draws them and wires the toggles.
  function sections(specs) {
    return specs.map((s) => `
      <section class="viz-card p-4 min-w-0 ${s.cls || ""}" id="sec-${s.id}" data-rail="${s.rail || s.title.split(/[:·(]/)[0].trim().slice(0, 30)}">
        <div class="flex items-baseline gap-2 flex-wrap"><h2 class="font-semibold">${s.title}</h2>
            ${s.sample ? `<span class="tag-sample">${s.sample}</span>` : ""}
          ${s.links ? `<span class="ml-auto text-xs font-semibold">${s.links}</span>` : ""}</div>
        <p class="text-xs text-ink2 my-2">${s.note}</p>
        ${s.seg ? `<div class="seg mb-2" role="group" aria-label="${s.seg.label || "Darstellung"}">${s.seg.opts.map(([v, l]) =>
          `<button type="button" data-vis="${s.id}" data-v="${v}" aria-pressed="${v === s.seg.def}">${l}</button>`).join("")}</div>` : ""}
        <div id="vis-${s.id}" class="chart"></div>
        <div class="source">${s.source}</div>
      </section>`).join("");
  }
  function mount(specs) {
    const state = Object.fromEntries(specs.map((s) => [s.id, s.seg ? { [s.seg.key]: s.seg.def } : {}]));
    const draw = (s) => { const el = document.getElementById(`vis-${s.id}`); if (el) s.draw(el, state[s.id]); };
    specs.forEach(draw);
    document.querySelectorAll("[data-vis]").forEach((b) => b.addEventListener("click", () => {
      const s = specs.find((x) => x.id === b.dataset.vis);
      if (!s) return;
      state[s.id][s.seg.key] = b.dataset.v;
      document.querySelectorAll(`[data-vis="${s.id}"]`).forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
      draw(s);
    }));
    // sizes (tile size, columns) depend on the width → redraw after a real width change
    let w = window.innerWidth, t;
    window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => { if (Math.abs(window.innerWidth - w) < 40) return; w = window.innerWidth; specs.forEach(draw); }, 250); });
  }

  window.VIS = { drawA1, drawA2, drawD1, drawD2, drawD3, drawD4, drawD5, drawI1, drawI2, drawI3, drawN1, drawN2, drawO1, drawO2, drawP1, drawP2, drawP3, drawS1, drawS2, drawS3, sections, mount, H1, H5 };
})();
