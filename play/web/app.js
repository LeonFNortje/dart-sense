'use strict';

const $ = (sel) => document.querySelector(sel);
const MAX_PLAYERS = 8;
const DART_COLOURS = ['#00e5ff', '#ffe600', '#ff2d95'];
const ICON_GEAR = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>';
const ICON_X = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';

async function api(path, body) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const initials = (name) => name.trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || '?';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ======================= SETUP ======================= */
const DEFAULTS = {
  players: ['Player 1', 'Player 2'], format: 'first_to', unit: 'legs', target: 3,
  start_score: '501', custom: 170, in_mode: 'straight', out_mode: 'double',
  camera: '192.168.0.8:8080', call_scores: true, save_training: false,
};
let setup = { ...DEFAULTS };
try { setup = { ...DEFAULTS, ...JSON.parse(localStorage.getItem('dartsense-setup') || '{}') }; } catch (e) { /* storage unavailable */ }
const saveSetup = () => { try { localStorage.setItem('dartsense-setup', JSON.stringify(setup)); } catch (e) { /* ignore */ } };

function renderPlayers() {
  const list = $('#player-list');
  list.innerHTML = '';
  setup.players.forEach((name, i) => {
    const chip = document.createElement('div');
    chip.className = 'player-chip';
    chip.innerHTML = `
      <div class="avatar">${esc(initials(name))}
        <button class="badge edit" title="Rename">${ICON_GEAR}</button>
        <button class="badge remove" title="Remove">${ICON_X}</button>
      </div>
      <input value="${esc(name)}" maxlength="16" aria-label="Player ${i + 1} name">`;
    const input = chip.querySelector('input');
    input.addEventListener('input', () => {
      setup.players[i] = input.value;
      chip.querySelector('.avatar').firstChild.nodeValue = initials(input.value);
      saveSetup();
    });
    chip.querySelector('.edit').addEventListener('click', () => { input.focus(); input.select(); });
    chip.querySelector('.remove').addEventListener('click', () => {
      if (setup.players.length > 1) { setup.players.splice(i, 1); saveSetup(); renderPlayers(); }
    });
    list.appendChild(chip);
  });
  $('#player-count').textContent = setup.players.length;
  $('#add-player').disabled = setup.players.length >= MAX_PLAYERS;
}

function renderSettings() {
  document.querySelectorAll('#setup .seg[data-setting]').forEach((seg) => {
    const value = String(setup[seg.dataset.setting]);
    seg.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.value === value));
  });
  $('#target').textContent = setup.target;
  $('#custom-score').value = setup.custom;
  const unit = setup.unit === 'sets' ? 'sets' : 'legs';
  const toWin = setup.format === 'first_to' ? setup.target : Math.floor(setup.target / 2) + 1;
  $('#format-hint').textContent = (setup.format === 'first_to' ? `First to ${setup.target} ${unit}` : `Best of ${setup.target} ${unit} (first to ${toWin})`)
    + (setup.unit === 'sets' ? ' · each set is first to 3 legs' : '');
  $('#camera-ip').value = setup.camera;
  $('#call-scores').checked = setup.call_scores;
  $('#save-training').checked = setup.save_training;
}

$('#add-player').addEventListener('click', () => {
  if (setup.players.length >= MAX_PLAYERS) return;
  setup.players.push(`Player ${setup.players.length + 1}`);
  saveSetup();
  renderPlayers();
  const inputs = document.querySelectorAll('#player-list input');
  inputs[inputs.length - 1].select();
});

document.querySelectorAll('#setup .seg[data-setting]').forEach((seg) => {
  seg.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    setup[seg.dataset.setting] = btn.dataset.value;
    if (seg.dataset.setting === 'format' && setup.format === 'best_of' && setup.target % 2 === 0) setup.target += 1;
    saveSetup();
    renderSettings();
  });
});

function stepTarget(dir) {
  const step = setup.format === 'best_of' ? 2 : 1;
  setup.target = Math.min(21, Math.max(1, setup.target + dir * step));
  saveSetup();
  renderSettings();
}
$('#target-up').addEventListener('click', () => stepTarget(1));
$('#target-down').addEventListener('click', () => stepTarget(-1));
$('#custom-score').addEventListener('input', (e) => { setup.custom = parseInt(e.target.value, 10) || 0; setup.start_score = 'custom'; saveSetup(); renderSettings(); });
$('#camera-ip').addEventListener('input', (e) => { setup.camera = e.target.value.trim(); $('#camera-status').className = 'dot'; saveSetup(); });
$('#call-scores').addEventListener('change', (e) => { setup.call_scores = e.target.checked; saveSetup(); });
$('#save-training').addEventListener('change', (e) => { setup.save_training = e.target.checked; saveSetup(); });

