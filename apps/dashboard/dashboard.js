const base = window.location.origin;
document.getElementById('apiBase').textContent = base;

const FIELDS = ['mode', 'broker', 'kill', 'balance', 'equity', 'positions'];

// Never leave values from an earlier successful poll on screen once the API stops
// answering: a stale balance or kill-switch state on a status page is misleading.
function clearStatus() {
  for (const id of FIELDS) {
    const el = document.getElementById(id);
    el.textContent = '—';
    el.className = '';
  }
}

async function load() {
  const healthEl = document.getElementById('health');
  try {
    const healthResponse = await fetch(base + '/health', { cache: 'no-store' });
    if (!healthResponse.ok) throw new Error('Health request failed');
    const h = await healthResponse.json();
    healthEl.textContent = h.ok ? 'ok' : 'degraded';
    healthEl.className = h.ok ? 'ok' : 'warn';
  } catch {
    healthEl.textContent = 'unavailable';
    healthEl.className = 'err';
    clearStatus();
    return;
  }
  try {
    const statusResponse = await fetch(base + '/status', { cache: 'no-store' });
    if (!statusResponse.ok) throw new Error('Status request failed');
    const s = await statusResponse.json();
    document.getElementById('mode').textContent = s.mode || '—';
    document.getElementById('broker').textContent = s.broker || '—';
    const kill = document.getElementById('kill');
    if (typeof s.kill_switch === 'boolean') {
      kill.textContent = s.kill_switch ? 'engaged' : 'released';
      kill.className = s.kill_switch ? 'warn' : 'ok';
    } else {
      kill.textContent = '—';
      kill.className = '';
    }
    const acct = s.account || {};
    document.getElementById('balance').textContent = acct.balance ?? '—';
    document.getElementById('equity').textContent = acct.equity ?? '—';
    document.getElementById('positions').textContent = Array.isArray(s.positions) ? s.positions.length : '—';
    document.getElementById('updated').textContent = new Date().toLocaleTimeString();
  } catch {
    clearStatus();
    document.getElementById('mode').textContent = 'unavailable';
    document.getElementById('mode').className = 'err';
  }
}
document.getElementById('refresh').addEventListener('click', load);
load();
setInterval(load, 5000);
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js').catch(() => {});
}
