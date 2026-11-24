/* Arithva front end.
 *
 * Three screens over one API. Two browser capabilities do real work here:
 * the Web Speech API for listening and speaking, and the Web Crypto API for
 * officer signatures. Both need HTTPS (or localhost).
 */

const API = '';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let lang = 'en-IN';
let pendingConfirmation = null;   // an action waiting for the user's yes
let lastContext = {};             // carries amount/scheme between turns

/* ------------------------------------------------------------ navigation */

$$('nav button').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('nav button').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    $$('.screen').forEach((s) => s.classList.remove('active'));
    $('#' + btn.dataset.screen).classList.add('active');
    if (btn.dataset.screen === 'officer') loadApplications();
    if (btn.dataset.screen === 'dashboard') loadDashboard();
    if (btn.dataset.screen === 'audit') loadAudit();
  });
});

/* ------------------------------------------------------------------ speech */

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onresult = (event) => {
    const said = event.results[0][0].transcript;
    $('#textInput').value = said;
    ask(said);
  };
  recognition.onerror = (event) => {
    setMicState(false);
    // A refused microphone or a failed recognition is reported, not hidden.
    renderNotice(`Could not hear that (${event.error}). You can type instead.`);
  };
  recognition.onend = () => setMicState(false);
} else {
  $('#micHint').textContent = 'Voice needs Chrome or Edge. Typing works everywhere.';
}

function setMicState(listening) {
  $('#mic').classList.toggle('listening', listening);
  $('#micHint').textContent = listening ? 'Listening… release to send' : 'Hold to talk';
}

function startListening() {
  if (!recognition) return;
  recognition.lang = lang;
  try {
    recognition.start();
    setMicState(true);
  } catch (_) { /* already running */ }
}

function stopListening() {
  if (recognition) { try { recognition.stop(); } catch (_) {} }
}

const mic = $('#mic');
mic.addEventListener('mousedown', startListening);
mic.addEventListener('mouseup', stopListening);
mic.addEventListener('touchstart', (e) => { e.preventDefault(); startListening(); });
mic.addEventListener('touchend', (e) => { e.preventDefault(); stopListening(); });

/* Speaking: try the server's voice provider, fall back to the browser.
 *
 * The fallback is not error handling bolted on, it is the design. Arithva must
 * work with no API key, so a missing key, a quota limit or a slow network
 * changes how the answer sounds and nothing else.
 */

let currentAudio = null;
let voiceProviderConfigured = false;   // set once, on load

async function speak(text) {
  if (!text) return;
  stopSpeaking();

  // Skip the round trip entirely when no provider is configured. Without this
  // every utterance logs a 503 in the console, which looks like a fault and
  // is not one.
  if (!voiceProviderConfigured) {
    browserSpeak(text);
    showVoiceProvider('browser');
    return;
  }

  try {
    const response = await fetch(API + '/api/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language: lang }),
    });

    if (response.ok) {
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      currentAudio.onended = () => URL.revokeObjectURL(url);
      await currentAudio.play();
      showVoiceProvider('ElevenLabs');
      return;
    }
    // 503 means "use the browser voice", which is expected, not a failure.
  } catch (_) {
    // Network refused the request entirely. Same handling.
  }

  browserSpeak(text);
  showVoiceProvider('browser');
}

function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
}

function showVoiceProvider(name) {
  const el = $('#voiceProvider');
  if (!el) return;
  const premium = name === 'ElevenLabs';
  el.innerHTML = `<span class="chip ${premium ? 'ok' : 'syn'}">voice: ${escapeHtml(name)}</span>`;
}

/* Say on load which provider is configured, so the fallback is visible before
 * anyone has spoken a word. */
(async () => {
  try {
    const data = await fetch(API + '/api/speech/status').then((r) => r.json());
    voiceProviderConfigured = data.value.configured === true;
    showVoiceProvider(voiceProviderConfigured ? 'ElevenLabs' : 'browser');
  } catch (_) {
    voiceProviderConfigured = false;
    showVoiceProvider('browser');
  }
})();

$$('#langRow button').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('#langRow button').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    lang = btn.dataset.lang;
  });
});

/* --------------------------------------------------------------- asking */

