# Hackathon build plan

What exists now, what each person owns on the day, and what we deliberately
leave unbuilt.

## Where the prototype already stands

Working end to end: the voice loop with its ElevenLabs → Polly → browser
provider chain, five MCP servers, scheme matching, EMI in integer paise, live
weather with deterministic advice, job posting with the wage flag, adaptive
quorum with real ECDSA signatures, the hash-chained audit log, and three
screens. 34 tests pass.

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

## Sponsor integrations

### Voice: done, needs keys

The chain is **ElevenLabs → Amazon Polly → browser**, already built and
tested. Both are real integrations; neither is on the critical path. To turn
them on, copy `.env.example` to `.env` and fill in the keys. Nothing else
changes.

Worth doing in the demo: remove the key, reload, and show it degrading to the
browser voice. Showing the fallback is a better argument than showing the
integration, because it proves the product does not depend on a vendor.

**Verify before claiming anything about Kannada.** Listen to a real sample from
each provider. If neither handles Kannada well, say so and demo in Hindi and
English — far better than a judge hearing mangled Kannada after we claimed it
works.

### AWS: what is worth adding, in order

1. **Amazon Polly** — done. A real AWS service doing real work in the product.
   Needs `pip install boto3` and an IAM user limited to
   `polly:SynthesizeSpeech`. Never use root keys.
2. **Host the backend on AWS** — App Runner, Elastic Beanstalk or Lightsail.
   This is deployment, not code: it gives a public URL for the last slide and
   lets judges try it themselves. The highest-value AWS addition after Polly,
   and it costs no build time from the people writing features.
3. **S3 + CloudFront for the frontend** — only if the backend is already
   hosted. The frontend is static files, so this is straightforward.
4. **Amazon Transcribe for Kannada speech input** — the most interesting
   option technically, since browser recognition is our weakest link. Also the
   biggest change. Do not start this on the day unless everything else is done.

**Do not add an AWS service that does nothing.** An empty S3 bucket added to
qualify for a prize is the kind of thing a judge asks about and nobody can
answer well. Polly plus hosting is honest and sufficient.

## Using AI tools on this project

Use whatever you are fastest in — Claude Code, Cursor, Copilot, ChatGPT,
Gemini. No one has to use the same tool. Four rules, whichever you pick:

1. **Point it at `CLAUDE.md` first.** Claude Code reads it automatically.
   For other tools, open it or paste it in at the start of a session. It
   contains the three invariants, and an agent that has not read them will
   cheerfully break one.
2. **Read the diff before you accept it.** Not optional. This is the difference
   between understanding your own system at hour 20 and not. Judges will ask
   you to explain how something works.
3. **Run `python -m pytest backend/tests/ -q` after every change.** 34 tests.
   If they pass, the demo path still works.
4. **Stay in your own files.** Agents touch more lines than humans do. Two
   people pointing agents at the same file is the main cause of merge pain.

If an agent proposes something that breaks an invariant — letting the model
compute a number, adding an approve tool, removing a SIMULATED label — say no.
Those are the pitch, not implementation details.

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
