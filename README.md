# The Week Ledger

A single-file weekly planner/ledger web app, originally authored and published as a
Claude Artifact. It is one self-contained HTML file — inline CSS and JS, no build step,
no dependencies. The only external request is Google Fonts.

## The one artifact

There is exactly **one** live artifact — rebuilt clean on 2026-08-25 and starting from an
empty week:

    https://claude.ai/code/artifact/0fe32cdb-1b1d-4be4-bd3a-fba8afae8316

**Never publish this app without that URL.** A publish with no `url` creates a *new*
artifact rather than a new version of this one. That is how every duplicate here appeared
— and, once, how a rebuild got unblocked on purpose:

| Artifact | Fate |
|---|---|
| `0fe32cdb-…` | **canonical.** The empty rebuild. Keep. |
| `ed576c5d-…` | the old full week. Superseded — its data is in `live-snapshot.html`. Delete. |
| `ba80fea8-…` | an earlier clean-slate restart that never got past the lectures. Delete. |
| `e4bd535b-…` | earliest duplicate, already deleted from the gallery. |

### Why the rebuild, and not a strip in place

The plan was to strip `ed576c5d` back to empty days and keep the URL. The publish path
would not allow it: overwriting a live artifact requires having read its current version
in full, and every refused attempt cleared that state, so re-reading and re-publishing
just alternated between *"you hadn't viewed the live version"* and *"identical content,
already refused"*. Publishing the same stripped document as a **new** artifact has no
prior version to reconcile against, so it goes straight through.

The cost is a new URL and the loss of the five ticks from 24–30 August, which survive in
`live-snapshot.html` and `data/*.csv`. Nothing else changed: the app code in the rebuild
is byte-identical to what was live.

## Files

| File | What it is |
|---|---|
| `index.html` | the code, and the empty week as published. |
| `templates/blocks.html` | one of each block type, logs and prescriptions intact, ticks cleared. Paste into a day's `<ul class="blks">` and set the times. |
| `live-snapshot.html` | the last capture of the old artifact — 26 blocks, 5 ticked, week of 24–30 August. |
| `earlier-publish.html` | reference copy of the deleted `e4bd535b` publish. |

All have had the Claude Artifact frame runtime (the injected `<base>` tag and
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

Three rules, in order:

1. **Always pass the canonical URL** (`0fe32cdb-…`). A bare publish forks a new artifact.
2. **Re-read the live artifact first and port code changes onto it.** The live page is
   the record of what is ticked; publishing `index.html` as-is reverts every tick made
   since it was last hand-edited.
3. **Expect the page to have moved.** It saves itself as you use it, so the version you
   read can be stale by the time you publish. If a publish is rejected as a conflict,
   merge onto the newer content and publish again — never force.

A cloud routine snapshots the live artifact into `live-snapshot.html` roughly twice a
day, which is why commits authored by Claude appear in this history.

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


## Moving blocks

Each block has a ⠿ handle on the left. Drag it to move the block within a day or to
another day; the week diagram follows immediately, because `drawShape()` reads `.t` and
`data-end` and that is exactly what a drop rewrites.

**The drop position sets the time.** A block keeps its duration and starts when the
block now above it ends. Dropped at the top of a day it ends where the next block
begins; dropped into an empty day it keeps its own clock time. The day is then re-sorted
by start time, so the list never falls out of chronological order.

Pointer events, not HTML5 drag-and-drop — `dragstart` never fires from touch, and this
has to work on a phone. `touch-action:none` on the handle stops a drag scrolling the
page.

Keyboard equivalent, so the handle is not mouse-only: focus it and use **Alt+↑/↓** to
nudge the start by 15 minutes, **Alt+←/→** to move the block a day.

Only `#days` and `#nextdays` accept drops. Filed weeks are frozen: `rollWeek()` strips
their handles along with the log toggles.

**+ block** now starts where the day currently ends rather than always at 12:00. The ×
on each row still deletes.
