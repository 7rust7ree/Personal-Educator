# Personal Educator

An AI teacher modeled on [LearnHarness](https://github.com/amosblomqvist/learnharness):
**probe** what you know → **plan** the shortest path to your goal → **teach** one step at a time
(predict → explain → check), with confidence sliders and think-out-loud boxes on every question.

## Run

**As a desktop app (recommended):** open **Personal Educator** from `~/Applications`, Spotlight or Launchpad.
Build/rebuild that app with `./scripts/make_mac_app.sh`.

**From the terminal:**
```sh
cd ~/PesonalEducator
source .venv/bin/activate
python -m backend.desktop                 # native window
# or: uvicorn backend.app:app --reload    # then open http://localhost:8000 in a browser
```
Needs `ANTHROPIC_API_KEY` in your environment (`~/.zshrc`). App logs go to `data/app.log`.

**Voice input:** click the mic on any text box (or press Ctrl+M) and talk. Your words type into the box live
(Vosk, a fast streaming recognizer). Click again, or press Enter, to stop; a few seconds later the text is swapped for
a cleaner, punctuated version (Whisper), unless you've edited it. Esc cancels. Everything runs on this computer:
free and offline after one-time model downloads (~70 MB + ~140 MB). macOS asks for microphone access once.

**Motion** (sidebar, bottom): Full / Lite / Off background animation. Lite is the default on laptops with 4 or
fewer CPU threads. Animation pauses while you dictate and when the window isn't focused.

**Keyboard:** `1`–`5` pick an option, `0` = I don't know, `Enter` submits, `Shift+Enter` new line.

First-time setup (only if `.venv` is missing):
```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
```

## Tests
```sh
.venv/bin/python -m pytest -q     # fake Claude: free, no network
```

## Layout
- `backend/app.py` web API + streaming · `backend/agent.py` the teaching loop
- `backend/prompts/teacher.md` the teacher's instructions (edit freely)
- `backend/tools.py` quiz / ask_question / probe_done / plan_init / plan_progress
- `backend/core/` pure logic (plan, grading, view) · `backend/store.py` the only code touching `data/`
- `backend/dictation.py` mic + local Whisper · `backend/desktop.py` native window launcher
- `frontend/` plain HTML/JS/CSS (Markdown, KaTeX math, Mermaid diagrams, animated background in `bg.js`)
- `data/` your sessions, profile, settings, usage log (git-ignored)

Costs: default teacher is Claude Opus 5.5 at medium effort; a turn is roughly 1–3¢ with caching.
Monthly cap defaults to $10 (`data/settings.json` → `monthly_budget_usd`).
