# Setup

Getting Arithva running on your machine. Takes about five minutes.

## You need

- **Python 3.11 or newer.** Check with `python --version`. If it is missing,
  install from python.org and tick **"Add Python to PATH"** during setup.
- **Git.** Check with `git --version`.
- **Chrome or Edge** for the voice features. Typing works in any browser.
- **VS Code**, with the Microsoft **Python** extension.

## First time

Open a terminal somewhere sensible — `C:\dev` rather than Desktop or OneDrive,
because OneDrive syncs files while you work and that causes odd problems.

```powershell
git clone https://github.com/jordanv25/arithva.git
cd arithva
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell refuses to run the activate script, run this once, then retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

On macOS or Linux the activate line is `source .venv/bin/activate` instead.

**Check it worked.** Your prompt should show `(.venv)`, and:

```powershell
python -c "import sys; print(sys.prefix)"
```

should print a path ending in `.venv`. If it prints something under
`AppData\Local\Programs\Python`, the virtual environment is not active and
nothing below will work properly.

## Running it

```powershell
python -m uvicorn backend.main:app --reload --port 8001
```

Open **http://localhost:8001**.

`--reload` restarts the server whenever you save a file, so the loop is: edit,
save, refresh the browser.

Use `python -m uvicorn`, not bare `uvicorn`. The `python -m` form always uses
the virtual environment's Python; bare `uvicorn` can silently pick up a
different installation and give you confusing import errors.

## Every time after that

```powershell
cd C:\dev\arithva
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8001
```

## Tests

```powershell
python -m pytest backend/tests/ -q
```

21 tests. Run them before every commit. If they pass, the demo path works.

## Try the demo path

1. **Citizen** tab. Click a sample question, or hold the mic button and speak.
2. Ask the weather, then a scheme, then an EMI. Look at the source line under
   each answer.
3. Say *"I need 2 painters for 3 days at 800 rupees"*. It reads the action back
   and waits. Nothing happens until you confirm.
4. Say *"apply for 1.5 lakh"*. An application goes to the officer queue.
5. **Officer** tab. Press **"Let the agent approve"** and watch it refuse.
6. Sign as Officer A, switch to Officer B in the dropdown, sign again, and
   again, until quorum is met. Those are real ECDSA signatures made in your
   browser.
7. **Dashboard** tab. The sanctioned amount appears, labelled simulated.
8. **Audit log** tab. *Verify chain*, then *Tamper with a row*, then verify
   again.

## Working on it

Read `CLAUDE.md` first. It has the architecture, the three invariants that must
not break, and who owns which files.

```powershell
git checkout main
git pull
git checkout -b yourname/what-youre-doing
# work, run the tests, read your diff
git add .
git commit -m "what changed and why"
git push -u origin yourname/what-youre-doing
```

Merge into `main` every two or three hours. Leaving it until the end is how
four days of work turns into four hours of merge conflicts.

## When something goes wrong

**`No module named 'backend'`** — you are in the wrong folder. Run `dir`. You
should see `backend`, `frontend`, `data`. If not, `cd` to where you do.

**`WinError 10013` on startup** — that port is blocked or reserved on your
machine. Use a different one: `--port 8002`, `--port 9000`. To see what Windows
has reserved: `netsh interface ipv4 show excludedportrange protocol=tcp`.

**Voice button does nothing** — speech recognition needs Chrome or Edge, and a
secure context. `localhost` counts as secure; an IP address like
`192.168.1.5:8001` does not. Typing works regardless.

**Weather says unavailable** — the forecast service did not answer. That is the
honest failure path working as designed, not a bug. Everything else still runs.

**Imports resolve oddly, or packages seem missing** — the virtual environment
is probably not active. Check for `(.venv)` in your prompt.
