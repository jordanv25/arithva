# Hackathon build plan

What exists now, what each person owns on the day, and what we deliberately
leave unbuilt.

## Where the prototype already stands

Working end to end: the voice loop, five MCP servers, scheme matching, EMI in
integer paise, live weather with deterministic advice, job posting with the
wage flag, adaptive quorum with real ECDSA signatures, the hash-chained audit
log, and three screens. 21 tests pass.

So the day is not about getting something running. It is about depth, the
things marked `VERIFY`, and the demo being solid.

## Ownership

Agents touch more lines per change than humans do, so overlapping on a file is
the main source of merge pain. One person per area.

| Person | Area | Files |
|---|---|---|
| | Tools and rules | `backend/tools/`, `data/` |
| | Agent and routing | `backend/agent.py` |
| | Frontend | `frontend/` |
| | API, storage, pitch | `backend/main.py`, `backend/db.py`, deck, video |

Fill in the names before you start. `main.py` and `db.py` are shared — say
something in the group before touching them.

## Priority order

Work down this list. Anything below the line is a bonus, not a plan.

**1. Replace the placeholder data.** This is the highest-value work and nobody
needs to write code for it.
- `data/wage_table.json` — every figure, from the Karnataka gazette
  notification for the right zone and scheduled employment.
- `data/schemes.json` — each rule marked `VERIFY`, against the official portal.
- `data/events_kalaburagi.json` — confirm the event windows locally.

Remove the `PLACEHOLDER` and `VERIFY` markers only once a figure is confirmed
against a named source, and record that source in the file.

**2. Make the voice loop solid.** This is the moat and it is what gets filmed.
- Test real Kannada and Hindi speech on an actual phone, not just the laptop.
- Handle the obvious failure cases: nothing heard, half a sentence, mixed
  languages in one utterance.
- Check the spoken amounts sound right in each language.

**3. Deepen the pipeline.** Pick one, finish it properly.
- Worker side of Jobs: apply by voice, employer accepts, contacts unmask.
- Subsidy estimate wired into the citizen screen for PMEGP.
- Application detail view showing the signature chain.

**4. Harden the demo.** Seed a clean database, walk the path five times, and
fix whatever feels awkward.

---

Below the line, only if everything above is done:

- A second district's data, to show it generalises.
- SHAP-style explanation of why a scheme matched.

## Not building

WhatsApp, IVR, mandi prices, document scanning, the daily voice brief.

These are on the roadmap slide. A half-built version is worse for us than an
honest roadmap: it invites exactly the question we cannot answer well, and it
costs hours we need elsewhere.

## Rhythm

- Commit with a real message every time something works.
- Merge to `main` every two or three hours.
- Run `python -m pytest backend/tests/ -q` before every merge.
- One person reviews merges into `main`, so somebody has the whole system in
  their head when something breaks during the demo.

## Before you record

- `git pull`, fresh database, run the demo path start to finish.
- All 21 tests passing.
- Every simulated and synthetic label still visible on screen.
- The README's "what is real and what is not" table matches what the code
  actually does.

## Questions judges will probably ask

Everyone should be able to answer these without looking anything up.

- Why MCP rather than a normal API backend?
- What stops the model inventing an interest rate or a scheme rule?
- What stops the agent approving its own application?
- Why does a multi-signature quorum matter here? Is it overkill?
- What happens on a feature phone, or with no data?
- How is this different from a government portal, or from a general chatbot?
- How do you make money if users pay nothing?
- What is actually built versus planned?

The honest answer to the last one is the "what is real and what is not" table
in the README. Know it.
