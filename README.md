# Arithva

**A voice-first assistant for rural micro-entrepreneurs, built on MCP.**
*wHACKiest 2026, Track 1: Make MCP Matter.*

Arithva is one microphone button. A shop owner in Kalaburagi speaks in Kannada,
Hindi or English, and the assistant answers in the same language, out loud.
Behind that button are five MCP servers. The model works out what the user
meant; the tools produce every number; anything involving money stops and waits
for human officers to sign.

> *Arithva*, from the Sanskrit *artha*, economic value.

---

## The idea in one line

> The AI understands. The tools decide. Officers sign.

Generic chatbots answer questions about schemes in general terms and will
happily invent an interest rate. Government portals have the real rules but
expect typing, literacy and a form. Arithva puts a microphone in front of real
rules, and refuses to let the model near the arithmetic.

## What it does

| | |
|---|---|
| **Discover** | "Which scheme can I get for a new tea stall?" Eligibility is decided by a curated rules file, each rule carrying its source. |
| **Plan** | "What would I pay each month for 1.5 lakh?" EMI computed in integer paise, read aloud as *"four thousand eight hundred seventy five rupees"*. |
| **Apply** | The agent drafts the application and reads it back. Nothing is submitted until the user says yes. |
| **Approve** | The application goes to an officer queue. The number of signatures needed rises with the amount and the risk. **The agent has no approval capability at all.** |
| **Track** | A dashboard showing requested, sanctioned and released, with the approval chain behind each one. |
| **Work** | "I need two painters for three days." Offers below the minimum wage for that trade are flagged. Contacts stay masked until both sides accept. |
| **Every day** | "Will it be hot tomorrow?" Forecast plus what it means for that business, including local events like the Urs or the marriage season. |

## Three design decisions

**1. The model never produces a number.**
Every rupee figure comes from `backend/tools/money.py`, in integer paise, never
floats. The language model's entire job is turning speech into a tool call and
reading the result back. If a tool cannot answer, it returns `unavailable` with
a reason, and the assistant says so rather than filling the gap.

```python
>>> calculate_emi(amount_inr=150000, tenure_months=36)
{'status': 'ok',
 'value': {'emi_inr': '4,875.37',
           'emi_spoken': 'four thousand eight hundred seventy five rupees',
           ...},
 'source': "Computed in integer paise by Arithva's loan tool (reducing balance)",
 'confidence': 'Rate of 10.5% a year is an assumed design value, not a quote...'}
```

**2. Adaptive quorum, enforced structurally.**
Money actions need human signatures, and more money means more signatures:

| Amount | Signatures | Plus a risk flag |
|---|---|---|
| Below ₹50,000 | 1 of 1 | +1 signer each |
| ₹50,000 – ₹5,00,000 | 2 of 3 | +1 signer each |
| Above ₹5,00,000 | 3 of 5 | +1 signer each |

These bands live in `data/quorum_rules.json`. They are **our own design values
for this prototype, not legal or banking thresholds** — a real deployment loads
the lender's own policy.

The guardrail is not a prompt instruction telling the model to behave. There is
**no approve function anywhere on the agent's surface**. Look at
`backend/mcp_servers/approvals_server.py`: it exposes `quorum_for`,
`prepare_application` and `application_status`, and nothing else. Approval
happens only when enough valid ECDSA P-256 signatures arrive from officer keys
and verify server-side. There is a test asserting the tool does not exist.

The officer screen has a button labelled **"Let the agent approve"**. It always
refuses, and the refusal is written to the audit log. A guardrail nobody can
watch being enforced is only a claim.

**3. The audit log is checkable, not trustworthy.**
Every action is hash-chained. Editing any past row breaks the chain from that
row onward. There is a **"Tamper with a row"** button that edits a past entry
without recomputing its hash, so you can press *Verify* and watch it name the
broken row. (A single-process SQLite chain is not a distributed ledger, and
nothing here pretends otherwise. It makes silent edits detectable.)

---

## Voice: a provider chain, not a dependency

Spoken replies try **ElevenLabs** first and fall back to the browser's own
speech synthesis. The fallback is the design, not error handling bolted on:
Arithva runs with no API key at all, so a missing key, an expired one, a quota
limit or a slow network changes how the answer *sounds* and nothing else. The
citizen screen shows which voice is actually speaking.

To enable it, copy `.env.example` to `.env` and set `ELEVENLABS_API_KEY`.
`.env` is gitignored and must never be committed.

