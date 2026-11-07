// Tiny falling snowflakes on a <canvas> behind page headers (decorative, aria-hidden; UI-SPEC §0.5).
// Used by 00-daten, 00-hypothesen and the hypothesis pages (hpage.js). Usage: SFSnow(canvasElement)
// Paused while the intro is off-screen or the tab is hidden; reduced motion → one still frame.
function SFSnow(canvas) {
  const ctx = canvas.getContext("2d"), still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const color = getComputedStyle(canvas).getPropertyValue("--snow").trim() || "#ffffff";
  let W = 0, H = 0, flakes = [], running = false, visible = true, last = 0;
  const flake = (y) => { const r = 0.6 + Math.random() ** 2 * 1.9;
    return { x: Math.random() * W, y: y ?? Math.random() * H, r, vy: 12 + r * 16, amp: 6 + Math.random() * 14,
             ph: Math.random() * 6.28, w: 0.3 + Math.random() * 0.7, a: 0.55 + Math.random() * 0.4 }; };
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.min(240, Math.round(W * H / 7000));
    flakes = Array.from({ length: n }, () => flake());
    draw(0);
  }
  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    for (const f of flakes) {
      const x = f.x + Math.sin(f.ph + t * f.w) * f.amp;
      ctx.globalAlpha = f.a; ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, f.y, f.r, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  function frame(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - (last || now)) / 1000); last = now;
    for (const f of flakes) { f.y += f.vy * dt; if (f.y - f.r > H) Object.assign(f, flake(-4)); }
    draw(now / 1000);
    requestAnimationFrame(frame);
  }
  const setRun = () => { const on = visible && !document.hidden && !still;
    if (on && !running) { running = true; last = 0; requestAnimationFrame(frame); } else if (!on) running = false; };
  resize();
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; setRun(); }).observe(canvas);
  document.addEventListener("visibilitychange", setRun);
  setRun();
}
window.SFSnow = SFSnow;