async function checkCamera() {
  const dot = $('#camera-status');
  dot.className = 'dot';
  dot.title = 'checking…';
  const res = await fetch(`/api/camera-check?ip=${encodeURIComponent(setup.camera)}`).then((r) => r.json()).catch(() => ({ ok: false }));
  dot.className = `dot ${res.ok ? 'ok' : 'bad'}`;
  dot.title = res.ok ? 'camera reachable' : `camera not reachable ${res.error || ''}`;
  return res.ok;
}
$('#camera-check').addEventListener('click', checkCamera);

$('#start-game').addEventListener('click', async () => {
  const err = $('#setup-error');
  err.textContent = '';
  const startScore = setup.start_score === 'custom' ? setup.custom : parseInt(setup.start_score, 10);
  if (!(startScore >= 2)) { err.textContent = 'Enter a custom start score of 2 or more'; return; }
  const btn = $('#start-game');
  btn.disabled = true;
  try {
    await api('/api/start', {
      players: setup.players, start_score: startScore, target: setup.target, unit: setup.unit, format: setup.format,
      in_mode: setup.in_mode, out_mode: setup.out_mode, camera: setup.camera, call_scores: setup.call_scores,
      save_training: setup.save_training,
    });
    showGame();
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
});

/* ======================= GAME ======================= */
let current = null; // latest state from the server
let lastGameJson = '';
let lastMessageId = null;
let selected = null; // {kind, index} of the overlay point being edited
let dragging = false;

function showGame() {
  $('#setup').classList.add('hidden');
  $('#game').classList.remove('hidden');
  $('#camera-img').src = `/stream.mjpg?t=${Date.now()}`;
  lastGameJson = '';
  $('#score-input').focus();
}
function showSetup() {
  $('#game').classList.add('hidden');
  $('#setup').classList.remove('hidden');
  $('#camera-img').removeAttribute('src');
}

function renderCards(game) {
  const box = $('#player-cards');
  const n = game.players.length;
  box.classList.toggle('compact', n >= 3);
  box.classList.toggle('tiny', n >= 6);
  if (box.children.length !== n) {
    box.innerHTML = game.players.map(() => `
      <div class="pcard">
        <div class="who"><div class="avatar"></div><div class="name"></div></div>
        <div class="score"></div>
        <div class="legs"><span class="starter" title="Threw first this leg"></span><span class="count sets"></span><span class="count legs-won"></span></div>
        <div class="stats">
          <span>3-dart avg.</span><b class="avg"></b>
          <span>Last score</span><b class="last"></b>
          <span>Darts thrown</span><b class="thrown"></b>
        </div>
        <div class="dots"><i></i><i></i></div>
      </div>`).join('');
  }
  game.players.forEach((p, i) => {
    const card = box.children[i];
    card.classList.toggle('active', i === game.current && game.winner === null);
    card.querySelector('.avatar').textContent = initials(p.name);
    card.querySelector('.name').textContent = p.name;
    card.querySelector('.score').textContent = p.score;
    card.querySelector('.starter').classList.toggle('on', i === game.leg_starter);
    const sets = card.querySelector('.count.sets');
    sets.classList.toggle('hidden', game.unit !== 'sets');
    sets.innerHTML = `${p.sets}<small>sets</small>`;
    card.querySelector('.count.legs-won').innerHTML = game.unit === 'sets' ? `${p.legs}<small>legs</small>` : p.legs;
    card.querySelector('.avg').textContent = p.average.toFixed(2);
    card.querySelector('.last').textContent = p.last_score ?? '–';
    card.querySelector('.thrown').textContent = p.darts_thrown;
  });
}

function renderHistory(game) {
  const n = game.players.length;
  const perPlayer = game.players.map((_, i) => game.leg_history.filter((v) => v.player === i));
  const done = Math.max(0, ...perPlayer.map((v) => v.length));
  const curRound = perPlayer[game.current].length + 1;
  const rounds = game.winner === null ? Math.max(done, curRound) : done;
  const table = $('#history');
  const panel = table.parentElement;
  const mirrored = n === 2;
  table.className = `history ${mirrored ? 'mirrored' : 'generic'}`;
  panel.classList.toggle('generic', !mirrored);

  const cell = (v, isNow) => {
    if (!v) return isNow ? { rem: '<span class="dots3">•••</span>', scored: '' } : { rem: '', scored: '' };
    const cls = v.bust ? 'bust-cell' : v.checkout ? 'checkout' : '';
    return { rem: `<span class="${cls}">${v.remaining}</span>`, scored: `<span class="${cls}">${v.bust ? 'BUST' : v.scored}</span>` };
  };

  let html = '';
  if (!mirrored) {
    html += `<tr><th></th>${game.players.map((p) => `<th class="pname">${esc(p.name)}</th>`).join('')}</tr>`;
  }
  for (let r = rounds; r >= 1; r--) {
    const isNow = game.winner === null && r === curRound;
    const cells = perPlayer.map((vs) => cell(vs[r - 1], isNow));
    const badge = `<td class="round"><span>#${r}</span></td>`;
    if (mirrored) {
      html += `<tr class="${isNow ? 'now' : ''}"><td class="scored">${cells[0].scored}</td><td class="rem">${cells[0].rem}</td>${badge}<td class="rem">${cells[1].rem}</td><td class="scored">${cells[1].scored}</td></tr>`;
    } else {
      html += `<tr class="${isNow ? 'now' : ''}">${badge}${cells.map((c) => `<td class="rem"><span class="cell-scored">${c.scored}</span>${c.rem}</td>`).join('')}</tr>`;
    }
  }
  table.innerHTML = html;
}

function renderDetected(state) {
  const box = $('#detected');
  const game = state.game;
  const visit = state.visit;
  if (!visit || game.winner !== null) {
    box.innerHTML = game.winner !== null ? '<button class="ghost" id="new-match">New match</button>' : '';
    const nm = $('#new-match');
    if (nm) nm.onclick = endMatch;
    return;
  }
  const chips = [0, 1, 2].map((i) => {
    const d = visit.darts[i];
    return d ? `<span class="chip" style="border-color:${DART_COLOURS[i]}">${d}</span>` : '<span class="chip empty">–</span>';
  }).join('');
  let summary = '';
  const ev = visit.evaluation;
  if (ev) {
    summary = ev.bust ? '<span class="total bust">BUST</span>'
      : ev.checkout ? `<span class="total finish">${ev.scored}</span><span class="finish">GAME SHOT</span>`
        : `<span class="total">${ev.scored}</span><span class="note">leaves ${ev.remaining}</span>`;
    if (!ev.opened && game.in_mode !== 'straight') summary += `<span class="note">needs a ${game.in_mode} to start</span>`;
  }
  const note = visit.waiting_for_clear && state.live && state.live.board_found ? '<span class="note">pull the darts out to confirm</span>' : '';
  const commit = visit.darts.length ? '<button class="ghost commit" id="commit-btn" title="Commit now (Enter)">Commit</button>' : '';
  box.innerHTML = chips + summary + note + commit;
  const cb = $('#commit-btn');
  if (cb) cb.onclick = () => api('/api/commit');
}

function renderOverlay(state) {
  if (dragging) return;
  const svg = $('#overlay');
  const live = state.live;
  if (!live) { svg.innerHTML = ''; return; }
  let html = '';
  if ($('#show-boxes').checked && state.view === 'imageplane') {
    const names = { 0: '20', 1: '3', 2: '11', 3: '6', 4: 'dart', 5: '9', 6: '15' };
    html += live.boxes.map((b) => `<text class="box" x="${b.x}" y="${b.y - 0.012}" text-anchor="middle">${names[b.cls]} ${b.conf}</text>`).join('');
  }
  html += live.calibration.map((c) => {
    const sel = selected && selected.kind === 'calibration' && selected.index === c.index ? ' sel' : '';
    return `<circle class="pt cal${sel}" data-kind="calibration" data-index="${c.index}" cx="${c.x}" cy="${c.y}" r="0.012"/>`;
  }).join('');
  html += live.darts.map((d, i) => {
    const sel = selected && selected.kind === 'dart' && selected.index === i ? ' sel' : '';
    return `<circle class="pt${sel}" data-kind="dart" data-index="${i}" cx="${d.x}" cy="${d.y}" r="0.014" stroke="${DART_COLOURS[i]}" fill="rgba(0,0,0,.2)"/>`
      + `<text class="lbl" x="${d.x + 0.02}" y="${d.y + 0.045}">${esc(d.label)}</text>`;
  }).join('');
  svg.innerHTML = html;

  const status = $('#cam-status');
  if (!live.connected && live.error) {
    status.textContent = 'Camera not connected';
    status.className = 'cam-status off';
  } else if (!live.board_found) {
    status.textContent = 'Board not detected – aim the camera at the board';
    status.className = 'cam-status off';
  } else {
    status.textContent = `Board detected · ${Math.round(live.fps)} fps`;
    status.className = 'cam-status';
  }
}

function renderTraining(training) {
  const el = $('#training-count');
  el.classList.toggle('hidden', !training);
  if (!training) return;
  const n = training.corrected + training.auto;
  el.textContent = `${n} training frame${n === 1 ? '' : 's'} saved`;
  el.title = `${training.corrected} corrected by hand, ${training.auto} as detected`;
}

function render(state) {
  current = state;
  renderTraining(state.training);
  const game = state.game;
  if (!game) { if (!$('#game').classList.contains('hidden')) showSetup(); return; }
  if ($('#game').classList.contains('hidden')) showGame();

  const gameJson = JSON.stringify(game);
  if (gameJson !== lastGameJson) {
    lastGameJson = gameJson;
    renderCards(game);
    renderHistory(game);
    const name = game.players[game.winner ?? game.current].name;
    $('#turn-banner').textContent = game.winner !== null ? `${name} wins the match!` : `${name}'s turn to throw!`;
    $('#score-input').disabled = game.winner !== null;
    $('#undo').disabled = !game.can_undo;
  }
  renderDetected(state);
  renderOverlay(state);
  document.querySelectorAll('#view-mode button').forEach((b) => b.classList.toggle('active', b.dataset.value === state.view));

  if (state.message && state.message.id !== lastMessageId) {
    const first = lastMessageId === null && lastGameJson === '';
    lastMessageId = state.message.id;
    if (!first) showToast(state.message.text);
  }
}

let toastTimer = null;
function showToast(text) {
  const t = $('#toast');
  t.textContent = text;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 3500);
}

