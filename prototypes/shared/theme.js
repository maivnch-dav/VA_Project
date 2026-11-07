// Colour themes for the prototypes (UI-SPEC §4). Every page loads shared/styles.css (structure, tokens only) and then
// this script, which adds shared/themes/<id>.css. Pick one with ?theme=<id> (remembered per browser) or the nav switcher.
// New theme: copy themes/canopy-citron.css, change the values, add it to THEMES.
(function () {
  const THEMES = [
    { id: "canopy-citron", label: "Canopy & Citron" },
    { id: "carbon-mint", label: "Carbon Mint" },
    { id: "peach-indigo", label: "Peach & Indigo" },
  ];
  const DEFAULT = "carbon-mint";
  const ids = THEMES.map((t) => t.id);
  let id = new URLSearchParams(location.search).get("theme");
  try {
    if (ids.includes(id)) localStorage.setItem("sf-theme", id);
    else id = localStorage.getItem("sf-theme");
  } catch (e) { /* storage blocked: fall back to the default */ }
  if (!ids.includes(id)) id = DEFAULT;
  const base = document.currentScript.src.replace(/[^/]*$/, "");
  // parser-inserted, so later scripts (charts) wait for it and read its tokens
  document.write(`<link rel="stylesheet" id="sf-theme" href="${base}themes/${id}.css">`);
  window.SF_THEME = {
    list: THEMES, current: id,
    set(next) {
      try { localStorage.setItem("sf-theme", next); } catch (e) { /* ignore */ }
      const u = new URL(location.href); u.searchParams.set("theme", next); location.replace(u);
    },
  };
})();
