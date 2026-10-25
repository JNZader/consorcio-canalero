# Work Unit: audit-2026-10-seg1-photo-decode-cap

Fixes audit finding SEG-1 (WARNING) from the 2026-10-23 exhaustive audit
(`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`): the denuncia
photo upload bounded only COMPRESSED bytes (`MAX_PHOTO_BYTES` = 10 MB) while
Pillow decoded the image twice (verify + re-encode) synchronously inside
`async def save` — a 10 MB JPEG can declare ~100-150 Mpx → 300-450 MB of RGB
per request, on the event loop, repeatable at 100 req/min by any authenticated
ciudadano. The repo had already fixed this exact class on the map-PDF surface
(`geo_map_pdf_max_image_px`, 40 Mpx).

## In

- app/config.py: new `denuncia_photo_max_image_px: int = 40_000_000`,
  mirroring `geo_map_pdf_max_image_px`. 40 Mpx ≈ 120 MB of RGB per decode —
  the same bound the map-PDF surface already accepted — and sits above every
  mainstream phone camera output (12-24 Mpx by default; high-res sensor modes
  top out around 50 Mpx and those JPEGs rarely fit the 10 MB byte cap anyway).
- app/shared/storage.py `_validate_and_strip_exif`: explicit decoded-pixel cap
  answered from the HEADER — checked right after the lazy `Image.open`, BEFORE
  `verify()` and the re-open/re-encode walk the raster. Rejects with the
  endpoint's existing error style (HTTPException 400, Spanish detail naming
  the limit and the offending dimensions).
- app/shared/storage.py `_validate_and_strip_exif`: `PIL.Image.DecompressionBombError`
  (raised by `Image.open` for headers declaring > Pillow's own ~179 Mpx
  default; an Exception, NOT an OSError) is now mapped to the same pixel-cap
  400 instead of escaping storage as a 500.
- app/shared/storage.py `LocalPhotoStorage.save`: the Pillow
  validate+strip+re-encode now runs via `starlette.concurrency.run_in_threadpool`
  — the same offload idiom the rest of the app uses — so concurrent uploads
  can't stall the event loop. Per-image decode memory stays bounded by the
  pixel cap (~120 MB RGB worst case).
- tests/new/test_photo_storage_decode_cap.py: red-checked regression suite —
  over-cap image rejected (cap monkeypatched low, image inside the byte cap),
  a 75-byte IHDR-declared bomb capped from the header under the REAL 40 Mpx
  default, Pillow's own bomb error mapped to 400, an under-cap JPEG saved with
  EXIF GPS values stripped (behavior pin), and the Pillow work proven to run
  off the event-loop thread (thread-ident spy). On unfixed code 4 of 5 fail:
  missing setting / OSError truncated raster / DecompressionBombError
  escaping / same-thread execution; the EXIF pin passes before and after by
  design.

## Out

- ~~No concurrency semaphore for in-flight Pillow decodes~~ — ADDED in the
  review fix round (RSK1-001): `denuncia_photo_max_concurrency` (default 2,
  mirroring `geo_map_pdf_max_concurrency`), non-blocking acquire + immediate
  503 `Retry-After: 2` (the caller is async; a blocking acquire would stall
  the loop — deviation from the PDF's timeout pattern documented in-code).
  Saturation test pins second-in-flight → 503, recovery after release.
- Residual status-code escapes for corrupt payloads that pass open+format+cap
  (review RSK1-002, PRE-EXISTING): broken-PNG `verify()` raises `SyntaxError`
  → generic 500; truncated-JPEG scan passes verify and fails at save with a
  503 "No se pudo guardar". Reported for a separate small unit.
- Pillow 12 quirk observed while writing the fixture (pre-existing, not
  touched): after the strip, the re-encoded JPEG can still carry a dangling
  EMPTY GPSInfo IFD pointer (`Exif.tobytes()` re-adds cached empty sub-IFDs).
  The GPS VALUES are gone — no PII leaks — so this is cosmetic.
- Resizing/downscaling oversized-but-legitimate photos instead of rejecting
  them (friendlier UX) — separate product decision; today the citizen gets a
  clear 400 naming the pixel limit.