/* ---- score entry ---- */
$('#score-input').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 3); });
$('#score-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#score-input');
  const value = input.value.trim();
  try {
    if (value === '') {
      if (current && current.visit && current.visit.darts.length) await api('/api/commit');
    } else {
      await api('/api/score', { points: parseInt(value, 10) });
      input.value = '';
    }
  } catch (err) {
    showToast(err.message);
  }
});
$('#undo').addEventListener('click', () => api('/api/undo'));

/* ---- camera overlay editing ---- */
const overlay = $('#overlay');
let lastMove = 0;
function pointFromEvent(e) {
  const r = overlay.getBoundingClientRect();
  return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) };
}
function sendMove(el, x, y, force) {
  el.setAttribute('cx', x);
  el.setAttribute('cy', y);
  const now = performance.now();
  if (force || now - lastMove > 50) {
    lastMove = now;
    api('/api/dart', { action: 'move', kind: el.dataset.kind, index: +el.dataset.index, x, y });
  }
}
overlay.addEventListener('pointerdown', (e) => {
  const el = e.target.closest('.pt');
  if (!el) { selected = null; return; }
  selected = { kind: el.dataset.kind, index: +el.dataset.index };
  dragging = true;
  overlay.setPointerCapture(e.pointerId);
  overlay.querySelectorAll('.pt').forEach((p) => p.classList.toggle('sel', p === el));
  overlay.dragEl = el;
});
overlay.addEventListener('pointermove', (e) => {
  if (!dragging || !overlay.dragEl) return;
  const { x, y } = pointFromEvent(e);
  sendMove(overlay.dragEl, x, y, false);
});
overlay.addEventListener('pointerup', (e) => {
  if (dragging && overlay.dragEl) {
    const { x, y } = pointFromEvent(e);
    sendMove(overlay.dragEl, x, y, true);
  }
  dragging = false;
  overlay.dragEl = null;
});

