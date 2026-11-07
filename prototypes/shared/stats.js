// Small statistics helpers for the prototypes (the real engine uses numpy/scipy/sklearn, SYSTEM-DESIGN §3.3).
const Stats = (() => {
  function rng(seed = 42) { // mulberry32 → reproducible like the engine's seed 42
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const std = (a) => { const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length); };
  function ranks(a) {
    const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]), r = new Array(a.length);
    for (let i = 0; i < idx.length;) { let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++; for (let k = i; k <= j; k++) r[idx[k][1]] = (i + j) / 2 + 1; i = j + 1; }
    return r;
  }
  function pearson(x, y) {
    const mx = mean(x), my = mean(y); let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < x.length; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
    return sxx && syy ? sxy / Math.sqrt(sxx * syy) : 0;
  }
  const spearman = (x, y) => pearson(ranks(x), ranks(y));
  function bootstrapCI(x, y, fn = spearman, n = 500, seed = 42) {
    const r = rng(seed), vals = [];
    for (let b = 0; b < n; b++) {
      const xs = [], ys = [];
      for (let i = 0; i < x.length; i++) { const j = Math.floor(r() * x.length); xs.push(x[j]); ys.push(y[j]); }
      vals.push(fn(xs, ys));
    }
    vals.sort((a, b) => a - b);
    return [vals[Math.floor(0.025 * n)], vals[Math.floor(0.975 * n)]];
  }
  function quantile(sorted, q) { const p = (sorted.length - 1) * q, lo = Math.floor(p), hi = Math.ceil(p); return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo); }
  // PCA via covariance + power iteration with deflation (k ≤ ~30 columns)
  function pca(Z, nComp = 2) {
    const n = Z.length, k = Z[0].length, C = Array.from({ length: k }, () => new Array(k).fill(0));
    for (const row of Z) for (let i = 0; i < k; i++) for (let j = 0; j < k; j++) C[i][j] += row[i] * row[j] / (n - 1);
    const total = C.reduce((s, r, i) => s + r[i], 0), comps = [], vars = [];
    for (let c = 0; c < nComp; c++) {
      let v = Array.from({ length: k }, (_, i) => 1 + i * 0.01), lambda = 0;
      for (let it = 0; it < 500; it++) {
        const w = C.map((r) => r.reduce((s, x, j) => s + x * v[j], 0));
        const norm = Math.hypot(...w); if (!norm) break;
        v = w.map((x) => x / norm); lambda = norm;
      }
      comps.push(v); vars.push(lambda / total);
      for (let i = 0; i < k; i++) for (let j = 0; j < k; j++) C[i][j] -= lambda * v[i] * v[j];
    }
    const scores = Z.map((row) => comps.map((v) => row.reduce((s, x, j) => s + x * v[j], 0)));
    return { comps, vars, scores };
  }
  return { rng, mean, std, ranks, pearson, spearman, bootstrapCI, quantile, pca };
})();
window.Stats = Stats;
