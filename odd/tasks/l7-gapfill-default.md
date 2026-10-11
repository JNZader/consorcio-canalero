# l7-gapfill-default

Landsat 7 explorer uses SLC-off gap fill by default. Fill uses 3 neighbor dates and no focal blur.

## Tasks

- [x] Drop residual focal_mean; allow 3 fill dates
- [x] L7 calendar / Probar este default to composite (buffer 20)
- [x] Tests + work-unit commit

## Out of scope

20px kernel, filling unused bands, false color (#446).
