// Section rail (UI-SPEC §5 `SectionRail`): one square per [data-rail] section, fixed at the right edge.
// Passed = dark, current = accent (larger), upcoming = light. Hover/focus shows the label; click scrolls.
// Desktop only (≥ 1024 px, CSS); the page works the same without it.
(function () {
  function build() {
    const secs = [...document.querySelectorAll("[data-rail]")];
    if (secs.length < 3) return;
    const nav = document.createElement("nav");
    nav.className = "rail"; nav.setAttribute("aria-label", "Abschnitte");
    const dots = secs.map((sec) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "rail-dot is-next";
      b.dataset.label = sec.dataset.rail; b.setAttribute("aria-label", `Zu «${sec.dataset.rail}»`);
      b.addEventListener("click", () => {
        const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        sec.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
      });
      nav.appendChild(b);
      return b;
    });
    document.body.appendChild(nav);
    document.body.classList.add("has-rail");

    let current = -2, queued = false;
    function update() {
      queued = false;
      // current = last section whose top has passed 35 % of the viewport (last one once the page bottom is reached)
      const line = window.innerHeight * 0.35;
      let idx = 0;
      secs.forEach((s, i) => { if (s.getBoundingClientRect().top <= line) idx = i; });
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) idx = secs.length - 1;
      if (idx === current) return;
      current = idx;
      dots.forEach((d, i) => {
        d.className = `rail-dot ${i < idx ? "is-past" : i === idx ? "is-now" : "is-next"}`;
        if (i === idx) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current");
      });
    }
    const queue = () => { if (!queued) { queued = true; requestAnimationFrame(update); } };
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    update();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
})();
