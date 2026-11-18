// Jarvis observatory. Read-only: it only issues GET requests and never places orders.
// No inline script or style is used so the strict same-origin CSP stays intact.
const SVG_NS = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
const money = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const num = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 2) => (v === null || v === undefined) ? '—' : (v > 0 ? '+' : '') + num(v, d) + '%';
const signed = v => (v > 0 ? '+' : v < 0 ? '−' : '') + money.format(Math.abs(v));
const when = iso => new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

function el(tag, attrs = {}, kids = [], svg = false) {
  const node = svg ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    if (k === 'text') node.textContent = v; else node.setAttribute(k, v);
  }
  for (const kid of [].concat(kids)) if (kid) node.append(kid);
  return node;
}
const s = (tag, attrs, kids) => el(tag, attrs, kids, true);

function scale(d0, d1, r0, r1) {
  const span = (d1 - d0) || 1;
  return v => r0 + ((v - d0) / span) * (r1 - r0);
}
function path(points) {
  return points.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
}
function niceTicks(lo, hi, n = 4) {
  const step = (hi - lo) / n;
  return Array.from({ length: n + 1 }, (_, i) => lo + step * i);
}

// Shared chart frame: sizes the SVG to its box, draws grid + y labels, wires the hover crosshair.
function frame(svg, tipEl, { rows, y0, y1, fmt, xs, onHover }) {
  const box = svg.getBoundingClientRect();
  const W = Math.max(320, box.width), H = Math.max(180, box.height);
  const m = { l: 56, r: 12, t: 10, b: 24 };
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const defs = s('defs', {}, s('linearGradient', { id: 'brassFade', x1: 0, y1: 0, x2: 0, y2: 1 }, [
    s('stop', { offset: '0%', 'stop-color': '#d2ad62', 'stop-opacity': 0.32 }),
    s('stop', { offset: '100%', 'stop-color': '#d2ad62', 'stop-opacity': 0 }),
  ]));
  svg.append(defs);
  const X = scale(0, rows - 1, m.l, W - m.r);
  const Y = scale(y0, y1, H - m.b, m.t);
  for (const t of niceTicks(y0, y1)) {
    svg.append(s('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
    svg.append(s('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end', text: fmt(t) }));
  }
  const labelAt = [0, 0.25, 0.5, 0.75, 1];
  for (const f of labelAt) {
    const i = Math.round((rows - 1) * f);
    svg.append(s('text', { x: X(i), y: H - 6, 'text-anchor': f === 0 ? 'start' : f === 1 ? 'end' : 'middle',
      text: new Date(xs[i]).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }));
  }
  const cross = s('line', { class: 'cross', y1: m.t, y2: H - m.b, visibility: 'hidden' });
  svg.append(cross);
  return { W, H, m, X, Y, cross, attach() {
    const hit = s('rect', { class: 'hit', x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b });
    const move = ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) * (W / r.width);
      const i = Math.max(0, Math.min(rows - 1, Math.round(((px - m.l) / (W - m.l - m.r)) * (rows - 1))));
      cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('visibility', 'visible');
      tipEl.hidden = false;
      tipEl.replaceChildren(...onHover(i));
      const left = (X(i) / W) * r.width;
      tipEl.style.left = Math.min(Math.max(0, left + 12), r.width - tipEl.offsetWidth) + 'px';
    };
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); tipEl.hidden = true; });
    svg.append(hit);
  } };
}

function drawEquity(data, animate) {
  const svg = $('equityChart'), tip = $('equityTip');
  const eq = data.equity, start = data.metrics.starting_equity;
  const vals = eq.map(p => p.e).concat(start);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.12 || 1;
  const f = frame(svg, tip, { rows: eq.length, y0: lo - pad, y1: hi + pad, fmt: v => whole.format(v), xs: eq.map(p => p.t),
    onHover: i => [el('strong', { text: money.format(eq[i].e) }), el('br'), el('span', { text: when(eq[i].t) + ' · drawdown ' + num(eq[i].dd, 2) + '%' })] });
  const pts = eq.map((p, i) => [f.X(i), f.Y(p.e)]);
  const g = s('g', { class: animate ? 'load-reveal' : '' });
  g.append(s('line', { class: 'base-line', x1: f.m.l, x2: f.W - f.m.r, y1: f.Y(start), y2: f.Y(start) }));
  g.append(s('path', { class: 'eq-area', d: path(pts) + `L${pts.at(-1)[0]} ${f.H - f.m.b} L${pts[0][0]} ${f.H - f.m.b} Z` }));
  g.append(s('path', { class: 'eq-line', d: path(pts) }));
  svg.insertBefore(g, f.cross);
  f.attach();
}

