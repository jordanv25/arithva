# Working on Arithva

Read this before changing anything. It is the shared context for everyone on
the team, human or agent, so that four people working in parallel make the same
assumptions.

## What this project is

A voice-first assistant for rural micro-entrepreneurs, built on MCP, for
wHACKiest 2026 Track 1. A shop owner speaks in Kannada, Hindi or English; the
assistant answers aloud; five MCP servers do the actual work.

**The one-line summary that governs every design decision:**

> The AI understands. The tools decide. Officers sign.

## The three invariants

These are the pitch. Breaking one does not just introduce a bug, it removes the
reason the project is interesting. Do not break them without the team agreeing
first.

### 1. The model never produces a number

Every rupee figure comes from a tool, computed in integer paise in
`backend/tools/money.py`. The language model's entire job is turning speech
into a tool call and reading the result back.

- Never use floats for money. Never let the model do arithmetic.
- Never hardcode a scheme rule, wage or rate in Python. It belongs in `data/`.
- If a tool cannot answer, it returns `unavailable` with a reason, and the
  assistant says that reason out loud. We never fill a gap with a plausible
  guess.

### 2. The agent cannot approve anything involving money

There is **no approve function on the agent's surface**. Look at
`backend/mcp_servers/approvals_server.py`: it exposes `quorum_for`,
`prepare_application` and `application_status`, and nothing else.

- Never add an approve, disburse or release tool to an MCP server.
- Approval happens only when enough valid ECDSA P-256 signatures from officer
  keys verify server-side, in `approvals_tool.submit_signature`.
- `agent_attempt_approve` always refuses and logs. It exists so the guardrail
  can be demonstrated. Do not "fix" it.
- `test_approvals_server_exposes_no_approve_tool` asserts this. If that test
  fails, something important broke.

### 3. Every answer carries its source

Tool results are built with `ok()` / `unavailable()` / `refused()` from
`backend/tools/registry.py`, which attach a source and a timestamp. The UI
renders the source line under every answer.

- A new tool returns results through those helpers, never a bare dict.
- Uncertain data says so. Several scheme rules are marked `VERIFY` and the wage
  table is marked `PLACEHOLDER`. Keep those markers until someone confirms the
  figures against the official source.

## Honesty rules for the demo

We would rather a judge hear it from us than find it themselves.

- Anything simulated is labelled **SIMULATED** in the UI. All money movement is
  simulated; nothing is disbursed.
- Anything synthetic is labelled **SYNTHETIC**. Seed jobs, demo employers and
  the centre list are synthetic.
- Officer signing keys are generated in the browser for the demo and labelled
  as such.
- Never add a feature that looks real but is faked behind the scenes. Either
  build it honestly or show it on the roadmap slide.
- The "what is real and what is not" table in `README.md` is part of the
  submission. If you add a feature, update that table in the same commit.

## Architecture

```
frontend/          three screens, plain HTML/CSS/JS, no build step
  index.html       citizen (mic), officer (signing), dashboard, audit log
  app.js           Web Speech API for voice, Web Crypto for signatures
backend/
  main.py          FastAPI app, all HTTP endpoints
  agent.py         intent routing, read-back, the confirmation gate
  db.py            SQLite storage
  audit.py         hash-chained log and its verifier
  tools/           the capabilities themselves
    money.py       integer-paise arithmetic, Indian number words
    registry.py    ok() / unavailable() / refused(), data file loading
    *_tool.py      scheme, loan, weather, jobs, approvals
  mcp_servers/     five MCP servers wrapping tools/ — no logic of their own
data/              rules and reference data, every file citing its source
```

**The important structural rule:** `mcp_servers/` and `main.py` are both thin
wrappers over `tools/`. Business logic lives in `tools/` only, so the MCP
client and the web app can never disagree. If you add a capability, write it in
`tools/`, then expose it in both places.

## Conventions

- Data, not code. Thresholds, rules, wages and rates live in `data/*.json`.
- Every data file carries `_note`, `source` and `confidence` fields.
- State-changing actions go through the confirmation gate in `agent.py`:
  `confirmation_for()` returns the sentence the user must agree to. Read-only
  questions skip it — asking the weather should not need ceremony.
- Money in, money out: `rupees_to_paise()` at the boundary,
  `paise_to_rupees_str()` for display, `speak_rupees()` for anything spoken.
- Keep the frontend build-free. No npm, no bundler. It must start with one
  command on any laptop.

## Before you commit

```powershell
python -m pytest backend/tests/ -q
```

21 tests cover the money arithmetic, intent routing, the confirmation gate,
quorum escalation, signature forgery and replay, and the tamper-evident log.
**If these pass, the demo path works.** If you change behaviour deliberately,
update the test in the same commit.

Then read your own diff before committing:

```powershell
git diff
```

## Who owns what

Agents touch more lines than humans do, so two people pointing agents at the
same file is the main cause of merge pain. Stay in your area.

| Area | Files |
|---|---|
| Tools and rules | `backend/tools/`, `data/` |
| Agent and routing | `backend/agent.py` |
| Frontend | `frontend/` |
| API and storage | `backend/main.py`, `backend/db.py` |

`main.py` and `db.py` are the shared ones. Say something in the group before
editing them.

Branch per person, merge into `main` every two or three hours rather than once
at the end:

```powershell
git checkout main
git pull
git checkout -b yourname/what-youre-doing
```

## Not built, and deliberately so

WhatsApp and IVR channels, mandi price lookups, document scanning, the daily
voice brief. These are on the roadmap slide. Do not half-build one during the
hackathon — a convincing fake is worse for us than an honest roadmap.

## Known gaps

- The minimum wage table in `data/wage_table.json` is placeholder data and must
  be replaced from the Karnataka gazette notification.
- Several scheme rules in `data/schemes.json` are marked `VERIFY`.
- Local event dates need confirming locally.
- Kannada speech accuracy on noisy audio is untested. The browser's Web Speech
  API is what runs today.
