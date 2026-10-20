// Price & technicals panel (same layout and logic as the BMR-Com cotton technicals page).
// Usage: Tech.mount(element, ['ZC']) or Tech.mount(element, ['DC','GDK','CSC',...]) for a symbol picker.
const Tech = (() => {
  const C = { surface: '#ffffff', text: '#1a1a1a', text2: '#444', muted: '#8a8984', grid: '#efefeb', border: '#e5e5e0', up: '#1f7a3a', down: '#b3261e', cup: '#1baf7a', cdn: '#e34948', accent: '#2f6b3a' };
  const PAL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  const OV = { sma20: ['SMA 20', 1], sma50: ['SMA 50', 1], sma100: ['SMA 100', 0], sma200: ['SMA 200', 1], ema9: ['EMA 9', 0], ema21: ['EMA 21', 0], bb: ['Bollinger 20,2', 0], kc: ['Keltner 20,2', 0], dc: ['Donchian 20', 0], ichi: ['Ichimoku', 0], sar: ['Parabolic SAR', 0], piv: ['Weekly pivots', 0], sr: ['Support / resistance', 1] };
  const OSC = { vol: ['Volume', 1], rsi: ['RSI 14', 1], macd: ['MACD 12,26,9', 1], stoch: ['Stochastic 14,3,3', 0], adx: ['ADX / DI 14', 0], atr: ['ATR 14', 0], cci: ['CCI 20', 0], wr: ['Williams %R', 0], obv: ['OBV', 0], mfi: ['MFI 14', 0], mom: ['Momentum 10', 0] };
  let on = {}; Object.keys(OV).forEach(k => on[k] = !!OV[k][1]); Object.keys(OSC).forEach(k => on[k] = !!OSC[k][1]);
  try { const s = JSON.parse(localStorage.getItem('ags_tech_on') || 'null'); if (s) on = Object.assign(on, s); } catch (e) {}
  const save = () => { try { localStorage.setItem('ags_tech_on', JSON.stringify(on)); } catch (e) {} };
  const NAMES = { ZC: 'Corn', ZS: 'Soybeans', ZW: 'Chicago wheat', KE: 'KC wheat', ZM: 'Meal', ZL: 'Oil', HE: 'Lean hogs', LE: 'Live cattle', GF: 'Feeder cattle', DC: 'Class III', GDK: 'Class IV', CSC: 'Cheese', CB: 'Butter', GNF: 'NFDM', DY: 'Dry whey' };
  const cache = {};
  let uid = 0;

  // ---------- indicator math ----------
  const sma = (a, n) => a.map((_, i) => { if (i < n - 1) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) s += a[j]; return s / n; });
  const ema = (a, n) => { const k = 2 / (n + 1); let p = null; return a.map(v => { if (v == null) return p; p = p == null ? v : v * k + p * (1 - k); return p; }); };
  const rma = (a, n) => { let p = null, c = 0, s = 0; return a.map(v => { if (v == null) return null; if (p == null) { s += v; c++; if (c === n) { p = s / n; return p; } return null; } p = (p * (n - 1) + v) / n; return p; }); };
  const stdev = (a, n) => a.map((_, i) => { if (i < n - 1) return null; let m = 0; for (let j = i - n + 1; j <= i; j++) m += a[j]; m /= n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (a[j] - m) ** 2; return Math.sqrt(v / n); });
  const hh = (a, n) => a.map((_, i) => i < n - 1 ? null : Math.max(...a.slice(i - n + 1, i + 1)));
  const ll = (a, n) => a.map((_, i) => i < n - 1 ? null : Math.min(...a.slice(i - n + 1, i + 1)));
  const trueRange = (H, L, Cl) => H.map((h, i) => i === 0 ? h - L[i] : Math.max(h - L[i], Math.abs(h - Cl[i - 1]), Math.abs(L[i] - Cl[i - 1])));
  function rsi(Cl, n = 14) { const g = [], l = []; Cl.forEach((c, i) => { const d = i ? c - Cl[i - 1] : 0; g.push(Math.max(d, 0)); l.push(Math.max(-d, 0)); }); const ag = rma(g, n), al = rma(l, n); return ag.map((v, i) => v == null || al[i] == null ? null : al[i] === 0 ? 100 : 100 - 100 / (1 + v / al[i])); }
  function macd(Cl) { const e26 = ema(Cl, 26), e12 = ema(Cl, 12); const line = e12.map((v, i) => v - e26[i]); const sig = ema(line, 9); return { line, sig, hist: line.map((v, i) => v - sig[i]) }; }
  function smaN(a, n) { return a.map((_, i) => { const w = a.slice(Math.max(0, i - n + 1), i + 1); if (w.length < n || w.some(v => v == null)) return null; return w.reduce((x, y) => x + y, 0) / n; }); }
  function stoch(H, L, Cl) { const h = hh(H, 14), l = ll(L, 14); const raw = Cl.map((c, i) => h[i] == null || h[i] === l[i] ? null : 100 * (c - l[i]) / (h[i] - l[i])); const k = smaN(raw, 3); return { k, d: smaN(k, 3) }; }
  function adx(H, L, Cl, n = 14) { const p = [0], m = [0]; for (let i = 1; i < H.length; i++) { const u = H[i] - H[i - 1], d = L[i - 1] - L[i]; p.push(u > d && u > 0 ? u : 0); m.push(d > u && d > 0 ? d : 0); }
    const tr = rma(trueRange(H, L, Cl), n), pp = rma(p, n), mm = rma(m, n); const pdi = pp.map((v, i) => v == null || !tr[i] ? null : 100 * v / tr[i]), mdi = mm.map((v, i) => v == null || !tr[i] ? null : 100 * v / tr[i]);
    const dx = pdi.map((v, i) => v == null || mdi[i] == null || v + mdi[i] === 0 ? null : 100 * Math.abs(v - mdi[i]) / (v + mdi[i])); return { adx: rma(dx, n), pdi, mdi }; }
  function cci(H, L, Cl, n = 20) { const tp = Cl.map((c, i) => (H[i] + L[i] + c) / 3), m = sma(tp, n); return tp.map((v, i) => { if (m[i] == null) return null; let md = 0; for (let j = i - n + 1; j <= i; j++) md += Math.abs(tp[j] - m[i]); md /= n; return md ? (v - m[i]) / (0.015 * md) : 0; }); }
  function psar(H, L) { const out = [null]; let bull = true, af = .02, ep = H[0], s = L[0]; for (let i = 1; i < H.length; i++) { s = s + af * (ep - s);
    if (bull) { s = Math.min(s, L[i - 1], L[Math.max(0, i - 2)]); if (L[i] < s) { bull = false; s = ep; ep = L[i]; af = .02; } else if (H[i] > ep) { ep = H[i]; af = Math.min(af + .02, .2); } }
    else { s = Math.max(s, H[i - 1], H[Math.max(0, i - 2)]); if (H[i] > s) { bull = true; s = ep; ep = H[i]; af = .02; } else if (L[i] < ep) { ep = L[i]; af = Math.min(af + .02, .2); } } out.push(s); } return out; }
  function obv(Cl, V) { let o = 0; return Cl.map((c, i) => { if (i) o += c > Cl[i - 1] ? V[i] : c < Cl[i - 1] ? -V[i] : 0; return o; }); }
  function mfi(H, L, Cl, V, n = 14) { const tp = Cl.map((c, i) => (H[i] + L[i] + c) / 3); return tp.map((_, i) => { if (i < n) return null; let p = 0, m = 0; for (let j = i - n + 1; j <= i; j++) { const f = tp[j] * V[j]; if (tp[j] > tp[j - 1]) p += f; else if (tp[j] < tp[j - 1]) m += f; } return m === 0 ? 100 : 100 - 100 / (1 + p / m); }); }

  function chartOpts(h, w) { return { height: h, width: w, layout: { background: { type: 'solid', color: C.surface }, textColor: C.text2, fontFamily: 'system-ui,-apple-system,Segoe UI,sans-serif', fontSize: 11 },
    grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } }, rightPriceScale: { borderColor: C.border }, timeScale: { borderColor: C.border, rightOffset: 4 },
    crosshair: { mode: 0 }, handleScroll: true, handleScale: true, localization: { locale: 'en-US' } }; }
  const lineS = (c, color, w = 1.5, extra = {}) => c.addLineSeries({ color, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });

  function mount(root, syms) {
    const id = 't' + (++uid);
    const st = { sym: syms[0], D: null, S: null, tf: 'D', range: '1Y', charts: [], seasIdx: 0, seasChart: null };
    const q = s => root.querySelector(s);
    root.innerHTML = `<div class="card tech"><h2>Price &amp; technicals</h2><div class="note" data-r="asof">Loading…</div>
      ${syms.length > 1 ? `<div class="tbar"><div class="grp" data-r="g-sym"><span class="lab">Market</span></div></div>` : ''}
      <div class="tbar"><div class="grp" data-r="g-series"><span class="lab">Contract</span></div></div>
      <div class="tbar"><div class="grp" data-r="g-tf"><span class="lab">Bars</span></div><div class="grp" data-r="g-range"><span class="lab">Range</span></div></div>
      <div class="tbar"><div class="grp" data-r="g-ov"><span class="lab">Overlays</span></div></div>
      <div class="tbar"><div class="grp" data-r="g-osc"><span class="lab">Panels</span></div></div>
      <div class="tlayout"><div><div class="tlegend" data-r="legend"></div><div data-r="main" class="tmain"></div><div data-r="panes"></div><p class="note" data-r="tnote"></p></div>
        <div class="tside"><div data-r="summary"></div><div data-r="levels" style="margin-top:12px"></div></div></div>
      <div data-r="seas-card" style="margin-top:16px"><h2>Seasonality and percentiles — price and spreads</h2><p class="note" data-r="seas-lead"></p>
        <div class="tbl"><table data-r="t-seas"></table></div>
        <div class="tbar"><div class="grp" data-r="g-seas"><span class="lab">Seasonal chart</span></div></div>
        <div class="tlegend"><span style="color:#2a78d6">■</span> current contract &nbsp; <span style="color:#eb6834">■</span> same contract last year &nbsp; <span style="color:#8a8984">■</span> 5-yr average &nbsp; shaded: 10–90th and 25–75th percentile of all years</div>
        <div style="position:relative;height:340px"><canvas data-r="c-seas" id="${id}seas"></canvas></div>
        <p class="note">History: per-contract daily closes since 2006 (TradingView/CME). Each contract is aligned on weeks before its last trading day, so the same point in every season lines up. Percentile = share of past observations below today's level.</p></div></div>`;
    const R = n => q(`[data-r="${n}"]`);

    function chips(name, items, cur, cb, cls = '') { const g = R(name); g.querySelectorAll('button').forEach(b => b.remove());
      items.forEach(([k, lab]) => { const b = document.createElement('button'); b.className = 'chip ' + cls + ((typeof cur === 'function' ? cur(k) : cur === k) ? ' on' : ''); b.textContent = lab; b.onclick = () => cb(k, b); g.appendChild(b); }); }

    function bars() { let b = st.S.bars.map(x => ({ time: x[0], open: x[1], high: x[2], low: x[3], close: x[4], volume: x[5] }));
      if (st.tf === 'D') return b;
      const key = t => { const d = new Date(t + 'T00:00:00Z'); if (st.tf === 'M') return t.slice(0, 7) + '-01'; const day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
      const out = []; b.forEach(x => { const k = key(x.time), l = out[out.length - 1]; if (l && l.k === k) { l.high = Math.max(l.high, x.high); l.low = Math.min(l.low, x.low); l.close = x.close; l.volume += x.volume; } else out.push({ k, time: k, open: x.open, high: x.high, low: x.low, close: x.close, volume: x.volume }); });
      return out.map(({ k, ...r }) => r); }
    const pts = (B, a) => a.map((v, i) => v == null || !isFinite(v) ? { time: B[i].time } : { time: B[i].time, value: v });

    function render() {
      st.charts.forEach(c => c.remove()); st.charts = []; R('panes').innerHTML = '';
      const B = bars(), Cl = B.map(b => b.close), H = B.map(b => b.high), L = B.map(b => b.low), V = B.map(b => b.volume);
      const el = R('main'), W = el.clientWidth || 800, dp = st.D.dp;
      const main = LightweightCharts.createChart(el, { ...chartOpts(460, W), localization: { locale: 'en-US', priceFormatter: v => v.toFixed(dp) } }); st.charts.push(main);
      let cs;
      if (st.S.kind === 'spread') { cs = main.addLineSeries({ color: C.text, lineWidth: 2, priceLineVisible: true }); cs.setData(B.map(b => ({ time: b.time, value: b.close }))); }
      else { cs = main.addCandlestickSeries({ upColor: C.cup, downColor: C.cdn, borderVisible: false, wickUpColor: C.cup, wickDownColor: C.cdn }); cs.setData(B.map(({ volume, ...r }) => r)); }
      const legendItems = [];
      const add = (label, arr, color, w, extra) => { const s = lineS(main, color, w, extra); s.setData(pts(B, arr)); legendItems.push([label, color]); return s; };
      if (on.sma20) add('SMA 20', sma(Cl, 20), PAL[0]);
      if (on.sma50) add('SMA 50', sma(Cl, 50), PAL[1]);
      if (on.sma100) add('SMA 100', sma(Cl, 100), PAL[2]);
      if (on.sma200) add('SMA 200', sma(Cl, 200), PAL[6], 2);
      if (on.ema9) add('EMA 9', ema(Cl, 9), PAL[3]);
      if (on.ema21) add('EMA 21', ema(Cl, 21), PAL[4]);
      if (on.bb) { const m = sma(Cl, 20), sd = stdev(Cl, 20); add('BB mid', m, C.muted, 1, { lineStyle: 2 }); lineS(main, C.muted).setData(pts(B, m.map((v, i) => v == null ? null : v + 2 * sd[i]))); lineS(main, C.muted).setData(pts(B, m.map((v, i) => v == null ? null : v - 2 * sd[i]))); }
      if (on.kc) { const m = ema(Cl, 20), a = rma(trueRange(H, L, Cl), 10); add('Keltner', m, PAL[5], 1, { lineStyle: 2 }); lineS(main, PAL[5], 1, { lineStyle: 1 }).setData(pts(B, m.map((v, i) => a[i] == null ? null : v + 2 * a[i]))); lineS(main, PAL[5], 1, { lineStyle: 1 }).setData(pts(B, m.map((v, i) => a[i] == null ? null : v - 2 * a[i]))); }
      if (on.dc) { add('Donchian 20', hh(H, 20), PAL[7], 1, { lineStyle: 2 }); lineS(main, PAL[7], 1, { lineStyle: 2 }).setData(pts(B, ll(L, 20))); }
      if (on.ichi) { const conv = hh(H, 9).map((v, i) => v == null ? null : (v + ll(L, 9)[i]) / 2), base = hh(H, 26).map((v, i) => v == null ? null : (v + ll(L, 26)[i]) / 2);
        const a = conv.map((v, i) => v == null || base[i] == null ? null : (v + base[i]) / 2), b = hh(H, 52).map((v, i) => v == null ? null : (v + ll(L, 52)[i]) / 2);
        const shift = arr => { const r = Array(B.length).fill(null); arr.forEach((v, i) => { if (i + 26 < B.length) r[i + 26] = v; }); return r; };
        add('Tenkan', conv, PAL[0], 1); add('Kijun', base, PAL[7], 1); add('Senkou A', shift(a), PAL[2], 1, { lineStyle: 2 }); add('Senkou B', shift(b), PAL[1], 1, { lineStyle: 2 }); }
      if (on.sar) { const s = lineS(main, C.text2, 1, { lineVisible: false, pointMarkersVisible: true, pointMarkersRadius: 1.5 }); s.setData(pts(B, psar(H, L))); legendItems.push(['SAR', C.text2]); }
      const A = st.S.analysis;
      if (on.piv && A.pivots && A.pivots.weekly) { const p = A.pivots.weekly; [['P', '#8a8984'], ['R1', PAL[7]], ['R2', PAL[7]], ['S1', PAL[2]], ['S2', PAL[2]]].forEach(([k, c]) => cs.createPriceLine({ price: p[k], color: c, lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: 'W ' + k })); }
      if (on.sr) { (A.resistance || []).slice(0, 3).forEach(v => cs.createPriceLine({ price: v, color: C.down, lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: 'R' }));
        (A.support || []).slice(0, 3).forEach(v => cs.createPriceLine({ price: v, color: C.up, lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: 'S' })); }
      if (on.vol) { const vs = main.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
        main.priceScale('vol').applyOptions({ scaleMargins: { top: .82, bottom: 0 } });
        vs.setData(B.map((b, i) => ({ time: b.time, value: b.volume, color: (i && b.close < B[i - 1].close) ? C.cdn + '66' : C.cup + '66' }))); }
      const pane = (title, fn) => { const wrap = document.createElement('div'); wrap.innerHTML = `<div class="pane-title">${title}</div><div class="sub-pane"></div>`; R('panes').appendChild(wrap);
        const c = LightweightCharts.createChart(wrap.querySelector('.sub-pane'), chartOpts(140, W)); st.charts.push(c); fn(c); return c; };
      const lvl = (s, vals) => vals.forEach(v => s.createPriceLine({ price: v, color: C.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
      if (on.rsi) pane('RSI 14', c => { const s = lineS(c, PAL[6], 1.5, { lastValueVisible: true }); s.setData(pts(B, rsi(Cl))); lvl(s, [30, 50, 70]); });
      if (on.macd) pane('MACD 12,26,9', c => { const m = macd(Cl); const h = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }); h.setData(B.map((b, i) => ({ time: b.time, value: m.hist[i], color: m.hist[i] >= 0 ? C.cup + '99' : C.cdn + '99' })));
        lineS(c, PAL[0], 1.5, { lastValueVisible: true }).setData(pts(B, m.line)); lineS(c, PAL[1]).setData(pts(B, m.sig)); });
      if (on.stoch) pane('Stochastic 14,3,3', c => { const s = stoch(H, L, Cl); const a = lineS(c, PAL[0], 1.5, { lastValueVisible: true }); a.setData(pts(B, s.k)); lineS(c, PAL[1]).setData(pts(B, s.d)); lvl(a, [20, 80]); });
      if (on.adx) pane('ADX / +DI / −DI 14', c => { const a = adx(H, L, Cl); const s = lineS(c, C.text, 1.5, { lastValueVisible: true }); s.setData(pts(B, a.adx)); lineS(c, PAL[2]).setData(pts(B, a.pdi)); lineS(c, PAL[7]).setData(pts(B, a.mdi)); lvl(s, [20, 25]); });
      if (on.atr) pane(`ATR 14 (${st.D.unit})`, c => { lineS(c, PAL[3], 1.5, { lastValueVisible: true }).setData(pts(B, rma(trueRange(H, L, Cl), 14))); });
      if (on.cci) pane('CCI 20', c => { const s = lineS(c, PAL[4], 1.5, { lastValueVisible: true }); s.setData(pts(B, cci(H, L, Cl))); lvl(s, [-100, 0, 100]); });
      if (on.wr) pane('Williams %R 14', c => { const h = hh(H, 14), l = ll(L, 14); const s = lineS(c, PAL[5], 1.5, { lastValueVisible: true }); s.setData(pts(B, Cl.map((x, i) => h[i] == null || h[i] === l[i] ? null : -100 * (h[i] - x) / (h[i] - l[i])))); lvl(s, [-80, -20]); });
      if (on.obv) pane('On-balance volume', c => { lineS(c, PAL[0], 1.5, { lastValueVisible: true, priceFormat: { type: 'volume' } }).setData(pts(B, obv(Cl, V))); });
      if (on.mfi) pane('Money flow index 14', c => { const s = lineS(c, PAL[2], 1.5, { lastValueVisible: true }); s.setData(pts(B, mfi(H, L, Cl, V))); lvl(s, [20, 80]); });
      if (on.mom) pane(`Momentum 10 (${st.D.unit})`, c => { const s = lineS(c, PAL[1], 1.5, { lastValueVisible: true }); s.setData(pts(B, Cl.map((x, i) => i < 10 ? null : x - Cl[i - 10]))); lvl(s, [0]); });
      let busy = false; st.charts.forEach(c => c.timeScale().subscribeVisibleLogicalRangeChange(r => { if (busy || !r) return; busy = true; st.charts.forEach(o => { if (o !== c) o.timeScale().setVisibleLogicalRange(r); }); busy = false; }));
      const n = { '3M': 63, '6M': 126, '1Y': 252, '3Y': 756, 'All': 1e9 }[st.range] / (st.tf === 'W' ? 5 : st.tf === 'M' ? 21 : 1);
      main.timeScale().setVisibleLogicalRange({ from: Math.max(0, B.length - n), to: B.length + 3 });
      const lg = R('legend'), f = v => v == null ? '–' : v.toFixed(dp);
      const show = b => { if (!b) return; const i = B.findIndex(x => x.time === b.time), p = i > 0 ? B[i - 1].close : null, ch = p != null ? b.close - p : null;
        lg.innerHTML = `<b>${st.D.name} · ${st.S.label}</b> ${b.time} · O <b>${f(b.open)}</b> H <b>${f(b.high)}</b> L <b>${f(b.low)}</b> C <b>${f(b.close)}</b>` + (ch != null ? ` <span style="color:${ch >= 0 ? C.up : C.down}">${ch >= 0 ? '+' : ''}${ch.toFixed(dp)}</span>` : '') + ` · Vol ${(b.volume || 0).toLocaleString()}` +
          (legendItems.length ? ' &nbsp; ' + legendItems.map(([t, c]) => `<span style="color:${c}">■</span> ${t}`).join(' &nbsp;') : ''); };
      show(B[B.length - 1]);
      main.subscribeCrosshairMove(p => { if (!p || !p.time) { show(B[B.length - 1]); return; } const t = typeof p.time === 'string' ? p.time : `${p.time.year}-${String(p.time.month).padStart(2, '0')}-${String(p.time.day).padStart(2, '0')}`; show(B.find(x => x.time === t)); });
      R('tnote').textContent = st.D.note;
    }

    function renderSide() {
      const A = st.S.analysis, r = A.returns || {}, dp = st.D.dp, u = st.D.unit;
      const pc = v => v == null ? '–' : `<span class="pill ${v >= 0 ? 'up' : 'down'}">${v >= 0 ? '+' : ''}${A.spread ? v.toFixed(dp) : v.toFixed(1) + '%'}</span>`;
      const g = x => x ? `<div><div class="l">${x[0]}</div><div class="v ${x[1].replace(' ', '-')}">${x[1]}</div></div>` : '';
      const rd = A.rating_daily || {}, rw = A.rating_weekly || {};
      const cnt = c => c ? `${c[0]} buy · ${c[1]} neutral · ${c[2]} sell` : '';
      const sig = x => `<td class="${x > 0 ? 'b' : x < 0 ? 's' : 'n'}">${x > 0 ? 'Buy' : x < 0 ? 'Sell' : 'Neutral'}</td>`;
      R('summary').innerHTML = `<h3>Technical summary · ${st.S.label}</h3><div class="big">${A.last.toFixed(dp)} <span class="u">${u}</span> <span class="pill ${A.chg >= 0 ? 'up' : 'down'}">${A.chg >= 0 ? '+' : ''}${A.chg.toFixed(dp)}</span></div>
        <div class="note">as of ${A.date} · 1w ${pc(r['1w'])} 1m ${pc(r['1m'])} 3m ${pc(r['3m'])} YTD ${pc(r.ytd)}</div>
        <div class="gauge">${g(['Daily', rd.overall || '–'])}${g(['Weekly', rw.overall || '–'])}${g(['Trend', A.trend])}</div>
        <ul class="read">${A.text.map(t => `<li>${t}</li>`).join('')}</ul>
        <details><summary>Moving averages — daily (${cnt(rd.ma_counts)})</summary><table><tr><th>MA</th><th>Value</th><th>Signal</th></tr>${(rd.ma_detail || []).map(x => `<tr><td>${x[0]}</td><td>${(+x[1]).toFixed(dp)}</td>${sig(x[2])}</tr>`).join('')}</table></details>
        <details><summary>Oscillators — daily (${cnt(rd.osc_counts)})</summary><table><tr><th>Oscillator</th><th>Value</th><th>Signal</th></tr>${(rd.osc_detail || []).map(x => `<tr><td>${x[0]}</td><td>${x[1] == null ? '–' : x[1]}</td>${sig(x[2])}</tr>`).join('')}</table></details>`;
      const P = A.pivots || {}, fb = A.fib || {}, f = v => v == null ? '–' : (+v).toFixed(dp);
      let h = `<h3>Key levels</h3><table><tr><th></th><th>Weekly</th><th>Monthly</th></tr>`;
      ['R3', 'R2', 'R1', 'P', 'S1', 'S2', 'S3'].forEach(k => { h += `<tr><td>Pivot ${k}</td><td>${P.weekly ? f(P.weekly[k]) : '–'}</td><td>${P.monthly ? f(P.monthly[k]) : '–'}</td></tr>`; });
      h += `</table><table style="margin-top:8px"><tr><th>52-week Fibonacci</th><th>Level</th></tr><tr><td>52-wk high</td><td>${f(A.hi52)}</td></tr>` +
        Object.entries(fb).map(([k, v]) => `<tr><td>${k}</td><td>${f(v)}</td></tr>`).join('') + `<tr><td>52-wk low</td><td>${f(A.lo52)}</td></tr></table>` +
        `<table style="margin-top:8px"><tr><th>Swing levels</th><th>Nearest first</th></tr><tr><td>Resistance</td><td style="white-space:normal">${(A.resistance || []).slice(0, 4).map(f).join(', ') || '–'}</td></tr><tr><td>Support</td><td style="white-space:normal">${(A.support || []).slice(0, 4).map(f).join(', ') || '–'}</td></tr></table>`;
      R('levels').innerHTML = h;
    }

    function renderSeas() {
      const L = st.D.seasonal; if (!L || !L.length) { R('seas-card').style.display = 'none'; return; }
      R('seas-card').style.display = '';
      const dp = st.D.dp, pc = v => v == null ? '–' : `${v.toFixed(0)}`, f2 = v => v == null ? '–' : v.toFixed(dp);
      const tone = v => v == null ? '' : (v >= 80 || v <= 20) ? 'x' : '';
      let h = `<tr><th>Series</th><th>Contract</th><th>Now (${st.D.unit})</th><th>Weeks to expiry</th><th>%ile same time</th><th>%ile same time, 10 yrs</th><th>%ile all history</th><th>%ile last 10 yrs</th><th>Median same time</th><th>5-yr avg same time</th><th>Last year same time</th><th>Range same time</th></tr>`;
      L.forEach(x => { h += `<tr><td>${x.label}</td><td>${x.contract}</td><td><b>${f2(x.now)}</b></td><td>${x.wk_now}</td><td class="${tone(x.pct_same_time)}">${pc(x.pct_same_time)}</td><td>${pc(x.pct_same_time_10y)}</td><td class="${tone(x.pct_all)}">${pc(x.pct_all)}</td><td>${pc(x.pct_all_10y)}</td><td>${f2(x.median_same_time)}</td><td>${f2(x.avg5_same_time)}</td><td>${f2(x.ly_same_time)}</td><td>${f2(x.min_same_time)} – ${f2(x.max_same_time)}</td></tr>`; });
      R('t-seas').innerHTML = h;
      const yrs = L[0].years || [];
      R('seas-lead').textContent = `Where each futures price and calendar spread sits today against the same point of the season in every year since ${yrs[0] || 2006} (${L[0].n_years} seasons), and against all history. High percentile = expensive / unusually inverted spread; low = cheap / deep carry.`;
      if (st.seasIdx >= L.length) st.seasIdx = 0;
      chips('g-seas', L.map((x, i) => [i, x.label]), st.seasIdx, k => { st.seasIdx = k; renderSeas(); });
      const x = L[st.seasIdx], exp = new Date(x.expiry + 'T00:00:00Z');
      const lab = w => { const d = new Date(exp); d.setUTCDate(d.getUTCDate() - 7 * w); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); };
      const P = a => (a || []).map(p => ({ x: p[0], y: p[1] }));
      if (st.seasChart) st.seasChart.destroy();
      const band = 'rgba(138,137,132,.16)', band2 = 'rgba(138,137,132,.28)';
      st.seasChart = new Chart(R('c-seas'), { type: 'line', data: { datasets: [
        { label: '90th', data: P(x.bands[90]), borderWidth: 0, pointRadius: 0, fill: false },
        { label: '10–90th', data: P(x.bands[10]), borderWidth: 0, pointRadius: 0, backgroundColor: band, fill: '-1' },
        { label: '75th', data: P(x.bands[75]), borderWidth: 0, pointRadius: 0, fill: false },
        { label: '25–75th', data: P(x.bands[25]), borderWidth: 0, pointRadius: 0, backgroundColor: band2, fill: '-1' },
        { label: 'Median', data: P(x.bands[50]), borderColor: C.muted, borderWidth: 1, pointRadius: 0, borderDash: [2, 3] },
        { label: '5-yr avg', data: P(x.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
        { label: 'Last year', data: P(x.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
        { label: x.contract, data: P(x.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { display: false }, tooltip: { filter: i => !['90th', '75th'].includes(i.dataset.label), callbacks: { title: i => `${i[0].parsed.x} weeks to expiry (~${lab(i[0].parsed.x)})`, label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(dp)}` } } },
          scales: { x: { type: 'linear', reverse: true, min: 0, max: 52, grid: { display: false }, ticks: { color: C.muted, callback: v => lab(v), maxTicksLimit: 9 } },
            y: { grid: { color: C.grid }, ticks: { color: C.muted } } } } });
    }

    function controls() {
      if (syms.length > 1) chips('g-sym', syms.map(s => [s, NAMES[s] || s]), st.sym, k => { st.sym = k; load(); });
      chips('g-series', st.D.series.map((s, i) => [i, s.label]), st.D.series.indexOf(st.S), k => { st.S = st.D.series[k]; controls(); render(); renderSide(); });
      chips('g-tf', [['D', 'Daily'], ['W', 'Weekly'], ['M', 'Monthly']], st.tf, k => { st.tf = k; controls(); render(); });
      chips('g-range', [['3M', '3M'], ['6M', '6M'], ['1Y', '1Y'], ['3Y', '3Y'], ['All', 'All']], st.range, k => { st.range = k; controls(); render(); });
      chips('g-ov', Object.entries(OV).map(([k, v]) => [k, v[0]]), k => on[k], (k, b) => { on[k] = !on[k]; b.classList.toggle('on'); save(); render(); }, 'ind');
      chips('g-osc', Object.entries(OSC).map(([k, v]) => [k, v[0]]), k => on[k], (k, b) => { on[k] = !on[k]; b.classList.toggle('on'); save(); render(); }, 'ind');
    }
    async function load() {
      try {
        if (!cache[st.sym]) cache[st.sym] = await fetch(`data/technicals/${st.sym}.json?` + Date.now()).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
        st.D = cache[st.sym];
        st.S = st.D.series.find(s => s.ticker === st.D.default) || st.D.series[0];
        R('asof').textContent = `${st.D.name} · TradingView daily bars · updated ${st.D.generated} · default view is the most active nearby contract`;
        controls(); render(); renderSide(); renderSeas();
      } catch (e) { R('asof').textContent = `Price data for ${st.sym} is not built yet (data/technicals/${st.sym}.json).`; }
    }
    window.addEventListener('resize', () => { if (!root.isConnected) return; const w = R('main')?.clientWidth; if (w) st.charts.forEach(c => c.applyOptions({ width: w })); });
    load();
  }
  return { mount };
})();