function drawPrice(data, animate) {
  const svg = $('priceChart'), tip = $('priceTip');
  const c = data.candles, closes = c.map(x => x.c);
  const lo = Math.min(...closes), hi = Math.max(...closes), pad = (hi - lo) * 0.08 || 1;
  const f = frame(svg, tip, { rows: c.length, y0: lo - pad, y1: hi + pad, fmt: v => num(v, 1), xs: c.map(x => x.t),
    onHover: i => [el('strong', { text: num(c[i].c, 2) }), el('br'), el('span', { text: when(c[i].t) })] });
  const idx = new Map(c.map((x, i) => [x.t, i]));
  const g = s('g', { class: animate ? 'load-reveal' : '' });
  for (const t of data.trades) {
    const a = idx.get(t.entry_t), b = idx.get(t.exit_t);
    if (a !== undefined && b !== undefined) g.append(s('rect', { class: 'hold-band', x: f.X(a), width: Math.max(1, f.X(b) - f.X(a)), y: f.m.t, height: f.H - f.m.t - f.m.b }));
  }
  g.append(s('path', { class: 'p-line', d: path(c.map((x, i) => [f.X(i), f.Y(x.c)])) }));
  const line = key => path(c.map((x, i) => x[key] === null ? null : [f.X(i), f.Y(x[key])]).filter(Boolean));
  g.append(s('path', { class: 's-line', d: line('s') }));
  g.append(s('path', { class: 'f-line', d: line('f') }));
  for (const t of data.trades) {
    const a = idx.get(t.entry_t), b = idx.get(t.exit_t);
    if (a !== undefined) g.append(s('circle', { class: 'buy', cx: f.X(a), cy: f.Y(t.entry_price), r: 4.5 }, s('title', { text: 'Entry ' + num(t.entry_price) + ' · ' + when(t.entry_t) })));
    if (b !== undefined) g.append(s('circle', { class: 'sell', cx: f.X(b), cy: f.Y(t.exit_price), r: 4.5 }, s('title', { text: 'Exit ' + num(t.exit_price) + ' · ' + signed(t.net_pnl) })));
  }
  svg.insertBefore(g, f.cross);
  f.attach();
}

function metric(label, value, cls = '', sub = '') {
  return el('div', {}, [el('dt', { text: label }), el('dd', { class: cls }, [document.createTextNode(value), sub ? el('span', { class: 'sub', text: sub }) : null])]);
}

function renderResult(data, animate) {
  const m = data.metrics;
  const delta = m.ending_equity - m.starting_equity;
  $('heroValue').textContent = money.format(m.ending_equity);
  const sub = $('heroSub');
  sub.replaceChildren(
    el('span', { class: delta >= 0 ? 'gain' : 'loss', text: signed(delta) + ' (' + pct(m.return_pct) + ')' }),
    document.createTextNode(' from ' + money.format(m.starting_equity) + ' over ' + data.params.bars + ' simulated hours. Simply holding the asset returned ' + pct(m.buy_and_hold_pct) + '.'));
  $('banner').textContent = data.notice;
  drawEquity(data, animate);
  drawPrice(data, animate);

  const box = $('metrics');
  box.replaceChildren(
    metric('Net return', pct(m.return_pct), m.return_pct >= 0 ? 'gain' : 'loss'),
    metric('Max drawdown', num(m.max_drawdown_pct, 2) + '%', 'loss'),
    metric('Win rate', m.win_rate === null ? '—' : num(m.win_rate * 100, 0) + '%', '', m.wins + ' wins, ' + m.losses + ' losses'),
    metric('Profit factor', m.profit_factor === null ? '—' : num(m.profit_factor, 2)),
    metric('Expectancy per trade', m.expectancy_per_exit === null ? '—' : signed(m.expectancy_per_exit), (m.expectancy_per_exit || 0) >= 0 ? 'gain' : 'loss'),
    metric('Trades closed', String(m.exits), '', m.signals + ' signals, ' + m.risk_rejections + ' blocked by risk'),
    metric('Open positions', String(m.open_positions)),
    metric('Audit trail', m.audit_chain_valid ? 'Verified' : 'Broken', m.audit_chain_valid ? 'gain' : 'loss', m.audit_events + ' hash-chained events'),
  );

  const body = $('trades');
  if (!data.trades.length) {
    body.replaceChildren(el('tr', {}, el('td', { colspan: 4, class: 'empty', text: 'No trades closed in this run. Try another seed.' })));
  } else {
    body.replaceChildren(...data.trades.slice().reverse().map(t => el('tr', {}, [
      el('td', { text: when(t.entry_t) }),
      el('td', { class: 'num', text: num(t.entry_price) }),
      el('td', { class: 'num', text: num(t.exit_price) }),
      el('td', { class: 'num ' + (t.net_pnl >= 0 ? 'gain' : 'loss'), text: signed(t.net_pnl) }),
    ])));
  }
}