$('#sendBtn').addEventListener('click', () => {
  const text = $('#textInput').value.trim();
  if (text) ask(text);
});

$('#textInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#sendBtn').click();
});

$$('#examples button').forEach((btn) => {
  btn.addEventListener('click', () => {
    $('#textInput').value = btn.textContent;
    ask(btn.textContent);
  });
});

async function ask(text, confirmed = false) {
  const context = { ...lastContext, confirmed, user_id: 'demo_citizen', area: 'Super Market' };
  const response = await fetch(API + '/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, context }),
  }).then((r) => r.json());

  // Remember an amount so "apply" in the next turn knows what it refers to.
  if (response.slots && response.slots.amount_inr) {
    lastContext.amount_inr = response.slots.amount_inr;
  }

  renderTurn(text, response);
  speak(response.spoken);

  if (response.needs_confirmation) {
    pendingConfirmation = { text };
  } else {
    pendingConfirmation = null;
  }
}

/* ------------------------------------------------------------- rendering */

function renderNotice(message) {
  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `<div class="answer">${escapeHtml(message)}</div>`;
  $('#answers').prepend(card);
}

function renderTurn(said, response) {
  const card = document.createElement('div');
  card.className = 'card';

  let html = `<div class="heard">You said: <b>${escapeHtml(said)}</b></div>`;
  html += `<div class="answer">${escapeHtml(response.spoken)}</div>`;

  if (response.needs_confirmation) {
    html += `
      <div class="confirm-box">
        <p><strong>Nothing has happened yet.</strong> Arithva reads back every action before
        it takes it.</p>
        <div class="confirm-actions">
          <button class="primary" data-confirm="yes">Yes, do it</button>
          <button class="ghost" data-confirm="no">No, cancel</button>
        </div>
      </div>`;
  }

  const result = response.tool_result;
  if (result) {
    html += renderToolResult(response.intent, result);
  }

  card.innerHTML = html;

  const yes = card.querySelector('[data-confirm="yes"]');
  if (yes) {
    yes.addEventListener('click', () => {
      yes.closest('.confirm-box').innerHTML = '<p class="muted">Confirmed.</p>';
      ask(said, true);
    });
    card.querySelector('[data-confirm="no"]').addEventListener('click', () => {
      card.querySelector('.confirm-box').innerHTML = '<p class="muted">Cancelled. Nothing was done.</p>';
      pendingConfirmation = null;
    });
  }

  $('#answers').prepend(card);
}

