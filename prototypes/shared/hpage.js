// Shared hypothesis page (UI-SPEC §2.2, §2.8) as a story: typed question, answer, evidence steps, then
// «Selbst testen» with Ergebnis (Standard vs Variante), RuleEditor generated
// from descriptors, VariantList, SweepStrip, conditions, definitions, URL state.
// A page supplies: code, topic, statement, question (typed into the search box), DESC, compute(p) → {verdict, metricText, conds[]}, evidenceHtml,
// render(cur, ctx), defs(cur), basis(cur), seedVariants. Variants live in localStorage (real app: /rule-sets).
/* global SF */
const HPage = (() => {
  let cfg, DESC, D, DEFAULTS, params, STD, variants, loadedId = null, timer;

  // ---------- descriptor helpers ----------
  const visible = (d, p) => !d.when || p[d.when[0]] === d.when[1];
  const diffKeys = (p) => DESC.filter((d) => visible(d, p) && p[d.name] !== d.def).map((d) => d.name);
  const fmtVal = (d, v) => {
    if (d.type === "boolean") return v ? "ja" : "nein";
    if (d.type === "enum") return (d.options.find((o) => String(o[0]) === String(v)) || [v, v])[1];
    if (d.type === "multi") return String(v).split(",").map((x) => (d.options.find((o) => o[0] === x) || [x, x])[1]).join(", ");
    if (d.type === "assign") return d.summary ? d.summary(v) : v;
    return d.pct ? `${Math.round(v * 100)} %` : `${v}${d.unit ? " " + d.unit : ""}`;
  };
  const parse = (d, raw) => (d.type === "boolean" ? raw === "true" || raw === true
    : d.type === "number" || d.type === "integer" ? Number(raw) : String(raw));

  // ---------- URL ----------
  function readUrl() {
    const q = new URLSearchParams(location.search), p = { ...DEFAULTS };
    for (const d of DESC) if (q.has(d.name)) p[d.name] = parse(d, q.get(d.name));
    return p;
  }
  function writeUrl(p) {
    const q = new URLSearchParams();
    diffKeys(p).forEach((k) => q.set(k, p[k]));
    try { history.replaceState(null, "", q.toString() ? `?${q}` : location.pathname); } catch (e) { /* file:// in some browsers */ }
  }

  // ---------- layout: story (UI-SPEC §2.2, 20/10/2026) ----------
  // Frage (typed into a search box) → Antwort (standard verdict) → Evidenz, one step per block →
  // Warum dieses Urteil → Definitionen → «Selbst testen» (rules, variants, robustness) as the closing invitation.
  function skeleton() {
    const nav = (h, label) => h ? `<a href="${h}" class="btn btn-ghost">${label}</a>` : "<span></span>";
    const q = cfg.question || cfg.statement;
    return `
<div id="nav"></div>
<main class="max-w-screen-xl mx-auto px-4 pb-10">
  <div class="lg:hidden flex items-center justify-between text-sm pt-3">
    ${nav(cfg.prev, `‹ ${cfg.prevLabel || ""}`)}<span class="font-semibold">${cfg.code} von 5</span>${nav(cfg.next, `${cfg.nextLabel || ""} ›`)}
  </div>
  <section class="story-intro has-snow" data-rail="Frage" aria-labelledby="qTitle">
    <canvas class="snow" id="qSnow" aria-hidden="true"></canvas>
    <div class="display text-5xl lg:text-6xl leading-none mb-2">${cfg.code}</div>
    <div class="eyebrow">${cfg.topic}</div>
    <h1 id="qTitle" class="sr-only">${cfg.code}: ${q}</h1>
    <form class="qbar" id="qbar" role="search" aria-label="Frage an die Daten" onsubmit="return false">
      <svg class="qbar-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg>
      <div class="qbar-text" aria-hidden="true"><span id="qTyped"></span><span class="qbar-caret" id="qCaret"></span></div>
      <button class="qbar-go" id="qGo" type="submit" aria-label="Antwort ansehen">↓</button>
    </form>
    <div class="story-after-q" id="afterQ">
      <p class="text-ink2 mt-5 max-w-2xl text-center"><span class="section-title">Hypothese ${cfg.code}</span><br><span class="italic">«${cfg.statement}»</span></p>
      ${cfg.banner ? `<div class="tag-sample mt-4 text-center">${cfg.banner}</div>` : ""}
      <button type="button" class="scroll-cue" id="qCue" aria-label="Zur Antwort scrollen"><span>Antwort</span><span aria-hidden="true">↓</span></button>
    </div>
  </section>

  <section class="step story-answer" id="answerStep" data-rail="Antwort" aria-label="Antwort">
    <div class="step-eyebrow">Antwort nach den Standardregeln${cfg.resultTag ? ` · <span class="tag-sample">${cfg.resultTag}</span>` : ""}</div>
    <div id="answer" aria-live="polite"></div>
  </section>

  <div id="story" class="grid min-w-0">${cfg.evidenceHtml}</div>

  <section class="step" data-rail="Urteil" aria-label="Warum dieses Urteil">
    <div class="step-eyebrow">Warum dieses Urteil?</div>
    <section class="card p-4"><h2 class="font-semibold mb-2">Bedingungen</h2><table class="tbl num" id="conditions"></table></section>
  </section>
  <section class="step" data-rail="Definitionen" aria-label="Definitionen und Datenbasis">
    <div class="step-eyebrow">So haben wir gemessen</div>
    <section class="card p-4 grid gap-4 md:grid-cols-2 text-sm">
      <div><h2 class="font-semibold mb-1">Definitionen</h2><ul class="list-disc pl-5 grid gap-1 text-ink2" id="defs"></ul></div>
      <div><h2 class="font-semibold mb-1">Datenbasis</h2><ul class="grid gap-1 text-ink2" id="basis"></ul>
        <div class="flex gap-2 mt-3">
          <button class="btn" type="button" id="csvBtn">CSV ↓</button>
          <button class="btn" type="button" onclick="SF.toast('Bericht heruntergeladen')">Bericht ↓</button>
        </div></div>
    </section>
  </section>

  <section class="step story-play" id="play" data-rail="Selbst testen" aria-labelledby="playTitle">
    <div class="play-invite">
      <div class="step-eyebrow">Jetzt du</div>
      <h2 id="playTitle">Hält das Urteil, wenn du die Regeln änderst?</h2>
      <p class="text-ink2 mt-2 max-w-2xl">Die Antwort oben folgt den festgelegten Standardregeln. Ändere Schwellen und Definitionen, vergleiche mit dem Standard und speichere interessante Varianten. Die Diagramme oben zeigen dann die Variante; das offizielle Urteil bleibt der Standard.</p>
    </div>
    <div class="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)] mt-5">
      <details id="rules" class="card self-start min-w-0" open>
        <summary class="p-4 flex items-center gap-2 font-semibold">
          <span>Regeln anpassen</span><span id="changedChipM"></span><span class="ml-auto text-ink2" aria-hidden="true">▾</span>
        </summary>
        <div class="p-4 pt-0 lg:pt-4">
          <div class="hidden lg:flex items-center mb-3"><h3 class="font-semibold">Regeln</h3><span id="changedChip" class="ml-auto"></span></div>
          <form id="editor" class="grid gap-4" onsubmit="return false"></form>
          <div class="flex flex-wrap gap-2 mt-4 pt-4 border-t" style="border-color:var(--grid)">
            <button class="btn" id="resetAll" type="button">↺ Standard</button>
            <button class="btn btn-primary ml-auto" id="saveBtn" type="button">Als Variante speichern…</button>
          </div>
        </div>
      </details>
      <div class="grid gap-5 self-start min-w-0">
        <section class="card p-4" aria-label="Ergebnis Standard und Variante">
          <div class="flex items-center gap-2 mb-2"><span class="section-title">Ergebnis</span>${cfg.resultTag ? `<span class="tag-sample">${cfg.resultTag}</span>` : ""}</div>
          <div id="result" aria-live="polite" class="grid gap-2"></div>
          <p class="field-help mt-2">Bedingungen mit Standard- und Variantenspalte: <a href="#conditions" class="underline">oben unter «Warum dieses Urteil?»</a></p>
        </section>
        <section class="card p-4" aria-label="Robustheit">
          <h3 class="font-semibold mb-1">Robustheit</h3>
          <label class="field-help block mb-2">Parameter variieren <select id="sweepParam" class="input mt-1"></select></label>
          <div id="sweep" class="flex flex-wrap gap-2"></div>
          <p class="field-help mt-2">Umrandet = Standard. Klick übernimmt den Wert in die Regeln.</p>
        </section>
        <section class="card p-4" aria-label="Varianten">
          <div class="flex items-center mb-2"><h3 class="font-semibold">Varianten</h3><span class="ml-2 text-xs text-ink2" id="varCount"></span></div>
          <ul id="variants" class="grid gap-1"></ul>
        </section>
      </div>
    </div>
  </section>
</main>
<div id="varBar" class="var-bar navy-scope" hidden role="status">
  <span class="tag-variant">Variante aktiv</span><span class="text-sm">Diagramme zeigen die Variante</span>
  <a href="#play" class="btn btn-ghost" style="min-height:28px">Regeln ↓</a>
  <button type="button" class="btn" style="min-height:28px" id="varBarReset">↺ Standard</button>
</div>
<div id="modal" class="modal-backdrop" hidden>
  <form class="modal card p-5 grid gap-3" id="saveForm" role="dialog" aria-modal="true" aria-labelledby="mTitle">
    <h2 id="mTitle" class="font-semibold text-lg">Als Variante speichern</h2>
    <p class="text-sm text-ink2" id="mDiff"></p>
    <label class="field-label">Name <span style="color:var(--critical)">*</span><input class="input mt-1" name="name" maxlength="80" required></label>
    <label class="field-label">Notiz <textarea class="input mt-1" name="note" rows="2" maxlength="2000"></textarea></label>
    <label class="field-label">Autor <input class="input mt-1" name="author" maxlength="80" placeholder="optional (lokal)"></label>
    <label class="flex items-center gap-2 text-sm"><input type="checkbox" name="pinned"> ★ im Bericht zeigen</label>
    <p class="text-sm" id="mError" style="color:var(--critical)" hidden></p>
    <div class="flex gap-2 justify-end"><button class="btn" type="button" id="mCancel">Abbrechen</button><button class="btn btn-primary" type="submit">Speichern</button></div>
  </form>
</div>`;
  }

  // ---------- rule editor ----------
  function control(d) {
    const id = `f_${d.name}`, v = params[d.name], changed = v !== d.def;
    const reset = changed ? `<button type="button" class="icon-btn" title="Auf Standard zurücksetzen" aria-label="${d.label} auf Standard zurücksetzen" data-reset="${d.name}">↺</button>` : "";
    const std = changed ? `<span class="changed-mark">${d.type === "assign" || d.type === "multi" ? "geändert" : `Standard: ${fmtVal(d, d.def)}`}</span>` : "";
    const head = `<div class="flex items-center gap-2"><label for="${id}" class="field-label flex-1">${d.label}</label>${std}${reset}</div>`;
    const indent = d.when ? ' style="padding-left:14px;border-left:2px solid var(--grid)"' : "";
    let input;
    if (d.type === "boolean") {
      return `<div class="flex items-center gap-3"><label for="${id}" class="field-label flex-1">${d.label}</label>${std}${reset}
        <label class="switch"><input id="${id}" type="checkbox" data-k="${d.name}" ${v ? "checked" : ""}><span></span></label></div>`;
    }
    if (d.type === "enum" && d.radio) {
      input = `<div class="grid gap-1 mt-1" role="radiogroup" aria-label="${d.label}">` + d.options.map(([ov, l]) =>
        `<label class="flex items-center gap-2 text-sm"><input type="radio" name="${d.name}" value="${ov}" data-k="${d.name}" ${String(v) === String(ov) ? "checked" : ""} style="accent-color:var(--accent)">${l}${ov === d.def ? ' <span class="field-help">(Standard)</span>' : ""}</label>`).join("") + "</div>";
    } else if (d.type === "enum") {
      input = `<select id="${id}" class="input mt-1 ${changed ? "changed" : ""}" data-k="${d.name}">` +
        d.options.map(([ov, l, dis]) => `<option value="${ov}" ${String(v) === String(ov) ? "selected" : ""} ${dis ? "disabled" : ""}>${l}</option>`).join("") + "</select>";
    } else if (d.type === "multi") {
      const sel = String(v).split(",").filter(Boolean);
      input = `<div class="flex flex-wrap gap-2 mt-1" role="group" aria-label="${d.label}">` + d.options.map(([ov, l]) => {
        const on = sel.includes(ov);
        return `<button type="button" class="chip ${on ? "is-current" : ""}" aria-pressed="${on}" data-multi="${d.name}" data-v="${ov}">${l}${on ? " ✕" : ""}</button>`;
      }).join("") + `</div><div class="field-help">${d.help || ""}</div>`;
    } else if (d.type === "assign") {
      input = `<div class="grid gap-1 mt-1">` + d.items.map(([code, name]) => {
        const cur = d.get(v, code);
        const btn = (val, l) => `<button type="button" aria-pressed="${cur === val}" data-assign="${d.name}" data-item="${code}" data-v="${val}">${l}</button>`;
        return `<div class="flex items-center gap-3 text-sm"><span class="flex-1 min-w-0 truncate">${name}</span>
          <span class="seg" role="group" aria-label="${name}">${btn("s", "CH")}${btn("i", "Int.")}${btn("-", "–")}</span></div>`;
      }).join("") + `</div><div class="field-help">${d.help || ""}</div>`;
    } else {
      const shown = d.pct ? Math.round(v * 100) : v;
      const [mn, mx, st] = d.pct ? [d.min * 100, d.max * 100, d.step * 100] : [d.min, d.max, d.step];
      input = `<div class="flex items-center gap-2 mt-1">
        <input type="range" min="${mn}" max="${mx}" step="${st}" value="${shown}" data-k="${d.name}" data-pct="${!!d.pct}" aria-label="${d.label}">
        <input id="${id}" type="number" class="input num ${changed ? "changed" : ""}" style="width:76px" min="${mn}" max="${mx}" step="${st}" value="${shown}" data-k="${d.name}" data-pct="${!!d.pct}">
        <span class="text-xs text-ink2 w-8">${d.pct ? "%" : d.unit || ""}</span></div>
        <div class="field-help" data-err="${d.name}" hidden style="color:var(--critical)">Erlaubt: ${mn}–${mx}</div>`;
    }
    return `<div${indent}>${head}${input}</div>`;
  }
  function chipHtml() {
    const n = diffKeys(params).length;
    return n ? `<span class="tag-variant">${n} geändert</span>` : '<span class="text-xs text-ink2">Standard</span>';
  }
  function renderEditor() {
    const groups = ["Daten", "Regel", "Entscheidung"].filter((g) => DESC.some((d) => d.group === g));
    document.getElementById("editor").innerHTML = groups.map((g) =>
      `<fieldset class="grid gap-3 min-w-0"><legend class="section-title mb-1">${g}</legend>${DESC.filter((d) => d.group === g && visible(d, params)).map(control).join("")}</fieldset>`).join("");
    document.getElementById("changedChip").innerHTML = chipHtml();
    document.getElementById("changedChipM").innerHTML = chipHtml();
  }
  function renderEditorPreserveFocus() {
    const a = document.activeElement, k = a?.dataset?.k, t = a?.type;
    renderEditor();
    if (k) document.querySelector(`[data-k="${k}"]${t === "range" ? '[type="range"]' : t === "number" ? '[type="number"]' : ""}`)?.focus();
  }
  function setParam(k, v, immediate) {
    params = { ...params, [k]: v };
    loadedId = null;
    clearTimeout(timer);
    document.getElementById("result").classList.add("busy");
    timer = setTimeout(() => update(immediate), immediate ? 0 : 400);
  }
  function bindEditor() {
    const ed = document.getElementById("editor");
    ed.addEventListener("input", (e) => {
      const k = e.target.dataset.k; if (!k) return;
      const d = D[k];
      let v = d.type === "boolean" ? e.target.checked : d.type === "enum" ? parse(d, e.target.value) : Number(e.target.value);
      if (d.type === "number" || d.type === "integer") {
        const raw = v; v = e.target.dataset.pct === "true" ? raw / 100 : raw;
        const err = document.querySelector(`[data-err="${k}"]`);
        const bad = isNaN(raw) || v < d.min - 1e-9 || v > d.max + 1e-9;
        e.target.classList.toggle("invalid", bad); if (err) err.hidden = !bad;
        if (bad) return;
        document.querySelectorAll(`[data-k="${k}"]`).forEach((el) => { if (el !== e.target) el.value = raw; });
      }
      setParam(k, v, d.type === "enum" || d.type === "boolean");
    });
    ed.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.reset) { setParam(b.dataset.reset, DEFAULTS[b.dataset.reset], true); }
      if (b.dataset.multi) {
        const d = D[b.dataset.multi], sel = String(params[d.name]).split(",").filter(Boolean), x = b.dataset.v;
        let next = sel.includes(x) ? sel.filter((y) => y !== x) : [...sel, x];
        if (next.length < (d.minSel || 1)) { SF.toast(`Mindestens ${d.minSel || 1} Auswahl nötig`); return; }
        if (next.length > (d.maxSel || 99)) { SF.toast(`Höchstens ${d.maxSel} Auswahlen`); return; }
        next = d.options.map((o) => o[0]).filter((o) => next.includes(o));
        setParam(d.name, next.join(","), true);
      }
      if (b.dataset.assign) {
        const d = D[b.dataset.assign], nv = d.set(params[d.name], b.dataset.item, b.dataset.v);
        const err = d.validate ? d.validate(nv) : null;
        if (err) { SF.toast(err); return; }
        setParam(d.name, nv, true);
      }
    });
    document.getElementById("resetAll").onclick = () => { params = { ...DEFAULTS }; loadedId = null; update(true); };
  }

  // ---------- result / conditions / defs ----------
  function resultRow(r, isVariant, label) {
    const tag = isVariant ? '<span class="tag-variant">Variante (nicht offiziell)</span>' : '<span class="text-xs font-semibold text-ink2">Standard</span>';
    return `<div class="grid sm:grid-cols-[180px_auto_1fr] items-center gap-x-4 gap-y-1">
      <div>${tag}</div><div>${SF.badge(r.verdict)}</div>
      <div class="text-sm num ${isVariant && r.metricText !== STD.metricText ? "diff" : ""}">${r.metricText}${label ? ` <span class="text-ink2">· ${label}</span>` : ""}</div></div>`;
  }
  const mark = (passed) => passed === null ? '<span class="text-ink2">– nicht verlangt</span>'
    : passed ? '<span style="color:var(--v-supported)" aria-label="erfüllt">✓</span>' : '<span style="color:var(--v-rejected-text)" aria-label="nicht erfüllt">✕</span>';
  function renderConditions(r, isVar) {
    const n = Math.max(STD.conds.length, r.conds.length);
    const rows = Array.from({ length: n }, (_, i) => {
      const c = STD.conds[i], v = r.conds[i];
      const changed = isVar && c && v && (v.passed !== c.passed || v.value !== c.value);
      return `<tr><td>${(isVar ? v : c)?.label ?? ""}</td><td>${c ? `${mark(c.passed)} <span class="text-ink2">${c.value ?? ""}</span>` : ""}</td>
        ${isVar ? `<td class="${changed ? "diff" : ""}">${v ? `${mark(v.passed)} ${v.value ?? ""}` : ""}</td>` : ""}</tr>`;
    }).join("");
    document.getElementById("conditions").innerHTML =
      `<thead><tr><th>Bedingung</th><th>Standard</th>${isVar ? '<th style="color:var(--accent)">Variante</th>' : ""}</tr></thead><tbody>${rows}</tbody>`;
  }

  // ---------- variants ----------
  const VKEY = () => `sf_proto_${cfg.code.toLowerCase()}_variants`;
  const saveVariants = () => { try { localStorage.setItem(VKEY(), JSON.stringify(variants)); } catch (e) { /* storage blocked */ } };
  function renderVariants() {
    const live = variants.filter((v) => !v.deleted);
    document.getElementById("varCount").textContent = `${live.length} gespeichert`;
    const curKey = JSON.stringify(Object.fromEntries(diffKeys(params).map((k) => [k, params[k]])));
    const row = (v, std) => {
      const r = std ? STD : cfg.compute({ ...DEFAULTS, ...v.params });
      const active = std ? diffKeys(params).length === 0 : JSON.stringify(v.params) === curKey;
      const parent = !std && v.parent ? variants.find((x) => x.id === v.parent) : null;
      return `<li class="rounded p-2 ${active ? "ring-2" : ""}" style="${active ? "--tw-ring-color:var(--accent);background:color-mix(in srgb, var(--accent) 8%, transparent)" : ""}">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
          ${std ? '<span class="font-semibold text-sm">Standard</span>'
            : `<button class="icon-btn" aria-label="${v.pinned ? "Stern entfernen" : "Mit Stern markieren"}" data-pin="${v.id}" style="color:${v.pinned ? "var(--warning)" : "var(--muted)"}">${v.pinned ? "★" : "☆"}</button>
               <button class="text-left text-sm font-semibold flex-1 min-w-[9rem]" data-load="${v.id}" title="Laden">${v.name}</button>`}
          <span class="${std ? "ml-auto" : ""}">${SF.badge(r.verdict, "sm")}</span>
          ${std ? (active ? "" : '<button class="btn btn-ghost" style="min-height:26px;padding:0 6px" data-std="1">Laden</button>')
            : `<button class="icon-btn" aria-label="Löschen" data-del="${v.id}">✕</button>`}
        </div>
        ${std ? "" : `<div class="text-xs text-ink2 pl-9">${Object.entries(v.params).map(([k, val]) => `${D[k].label}: ${fmtVal(D[k], val)}`).join(" · ")}</div>
          <div class="text-xs pl-9" style="color:var(--muted)">${v.author || "–"} · ${v.date}${parent ? ` · ↳ abgeleitet von «${parent.name}»` : ""}</div>`}
      </li>`;
    };
    document.getElementById("variants").innerHTML = row(null, true) + live.map((v) => row(v, false)).join("");
  }
  function bindVariants() {
    document.getElementById("variants").addEventListener("click", (e) => {
      const t = e.target.closest("button"); if (!t) return;
      if (t.dataset.std) { params = { ...DEFAULTS }; loadedId = null; update(true); }
      if (t.dataset.load) { const v = variants.find((x) => x.id === +t.dataset.load); params = { ...DEFAULTS, ...v.params }; loadedId = v.id; update(true); }
      if (t.dataset.pin) { const v = variants.find((x) => x.id === +t.dataset.pin); v.pinned = !v.pinned; saveVariants(); renderVariants(); }
      if (t.dataset.del) {
        const v = variants.find((x) => x.id === +t.dataset.del); v.deleted = true; saveVariants(); renderVariants();
        SF.toast(`«${v.name}» gelöscht`, "Rückgängig", () => { v.deleted = false; saveVariants(); renderVariants(); });
      }
    });
    const modal = document.getElementById("modal"), form = document.getElementById("saveForm");
    document.getElementById("saveBtn").onclick = () => {
      const keys = diffKeys(params);
      if (!keys.length) { SF.toast("Keine Änderung gegenüber dem Standard – nichts zu speichern"); return; }
      document.getElementById("mDiff").innerHTML = "Geändert: " + keys.map((k) => `${D[k].label}: <b>${fmtVal(D[k], params[k])}</b>`).join(" · ");
      document.getElementById("mError").hidden = true; form.reset(); modal.hidden = false; form.name.focus();
    };
    document.getElementById("mCancel").onclick = () => { modal.hidden = true; };
    modal.addEventListener("keydown", (e) => { if (e.key === "Escape") modal.hidden = true; });
    form.onsubmit = () => {
      const p = Object.fromEntries(diffKeys(params).map((k) => [k, params[k]])), err = document.getElementById("mError");
      const dupP = variants.find((v) => !v.deleted && JSON.stringify(v.params) === JSON.stringify(p));
      const dupN = variants.find((v) => !v.deleted && v.name === form.name.value.trim());
      if (dupP || dupN) { err.textContent = dupP ? `Diese Regeln sind bereits als «${dupP.name}» gespeichert.` : "Name bereits vergeben."; err.hidden = false; return false; }
      const id = Math.max(0, ...variants.map((v) => v.id)) + 1;
      variants.unshift({ id, name: form.name.value.trim(), author: form.author.value.trim(),
        date: new Date().toLocaleDateString("de-CH", { day: "2-digit", month: "2-digit" }) + ".", pinned: form.pinned.checked, params: p, parent: loadedId || undefined });
      saveVariants(); loadedId = id; modal.hidden = true; update(false); SF.toast("Variante gespeichert");
      return false;
    };
  }

  // ---------- sweep ----------
  function renderSweep() {
    const sel = document.getElementById("sweepParam");
    const opts = DESC.filter((d) => d.sweep && visible(d, params));
    if (!opts.length) { sel.closest("section").hidden = true; return; }
    const cur = opts.find((d) => d.name === sel.value) ? sel.value : opts[0].name;
    sel.innerHTML = opts.map((d) => `<option value="${d.name}" ${d.name === cur ? "selected" : ""}>${d.label}</option>`).join("");
    const d = D[cur];
    document.getElementById("sweep").innerHTML = d.sweep.map((v) => {
      const r = cfg.compute({ ...params, [cur]: v }), vd = SF.verdicts[r.verdict];
      const cls = `${v === d.def ? "is-standard" : ""} ${v === params[cur] ? "is-current" : ""}`;
      const lab = d.chip?.[v] ?? fmtVal(d, v);
      return `<button class="chip ${cls}" data-sv="${v}" title="${fmtVal(d, v)} – ${vd.label}"><span aria-hidden="true">${vd.ico}</span>${lab}<span class="sr-only"> – ${vd.label}</span></button>`;
    }).join("");
  }
  function bindSweep() {
    document.getElementById("sweepParam").onchange = renderSweep;
    document.getElementById("sweep").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sv]"); if (!b) return;
      const d = D[document.getElementById("sweepParam").value];
      params = { ...params, [d.name]: parse(d, b.dataset.sv) }; loadedId = null; update(true);
    });
  }

  // ---------- main update ----------
  function update(rerenderEditor) {
    const cur = cfg.compute(params), isVar = diffKeys(params).length > 0;
    writeUrl(params);
    if (rerenderEditor) renderEditor();
    else {
      document.getElementById("changedChip").innerHTML = chipHtml(); document.getElementById("changedChipM").innerHTML = chipHtml();
      if (!isVar || document.activeElement?.type !== "range") renderEditorPreserveFocus();
    }
    const vName = loadedId ? variants.find((v) => v.id === loadedId)?.name : null;
    const res = document.getElementById("result");
    res.classList.remove("busy");
    res.innerHTML = resultRow(STD, false) + (isVar ? resultRow(cur, true, vName ? `«${vName}»` : "nicht gespeichert") : "");
    // story answer = always the standard (HR6); a variant only shows in «Selbst testen» and the variant bar
    document.getElementById("answer").innerHTML = `<div class="answer-badge">${SF.badge(STD.verdict)}</div>
      <p class="answer-metric num">${STD.metricText}</p>
      ${isVar ? `<p class="text-sm mt-2"><span class="tag-variant">Variante aktiv</span> Die Diagramme unten zeigen die Variante: ${SF.badge(cur.verdict, "sm")} <a href="#play" class="underline">Regeln ↓</a></p>` : ""}`;
    document.getElementById("varBar").hidden = !isVar;
    cfg.render(cur, { std: STD, isVar, params, DEFAULTS, diffKeys });
    renderConditions(cur, isVar);
    document.getElementById("defs").innerHTML = cfg.defs(cur).map((s) => `<li>${s}</li>`).join("");
    document.getElementById("basis").innerHTML = cfg.basis(cur).map((s) => `<li>${s}</li>`).join("");
    renderVariants(); renderSweep();
  }

  // ---------- story: evidence steps, typed question, scroll reveal ----------
  function buildStory(skipTyping) {
    // every top-level block of evidenceHtml becomes one step («Evidenz n / N»); label for the section rail:
    // data-rail on the block > its first non-empty h2 > «Evidenz n»
    const story = document.getElementById("story"), blocks = [...story.children], n = blocks.length;
    blocks.forEach((b, i) => {
      const h = [...b.querySelectorAll("h2")].map((x) => x.textContent.trim()).find(Boolean);
      const label = b.dataset.rail || (h ? h.replace(/^\([a-z]\)\s*/, "").split(/[:(–]/)[0].trim().slice(0, 30) : `Evidenz ${i + 1}`);
      b.removeAttribute("data-rail");
      const step = document.createElement("section");
      step.className = "step"; step.dataset.rail = label; step.setAttribute("aria-label", `Evidenz ${i + 1} von ${n}: ${label}`);
      step.innerHTML = `<div class="step-eyebrow">Evidenz ${i + 1} / ${n}</div>`;
      story.insertBefore(step, b); step.appendChild(b);
    });

    SFSnow(document.getElementById("qSnow"));

    // typed question (visual only; the full text is in the sr-only h1)
    const q = cfg.question || cfg.statement, typed = document.getElementById("qTyped");
    const after = document.getElementById("afterQ"), caret = document.getElementById("qCaret");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const done = () => { typed.textContent = q; caret.classList.add("is-done"); after.classList.add("is-in"); document.getElementById("qbar").classList.add("is-ready"); };
    if (reduce || skipTyping) done();
    else {
      const t0 = performance.now() + 450, dur = Math.min(2600, 30 * q.length);
      const tick = (now) => {
        const k = Math.max(0, Math.min(1, (now - t0) / dur)), eased = 1 - (1 - k) ** 2;
        typed.textContent = q.slice(0, Math.floor(eased * q.length));
        if (k < 1) requestAnimationFrame(tick); else done();
      };
      requestAnimationFrame(tick);
    }
    const toAnswer = () => document.getElementById("answerStep").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    document.getElementById("qbar").onsubmit = () => { done(); toAnswer(); return false; };
    document.getElementById("qCue").onclick = toAnswer;

    // reveal steps as they enter the viewport (content stays visible without JS / with reduced motion)
    if (reduce || !("IntersectionObserver" in window)) return;
    document.body.classList.add("js-story");
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); } }),
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 });
    document.querySelectorAll(".step").forEach((s) => io.observe(s));
  }

  function init(c) {
    cfg = c; DESC = c.DESC; D = Object.fromEntries(DESC.map((d) => [d.name, d]));
    DEFAULTS = Object.fromEntries(DESC.map((d) => [d.name, d.def]));
    document.getElementById("app").innerHTML = skeleton();
    window.NAV_STATUS = c.navStatus;
    document.getElementById("nav").innerHTML = SF.nav(c.code);
    params = readUrl();
    STD = c.compute(DEFAULTS);
    try { variants = JSON.parse(localStorage.getItem(VKEY())); } catch (e) { variants = null; }
    if (!Array.isArray(variants)) variants = c.seedVariants || [];
    bindEditor(); bindVariants(); bindSweep();
    document.getElementById("csvBtn").onclick = () => SF.toast(`${c.code}_${c.csvTable || "daten"}_${new Date().toISOString().slice(0, 10)}.csv heruntergeladen`);
    document.getElementById("varBarReset").onclick = () => { params = { ...DEFAULTS }; loadedId = null; update(true); };
    buildStory(diffKeys(params).length > 0);
    // draw after Tailwind (CDN) has applied the grid, then keep charts sized to their containers
    const start = () => {
      update(true);
      c.afterInit?.();
      new ResizeObserver(() => document.querySelectorAll(".js-plotly-plot").forEach((el) => Plotly.Plots.resize(el)))
        .observe(document.querySelector("main"));
    };
    if (document.readyState === "complete") requestAnimationFrame(start);
    else window.addEventListener("load", () => requestAnimationFrame(start));
  }
  return { init, fmtVal, visible };
})();
window.HPage = HPage;