let last = null, running = false;
async function runSimulation(animate = true) {
  if (running) return;
  running = true;
  const btn = $('run');
  btn.disabled = true; btn.textContent = 'Running…';
  const seed = $('seed').value.trim();
  try {
    if (!/^\d{1,9}$/.test(seed)) throw new Error('Enter a whole number from 0 to 999,999,999.');
    const r = await fetch('/showcase?seed=' + seed, { cache: 'no-store' });
    if (!r.ok) throw new Error('The simulation could not run (' + r.status + ').');
    last = await r.json();
    renderResult(last, animate);
  } catch (err) {
    $('banner').textContent = err.message || 'The simulation could not run. Check that the Jarvis server is running.';
  } finally {
    btn.disabled = false; btn.textContent = 'Run simulation'; running = false;
  }
}

function setSeal(id, cls, text) {
  const node = $(id);
  node.className = 'seal ' + cls;
  node.querySelector('.seal-text').textContent = text;
}

async function loadGate() {
  try {
    const g = await (await fetch('/gate', { cache: 'no-store' })).json();
    $('gateState').textContent = g.live_trading_enabled ? 'Open' : 'Locked. Live trading is not available.';
    const n = g.verified_demo_days;
    $('gateFill').setAttribute('width', String(300 * Math.min(1, n / g.required_demo_days)));
    $('gateMeter').setAttribute('aria-valuenow', String(n));
    $('gateDays').textContent = n + ' of ' + g.required_demo_days + ' verified demo days';
    $('criteria').replaceChildren(...g.criteria.map(c => el('tr', {}, [el('td', { text: c.label }), el('td', { class: 'num', text: c.current + ' / ' + c.required })])));
    $('gateNote').textContent = g.note;
  } catch { $('gateState').textContent = 'Gate status unavailable.'; }
}

const FEATURE_TAG = { enabled: ['on', 'On'], active: ['on', 'On'], experimental: ['exp', 'Experimental'], disabled: ['off', 'Off'], unavailable: ['off', 'Unavailable'] };
async function loadStatus() {
  try {
    const h = await fetch('/health', { cache: 'no-store' });
    if (!h.ok) throw new Error();
    setSeal('sealHealth', 'ok', 'Server healthy');
    const st = await (await fetch('/status', { cache: 'no-store' })).json();
    setSeal('sealMode', st.mode === 'paper' ? 'ok' : 'err', st.mode === 'paper' ? 'Paper money only' : 'Unexpected mode');
    setSeal('sealKill', st.kill_switch ? 'warn' : 'ok', st.kill_switch ? 'Kill switch engaged' : 'Kill switch released');
    const a = st.account || {};
    $('account').replaceChildren(
      metric('Balance', a.balance === undefined ? '—' : money.format(a.balance)),
      metric('Equity', a.equity === undefined ? '—' : money.format(a.equity)),
      metric('Open positions', Array.isArray(st.positions) ? String(st.positions.length) : '—'),
      metric('Broker', st.broker || '—'));
    const feats = (st.feature_inventory && st.feature_inventory.features) || [];
    $('features').replaceChildren(...feats.map(f => {
      const [cls, label] = FEATURE_TAG[f.state] || ['off', f.state];
      return el('li', {}, [el('span', { class: 'tag ' + cls, text: label }), el('span', { text: f.name })]);
    }));
    $('updated').textContent = new Date().toLocaleTimeString();
  } catch {
    setSeal('sealHealth', 'err', 'Server unreachable');
    setSeal('sealMode', '', 'Paper only');
    setSeal('sealKill', '', 'Kill switch');
    $('account').replaceChildren();
  }
}

$('runner').addEventListener('submit', ev => { ev.preventDefault(); runSimulation(true); });
$('shuffle').addEventListener('click', () => { $('seed').value = String(Math.floor(Math.random() * 1e6)); runSimulation(true); });
let resizeTimer;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => last && renderResult(last, false), 150); });

loadStatus(); loadGate(); runSimulation(true);
setInterval(loadStatus, 5000);
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => {});
