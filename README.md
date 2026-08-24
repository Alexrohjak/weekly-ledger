# The Week Ledger

A single-file weekly planner/ledger web app, originally authored and published as a
Claude Artifact. It is one self-contained HTML file — inline CSS and JS, no build step,
no dependencies. The only external request is Google Fonts.

## Files

| File | Source artifact | Published |
|---|---|---|
| `index.html` | https://claude.ai/code/artifact/ed576c5d-9a4e-4cf5-9375-78b1507c54f3 | 2026-08-23 (later) |
| `earlier-publish.html` | https://claude.ai/code/artifact/e4bd535b-e9fc-4901-b90d-0ea81721a0a7 | 2026-08-23 (~53 min earlier) |

These are two **separate** artifacts of the same app, not two versions of one artifact.
`index.html` is the current one; `earlier-publish.html` is kept only as a reference copy
of the earlier publish.

Both files have had the Claude Artifact frame runtime (the injected `<base>` tag and
`<!-- frame-runtime -->` bootstrap script, ~11.5 KB) stripped, so they are plain
standalone HTML. Beyond that, `index.html` carries the boot-order fix described below;
`earlier-publish.html` is untouched.

## The self-bricking save (fixed)

`index.html` as pulled down was inert: dropdowns would not open or close, ticks did not
fill the target rings, and nothing survived a reload. One error caused all three.

`publishNow()` regenerates the page by collecting every `[data-app]` node into `<head>`.
The app's own `<script>` carries `data-app`, so the first time the app saved itself it
hoisted its script above the `#doc` element that the script reads on its third line.
`document.getElementById('doc')` then returned `null` at parse time, the IIFE threw
immediately, and no event listeners were ever attached — checkboxes still ticked
natively, but nothing was listening. The save worked exactly once and broke every load
after it. `earlier-publish.html`, which predates that save, still has the script after
`#doc` and runs fine.

Two changes:

- Boot is deferred to `DOMContentLoaded`, so the script works wherever it sits.
- `publishNow()` now emits `<script data-app>` at the end of `<body>` instead of in
  `<head>`, so a save no longer relocates it.

## Running locally

Open `index.html` in a browser, or serve it:

    python3 -m http.server 8000    # then http://localhost:8000/index.html

## Persistence

The app persists through two paths:

- **Hosted as an Artifact** — uses the `artifact` runtime capability
  (`claude.use('artifact')`) to save new versions of the page itself, so edits survive
  for everyone who opens it.
- **Anywhere else, including locally** — `claude.use` is absent, the app reports
  *"Offline — changes stay on this device"* and falls back to `localStorage`.

So a local copy is fully usable, but edits made locally stay in that browser and do not
flow back to the published artifact.

## Republishing

To push local changes back to the live artifact, publish `index.html` to the existing
URL (`ed576c5d-…`) rather than as a new artifact — publishing without the URL creates a
separate artifact, which is how the duplicate above came about.

## Note on history

Claude Artifacts keep a version history in the web UI, but it is not retrievable through
the API — only the current version of each artifact can be read. The git history in this
repo therefore starts at the state pulled down on 2026-08-24; it is not a reconstruction
of the artifacts' own edit history.


## The live artifact is the data, this repo is the code

The app keeps its state *in its own markup*, so the published artifact is the record of
what is actually ticked — not this repo. Once the page saves itself, the two diverge:
the live version gains real data and a fresh `data-build`, while `index.html` here stays
at whatever was last hand-edited.

**Before republishing from this repo, re-read the live artifact and port code changes
onto it.** Publishing `index.html` as-is reverts every tick made since it was written.

Two other things the self-save does differently from a tool publish: it emits a single
clean document (a tool publish nests it inside the viewer's own skeleton), and it
re-serializes the DOM, so formatting and attribute order churn even where nothing
changed.


## Training data

`tools/extract_sessions.py` turns the ledger's markup into a tidy dataset. The ledger
keeps everything in HTML — the live week under `#days`, filed weeks deep-cloned into
`<details class="wkfile">` under `#archlist` (inputs disabled but their values kept), and
next week staged under `#nextdays`. The extractor reads `live-snapshot.html`, skips the
staged week because it hasn't happened, and writes:

- `data/runs.csv` — one row per run slot: date, week, planned, km, time, pace
- `data/sets.csv` — one row per set: date, session, exercise, prescription, kg, hit
- `data/sessions.json` — everything, nested

    python3 tools/extract_sessions.py                 # from live-snapshot.html
    python3 tools/extract_sessions.py --only-logged   # drop rows with no number

Stdlib only (no bs4/lxml). Pace is computed as time/distance; the clock parser accepts
`mm:ss`, `h:mm:ss` or bare minutes, matching the app.


## Finish times

Every block already carried a `data-end`; it was simply never displayed, so a lecture
read `08:15` with no indication of when it ended. Each block now shows `start – end`.

- The finish time is a `.tend` span after `.t`, editable like the start time. Editing it
  writes back to `data-end`, which is what `blockSpan()` reads for the week diagram.
- The en dash comes from `.tend::before`, so the editable text stays just `HH:MM`.
- `ensureEnds()` runs at the top of `render()` and adds a `.tend` to any block that
  lacks one — blocks arriving from the timetable feed, or added with **+ block**. It
  never rewrites an existing one: `render()` fires on every keystroke and would
  otherwise move the caret mid-edit.
- Archived weeks keep whatever they were filed with; `ensureEnds()` only touches `#days`
  and `#nextdays`.


## Today and now, in the week diagram

The diagram used to box today's whole column in a 1.5px amber ring
(`.col.today .track{box-shadow:inset 0 0 0 1.5px var(--amber)}`), which shouted —
particularly in dark mode, where `--amber` is `#F0A93C`. The now-line was a 2px bar with
an 8px dot.

Today is now marked by a lifted track (`--lift` rather than `--sunk`) with a 2px amber
cap along its top edge, and the amber column header that was always there. The now-line
is a hairline at 85% opacity with a 5px dot, ringed in `--sunk` so it stays legible
where it crosses a coloured bar.