$('#add-dart').addEventListener('click', () => api('/api/dart', { action: 'add' }));
$('#view-mode').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) api('/api/view', { mode: b.dataset.value });
});
$('#toggle-camera').addEventListener('click', () => $('#game').classList.toggle('no-camera'));

document.addEventListener('keydown', (e) => {
  if ($('#game').classList.contains('hidden')) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); api('/api/undo'); return; }
  if (e.key === 'a' && !e.ctrlKey) { e.preventDefault(); api('/api/dart', { action: 'add' }); return; }
  if (!selected) return;
  if (e.key === 'Delete') {
    api('/api/dart', { action: 'delete', kind: selected.kind, index: selected.index });
    selected = null;
    return;
  }
  const nudge = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }[e.key];
  if (nudge) {
    e.preventDefault();
    const el = overlay.querySelector(`.pt[data-kind="${selected.kind}"][data-index="${selected.index}"]`);
    if (el) sendMove(el, +el.getAttribute('cx') + nudge[0] / 720, +el.getAttribute('cy') + nudge[1] / 720, true);
  }
});

/* ---- end match ---- */
async function endMatch() {
  await api('/api/end');
  showSetup();
}
$('#end-match').addEventListener('click', () => $('#end-dialog').showModal());
$('#end-cancel').addEventListener('click', () => $('#end-dialog').close());
$('#end-confirm').addEventListener('click', async () => { $('#end-dialog').close(); await endMatch(); });

/* ---- boot ---- */
renderPlayers();
renderSettings();
const events = new EventSource('/events');
events.onmessage = (e) => render(JSON.parse(e.data));