Adding a provider means adding a function that returns audio or `unavailable`,
and putting it in the chain. Nothing else changes.

## Running it

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open **http://localhost:8000**. No API key needed for anything except the live
weather call.

Voice and officer signing both use browser APIs that require a secure context,
so they work on `localhost` and over HTTPS, but not over plain HTTP from
another machine. Speech recognition currently needs Chrome or Edge; typing
works in every browser.

### The demo path

1. **Citizen** tab → press a sample question or hold the mic and speak.
2. Ask about the weather, then a scheme, then an EMI. Note the source line
   under every answer.
3. Say *"I need 2 painters for 3 days at 800 rupees"* → it reads the action
   back and waits. Nothing happens until you confirm.
4. Say *"apply for 1.5 lakh"* → an application is prepared and sent to officers.
5. **Officer** tab → press **"Let the agent approve"**. Watch it refuse.
6. Sign as Officer A, switch to Officer B, sign again, and again until quorum
   is met. Each signature is a real ECDSA signature generated in your browser.
7. **Dashboard** tab → the sanctioned amount appears, labelled simulated.
8. **Audit log** tab → *Verify chain*, then *Tamper with a row*, then verify
   again.

### Tests

```bash
pytest backend/tests/ -v
```

21 tests covering the money arithmetic, intent routing, the confirmation step,
quorum escalation, signature forgery and replay, and the tamper-evident log.
If these pass, the demo path works.

### The MCP servers

Each one speaks stdio and can be mounted in any MCP client:

```bash
python -m backend.mcp_servers.scheme_server
python -m backend.mcp_servers.loan_server
python -m backend.mcp_servers.weather_server
python -m backend.mcp_servers.jobs_server
python -m backend.mcp_servers.approvals_server
```

They wrap the same functions in `backend/tools/` that the web app calls, so an
MCP client and the web app get identical answers from identical code.

---

## What is real and what is not

We would rather state this plainly than have a judge find it.

| | |
|---|---|
| **Real** | The MCP servers, the EMI arithmetic, the eligibility logic, the ECDSA signature generation and verification, the quorum escalation, the hash-chained audit log, the live weather call, browser speech in and out, the ElevenLabs integration and its fallback chain. |
| **Simulated** | All money movement. Nothing is disbursed anywhere. The dashboard shows what *would* move. |
| **Synthetic** | Seed jobs, demo employers and workers, the CSC and bank branch list. Labelled in the UI. |
| **Demo-only** | Officer signing keys are generated in the browser for the demo. A real deployment would use officers' own managed keys, never keys created by this application. |
| **Needs verifying** | The minimum-wage table is placeholder data and must be replaced from the Karnataka gazette notification. Several scheme rules are marked `VERIFY` in `data/schemes.json`. Local event dates need confirming locally. |
| **Not built** | WhatsApp and IVR channels, mandi prices, document scanning, the daily voice brief. These are roadmap, and the deck shows them as roadmap. |

Kannada speech accuracy on noisy shop audio is **untested**, in both
directions. Speech *recognition* is the browser's Web Speech API; Bhashini or
AI4Bharat would likely do better and that is future work, not a claim. For
speech *output*, whether ElevenLabs handles Kannada well enough to rely on is
**unverified** — listen to a sample before claiming it in a demo. The browser
fallback means neither question breaks the product.

## Privacy

Consent-first, designed to align with the DPDP Act 2023 — *designed to align*,
not *compliant*; nobody has audited this. No Aadhaar numbers are stored. Phone
numbers stay masked in Jobs until both sides accept.

## Layout

```
backend/
  agent.py              intent routing, read-back, confirmation gate
  main.py               FastAPI app and API
  db.py                 SQLite storage
  audit.py              hash-chained log and its verifier
  tools/                the actual capabilities
    money.py            integer-paise arithmetic, Indian number words
    scheme_tool.py      eligibility against the rules file
    loan_tool.py        EMI and subsidy
    weather_tool.py     forecast plus deterministic advice bands
    jobs_tool.py        posting, matching, wage flag, masked contacts
    approvals_tool.py   adaptive quorum, ECDSA verification
  mcp_servers/          five MCP servers wrapping the tools above
  tests/
data/                   rules and reference data, each file citing its source
frontend/               three screens, no build step
```

## Team

Trust The Process — Praneel Reddy, Harshvardhan S Jaisingh, Jordan Varghese,
Md Mujtaba Kashif. Ramaiah Institute of Technology.

## Licence

MIT.