function renderToolResult(intent, result) {
  if (result.status === 'unavailable') {
    return `<div class="banner warn" style="margin:14px 0 0"><b>No answer available.</b>
      ${escapeHtml(result.reason)} Arithva does not fill this gap with a guess.</div>`;
  }
  if (result.status === 'refused') {
    return `<div class="banner warn" style="margin:14px 0 0"><b>Refused.</b>
      ${escapeHtml(result.reason)}</div>`;
  }

  const value = result.value || {};
  let body = '';

  if (intent === 'scheme' && value.eligible) {
    body += value.eligible.map((scheme) => `
      <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--line)">
        <strong>${escapeHtml(scheme.name)}</strong> <span class="chip ok">may be eligible</span>
        <div class="muted" style="margin:4px 0 8px">${escapeHtml(scheme.what_it_gives)}</div>
        <ul style="margin:0 0 8px;padding-left:18px;font-size:14px">
          ${scheme.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}
        </ul>
        <details>
          <summary>${scheme.documents.length} documents needed</summary>
          <ul style="font-size:13.5px;padding-left:18px">
            ${scheme.documents.map((d) => `<li>${escapeHtml(d)}</li>`).join('')}
          </ul>
        </details>
      </div>`).join('');
  }

  if (intent === 'loan' && value.emi_inr) {
    body += `
      <div class="stat-grid" style="margin-top:14px">
        <div class="stat"><div class="label">Monthly instalment</div>
          <div class="value">&#8377;${escapeHtml(value.emi_inr)}</div></div>
        <div class="stat"><div class="label">Total interest</div>
          <div class="value">&#8377;${escapeHtml(value.total_interest_inr)}</div></div>
        <div class="stat"><div class="label">Over</div>
          <div class="value">${value.tenure_months} mo</div></div>
      </div>`;
  }

  if (intent === 'job_post' && value.wage_check) {
    const wage = value.wage_check;
    if (wage.below_minimum) {
      body += `<div class="banner warn" style="margin:14px 0 0">
        <b>Below minimum wage.</b> ${escapeHtml(wage.flag)}</div>`;
    } else if (wage.checked) {
      body += `<div class="banner ok" style="margin:14px 0 0">
        At or above the &#8377;${wage.minimum_wage_inr} recorded for
        ${escapeHtml(wage.category.replace('_', ' '))} work.</div>`;
    }
  }

  if (intent === 'job_find' && value.jobs && value.jobs.length) {
    body += `<div class="scroll" style="margin-top:14px"><table><tbody>
      ${value.jobs.map((job) => `
        <tr>
          <td><strong>${escapeHtml(job.trade)}</strong><div class="muted">${escapeHtml(job.why || '')}</div></td>
          <td style="text-align:right;white-space:nowrap">
            &#8377;${job.wage_per_day_inr.toLocaleString('en-IN')}/day
            ${job.wage_flag ? '<div><span class="chip warn">below minimum</span></div>' : ''}
          </td>
        </tr>`).join('')}
    </tbody></table></div>
    <div class="muted" style="margin-top:8px">Contacts stay masked until both sides accept.</div>`;
  }

  if (intent === 'apply' && value.quorum) {
    body += `<div class="banner sim" style="margin:14px 0 0">
      <b>Sent to officers.</b> This needs ${escapeHtml(value.quorum.description)} signatures
      (${escapeHtml(value.quorum.band)}). The agent cannot approve it.
      Open the <strong>Officer</strong> tab to sign.</div>`;
  }

  // Provenance. Every answer says where its numbers came from.
  let source = `<div class="source-line"><b>Source:</b> ${escapeHtml(result.source || 'n/a')}`;
  if (result.as_of) source += ` &middot; <b>as of</b> ${escapeHtml(result.as_of)}`;
  if (result.confidence) source += `<br><b>Caveat:</b> ${escapeHtml(result.confidence)}`;
  if (result.disclaimer) source += `<br>${escapeHtml(result.disclaimer)}`;
  source += `</div>`;

  return body + source;
}

/* --------------------------------------------------------- officer keys */

const officerKeys = {};   // officerId -> CryptoKeyPair, demo only, never persisted

async function getKeyPair(officerId) {
  if (!officerKeys[officerId]) {
    officerKeys[officerId] = await crypto.subtle.generateKey(
      { name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify'],
    );
  }
  return officerKeys[officerId];
}

async function signPayload(officerId, payload) {
  const keyPair = await getKeyPair(officerId);
  const signature = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    keyPair.privateKey,
    new TextEncoder().encode(payload),
  );
  const jwk = await crypto.subtle.exportKey('jwk', keyPair.publicKey);
  return {
    signature_b64: btoa(String.fromCharCode(...new Uint8Array(signature))),
    public_key_jwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y },
  };
}

const OFFICERS = [
  { id: 'officer_1', name: 'Officer A (District)' },
  { id: 'officer_2', name: 'Officer B (Bank)' },
  { id: 'officer_3', name: 'Officer C (Taluk)' },
  { id: 'officer_4', name: 'Officer D (Audit)' },
  { id: 'officer_5', name: 'Officer E (Zonal)' },
];

$('#officerSelect').innerHTML = OFFICERS
  .map((o) => `<option value="${o.id}">${o.name}</option>`).join('');

$('#officerSelect').addEventListener('change', () => {
  $('#keyStatus').textContent = officerKeys[$('#officerSelect').value]
    ? 'Demo key ready' : 'Key generated on first signature';
});

/* ------------------------------------------------------- officer screen */

