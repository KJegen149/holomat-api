# Phase 11 — Model Sourcing

**Status:** Shipped (PR #36, #37, plus the post-merge MakerWorld revert).
**Goal:** pull printable models into Holomat from many sources, all funnelling
into the shared STL pool (`scan_data/stls/`), so the existing slice → print
pipeline can take any of them to the Bambu P1S.

---

## Concept

Before Phase 11, `scan_data/stls/` was fed by exactly one source — OpenSCAD
case generation — and the Print tab listed/queued whatever was in that folder.
Phase 11 turned "model sourcing" into a first-class capability with several
inlets, presented as its own area in the UI (the Model Sources tab).

```
  OpenSCAD case-gen     ─┐
  STL Samba share       ─┤
  Meshy retrieval       ─┼──►  scan_data/stls/  ──►  OrcaSlicer  ──►  Bambu P1S
  Meshy library browse  ─┤
  Thingiverse           ─┤
  TinkerCad (external)  ─┘
```

---

## Outcomes

### 1. STL Samba share — ✅ shipped
`\\<host>\HolomatSTL` guest-writable share mapped to `scan_data/stls/`.
Shipped ahead of Phase 11 so print testing could proceed.

### 2. Model Sources tab — ✅ shipped (PR #36)
Dedicated grid-style tab over `scan_data/stls/`: thumbnail, source badge,
size, date, queue-to-print, delete, sidebar with the inlet buttons.

### 3. Meshy retrieval — ✅ shipped (PR #37)
On Meshy task success, `core/meshy_jobs.py` downloads `model_urls.stl` into
the pool with a sidecar that carries the thumbnail and task id. Wired into
the Gallery "make 3D" button and surfaced in the Model Sources sidebar's
"Meshy Retrievals" panel.

### 4. Thingiverse — ✅ shipped (PR #37)
`THINGIVERSE_TOKEN` (app token, sensitive, set via Settings). New search
modal: query → grid → file picker per Thing → import. Live-tested.

### 5. MakerWorld — ❌ removed (post-merge revert)
Initial implementation paste-URL → reverse-engineered Bambu Cloud download
worked on paper but errored immediately on a live test. Reverted because
Bambu Handy / Studio already cover the same round-trip natively. Anyone
wanting MakerWorld models exports the STL from Bambu Studio and drops it
into HolomatSTL.

### 6. TinkerCad — ✅ shipped as pop-out (PR #37)
Autodesk serves with `X-Frame-Options: SAMEORIGIN`, so the iframe path was
not viable. Fallback: a sidebar link opens TinkerCad in a new tab; exported
STLs land in HolomatSTL automatically.

### 7. Meshy library browse — ✅ shipped (PR #37)
Beyond Gallery-originated jobs, the Meshy Library modal lists every
image-to-3D task on the connected Meshy account (status chips for
Completed / In Progress / Failed), with one-click import on SUCCEEDED
tasks. Requires `MESHY_API_KEY` (direct Meshy API key, separate from
the Cloudflare worker's `CF_API_KEY`).

---

## Defaults that changed

- **Standard built-in print profile** now defaults to `supports: "tree"`.
  The Model Sources tab's Queue button uses this profile, so foreign-source
  STLs get auto-tree supports without the user needing a custom profile.
  Draft and Fine kept `supports: "none"` since those are explicit
  speed/precision choices.

## Known oddities to revisit

- **First-print-after-import sometimes stalls past the 5-min RUNNING
  window**, surfacing as "Printer never entered RUNNING state — most
  likely silently aborted." Retrying the same file (either from Model
  Sources Queue or the Print tab) printed fine. Not reproduced
  deterministically; not believed to be a code-level divergence between
  the two queue entry points. Worth investigating if it becomes a pattern.

## Operator setup added in Phase 11

- New env vars (both sensitive, set via Settings → External APIs):
  - `THINGIVERSE_TOKEN` — app token from thingiverse.com/developers/my-apps
  - `MESHY_API_KEY` — direct Meshy API key (gets the library browse working;
    the existing Cloudflare worker path still handles generate/upload)

---

*Phase 11 shipped 2026-05-24.*
