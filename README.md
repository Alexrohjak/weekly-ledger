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
standalone HTML. Nothing else was modified.

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