async function loadApplications() {
  const data = await fetch(API + '/api/applications').then((r) => r.json());
  const list = $('#applicationList');
  const rows = data.value || [];

  if (!rows.length) {
    list.innerHTML = `<div class="card"><div class="empty">
      No applications yet. Go to the Citizen tab and say
      &ldquo;apply for 1.5 lakh&rdquo; to create one.</div></div>`;
    return;
  }

  list.innerHTML = rows.map((app) => {
    const needed = app.signatures_required;
    const got = app.signatures_collected;
    const done = app.status === 'approved';
    const dots = Array.from({ length: needed }, (_, i) =>
      `<span class="dot ${i < got ? 'filled' : ''}"></span>`).join('');

    return `
      <div class="card">
        <div class="row-between">
          <div>
            <strong>#${app.id} &middot; ${escapeHtml(app.scheme_name)}</strong>
            <span class="chip ${done ? 'ok' : 'syn'}">${escapeHtml(app.status)}</span>
            <div class="muted" style="margin-top:3px">
              &#8377;${escapeHtml(app.amount_inr)} &middot; ${escapeHtml(app.band_label || '')}
              &middot; needs ${needed} signature${needed > 1 ? 's' : ''}
            </div>
            ${app.risk_flags.length
              ? `<div class="muted" style="margin-top:3px">Risk flags: ${app.risk_flags.map(escapeHtml).join(', ')}</div>`
              : ''}
            <div class="sig-dots">${dots}</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${done ? '' : `
              <button class="primary" data-sign="${app.id}">Sign as selected officer</button>
              <button class="danger" data-agent="${app.id}">Let the agent approve</button>`}
          </div>
        </div>
        <div id="sig-msg-${app.id}"></div>
      </div>`;
  }).join('');

  list.querySelectorAll('[data-sign]').forEach((btn) => {
    btn.addEventListener('click', () => signApplication(parseInt(btn.dataset.sign, 10)));
  });
  list.querySelectorAll('[data-agent]').forEach((btn) => {
    btn.addEventListener('click', () => agentTriesToApprove(parseInt(btn.dataset.agent, 10)));
  });
}

async function signApplication(applicationId) {
  const officerId = $('#officerSelect').value;
  const officer = OFFICERS.find((o) => o.id === officerId);
  const box = $(`#sig-msg-${applicationId}`);
  box.innerHTML = '<div class="muted" style="margin-top:10px">Signing…</div>';

  const payloadResponse = await fetch(`${API}/api/applications/${applicationId}/payload`)
    .then((r) => r.json());
  if (payloadResponse.status !== 'ok') {
    box.innerHTML = `<div class="banner warn" style="margin-top:10px">${escapeHtml(payloadResponse.reason)}</div>`;
    return;
  }

  const signed = await signPayload(officerId, payloadResponse.value.payload);
  $('#keyStatus').textContent = 'Demo key ready';

  const result = await fetch(API + '/api/applications/sign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      application_id: applicationId,
      officer_id: officerId,
      officer_name: officer.name,
      ...signed,
      decision: 'approve',
    }),
  }).then((r) => r.json());

  if (result.status !== 'ok') {
    box.innerHTML = `<div class="banner warn" style="margin-top:10px">${escapeHtml(result.reason)}</div>`;
    return;
  }

  const value = result.value;
  box.innerHTML = '';
  if (value.quorum_met) {
    notice('ok', `<b>Quorum met on #${applicationId}.</b>
      Signed by ${value.signed_by.map(escapeHtml).join(', ')}. Approved.
      <span class="chip sim">money movement simulated</span>`);
  } else {
    notice('sim', `<b>Signature verified on #${applicationId}.</b>
      ${value.signatures_collected} of ${value.signatures_required} collected.
      Switch officer above and sign again.`);
  }

  loadApplications();
}

async function agentTriesToApprove(applicationId) {
  const result = await fetch(`${API}/api/applications/${applicationId}/agent-approve`, {
    method: 'POST',
  }).then((r) => r.json());

  // Into the persistent notice area, not the per-application box: the refusal
  // is the thing being demonstrated, so it must survive the list refreshing.
  notice('warn', `<b>Agent refused on application #${applicationId}.</b>
    ${escapeHtml(result.reason)}`);
}

function notice(kind, html) {
  const box = document.createElement('div');
  box.className = `banner ${kind}`;
  box.innerHTML = html;
  $('#officerNotices').prepend(box);
}

/* ----------------------------------------------------------- dashboard */

