# Phase 11 — Model Sourcing

**Status:** Planned — not started.
**Target:** the v1.0.1 → v1.1.0 development cycle (Phase 10 ships v1.0.0).
**Goal:** pull printable models into Holomat from many sources, all funnelling
into the shared STL pool (`scan_data/stls/`), so the existing slice → print
pipeline can take any of them to the Bambu P1S.

---

## Concept

Today `scan_data/stls/` is fed by exactly one source — OpenSCAD case
generation — and the Print tab lists/queues whatever is in that folder.
Phase 11 turns "model sourcing" into a first-class capability with several
inlets, presented as its own area in the UI (separate from the Print tab).

```
  OpenSCAD case-gen  ─┐
  STL Samba share    ─┤
  Meshy retrieval    ─┼──►  scan_data/stls/  ──►  OrcaSlicer  ──►  Bambu P1S
  Thingiverse        ─┤
  MakerWorld         ─┤
  TinkerCad embed    ─┘
```

---

## Work items

### 1. STL Samba share — ✅ DONE (shipped early in the v1.0.x line)
A second guest-writable Samba share, `\\<host>\HolomatSTL`, mapped to
`scan_data/stls/`. Drop a Fusion / Tinkercad / downloaded `.stl` into it and it
appears in the Print tab immediately (`/api/print/stls` already globs that
folder). Shipped ahead of Phase 11 so print testing could proceed.

### 2. Meshy retrieval
Finish the Meshy loop. Today Holomat submits an image-to-3D job and polls
status but never retrieves the result. Add: on task success, read `model_urls`
from the Meshy response, download the model, and save it into `scan_data/stls/`.
- Verify which formats Meshy returns (glb / obj / fbx / usdz — and whether STL
  is directly available) against the Cloudflare worker's Meshy integration.
- Meshy meshes are organic and often not watertight — a manifold-repair /
  printability pass is likely needed before slicing.

### 3. Thingiverse integration
Browse / search Thingiverse and pull STLs into the pool.
- Needs a Thingiverse API key; review their API terms of use.

### 4. MakerWorld integration
The same idea for Bambu's MakerWorld library.
- Confirm whether MakerWorld exposes a usable public API; if not, this may be
  limited in scope or need a different approach.

### 5. TinkerCad embed
An in-Holomat iframe / web view of TinkerCad for creating and editing models,
exporting straight into the STL pool.
- Risk: TinkerCad (Autodesk) may block iframe embedding via `X-Frame-Options`
  / CSP `frame-ancestors`. Verify before committing to the iframe approach — a
  pop-out browser view may be the fallback.

### 6. Meshy embed (stretch)
A similar embedded web view for Meshy, if its app permits embedding.

---

## Pipeline note

Every source lands in `scan_data/stls/`. From there the path is unchanged: the
Print tab lists the files, OrcaSlicer slices to 3MF, and the LAN print path
dispatches to the Bambu P1S. OpenSCAD remains the route for parametric / case
work.

## Open questions

- Embeddability of TinkerCad and Meshy (`X-Frame-Options` / CSP).
- Thingiverse & MakerWorld API access, keys, and terms.
- Mesh repair — which tool/library makes downloaded meshes printable.
- Where the "Model Sources" UI lives (new tab) and how it relates to Gallery.

---

*Captured during Phase 10. Flesh this out when Phase 11 begins.*