async function loadDashboard() {
  const data = await fetch(API + '/api/applications').then((r) => r.json());
  const rows = data.value || [];

  const approved = rows.filter((r) => r.status === 'approved');
  const toNumber = (s) => parseFloat(String(s).replace(/,/g, '')) || 0;
  const requested = rows.reduce((sum, r) => sum + toNumber(r.amount_inr), 0);
  const sanctioned = approved.reduce((sum, r) => sum + toNumber(r.amount_inr), 0);

  $('#statGrid').innerHTML = `
    <div class="stat"><div class="label">Applications</div><div class="value">${rows.length}</div></div>
    <div class="stat"><div class="label">Requested</div>
      <div class="value">&#8377;${requested.toLocaleString('en-IN')}</div></div>
    <div class="stat"><div class="label">Sanctioned</div>
      <div class="value">&#8377;${sanctioned.toLocaleString('en-IN')}</div></div>
    <div class="stat"><div class="label">Released <span class="chip sim">sim</span></div>
      <div class="value">&#8377;${sanctioned.toLocaleString('en-IN')}</div></div>`;

  const table = $('#dashTable').querySelector('tbody');
  if (!rows.length) {
    table.innerHTML = `<tr><td><div class="empty">Nothing yet.</div></td></tr>`;
    return;
  }

  table.innerHTML = `
    <tr><th>#</th><th>Scheme</th><th>Amount</th><th>Signatures</th><th>Status</th></tr>
    ${rows.map((r) => `
      <tr>
        <td>${r.id}</td>
        <td>${escapeHtml(r.scheme_name)}<div class="muted">${escapeHtml(r.band_label || '')}</div></td>
        <td style="white-space:nowrap">&#8377;${escapeHtml(r.amount_inr)}</td>
        <td>${r.signatures_collected} / ${r.signatures_required}</td>
        <td><span class="chip ${r.status === 'approved' ? 'ok' : 'syn'}">${escapeHtml(r.status)}</span></td>
      </tr>`).join('')}`;
}

/* --------------------------------------------------------------- audit */

async function loadAudit() {
  const data = await fetch(API + '/api/audit').then((r) => r.json());
  const rows = data.value || [];
  const table = $('#auditTable').querySelector('tbody');

  if (!rows.length) {
    table.innerHTML = `<tr><td><div class="empty">The log is empty. Ask something first.</div></td></tr>`;
  } else {
    table.innerHTML = `
      <tr><th>#</th><th>When</th><th>Who</th><th>What</th><th>Hash</th></tr>
      ${rows.slice().reverse().map((row) => `
        <tr>
          <td>${row.id}</td>
          <td class="muted" style="white-space:nowrap">${escapeHtml(row.timestamp.replace('T', ' ').replace('+00:00', ''))}</td>
          <td class="muted">${escapeHtml(row.actor)}</td>
          <td><strong>${escapeHtml(row.action)}</strong>
            <details><summary>detail</summary><pre>${escapeHtml(JSON.stringify(row.detail, null, 2))}</pre></details>
          </td>
          <td class="mono muted">${escapeHtml(row.entry_hash.slice(0, 10))}&hellip;</td>
        </tr>`).join('')}`;
  }
  verifyChain();
}

async function verifyChain() {
  const data = await fetch(API + '/api/audit/verify').then((r) => r.json());
  const value = data.value;
  $('#chainStatus').innerHTML = value.intact
    ? `<span class="chip ok">chain intact</span> ${value.rows_checked} rows verified.`
    : `<span class="chip warn">chain broken</span> Row ${value.broken_at_row}: ${escapeHtml(value.reason)}`;
}

$('#verifyBtn').addEventListener('click', verifyChain);

$('#tamperBtn').addEventListener('click', async () => {
  const data = await fetch(API + '/api/audit').then((r) => r.json());
  const rows = data.value || [];
  if (!rows.length) { renderNotice('Nothing to tamper with yet.'); return; }

  const target = rows[Math.floor(rows.length / 2)];
  await fetch(API + '/api/audit/tamper', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entry_id: target.id,
      new_detail: { note: 'This row was edited by hand to prove the chain catches it.' },
    }),
  });
  loadAudit();
});

/* -------------------------------------------------------------- helpers */

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}
