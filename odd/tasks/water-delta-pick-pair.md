# water-delta-pick-pair

Operator picks two optical ranked scenes for Δ agua. Do not use stored pre/post slots (those are often S1).

## Tasks

- [x] Backend resolves `pre_scene_id` / `post_scene_id` against that event's imagery rows
- [x] Explorer: two optical selects + Medir; hide Medir unless ≥2 optical ranked scenes
- [x] Tests + work-unit commit

## Out of scope

- Map column height
- MNDWI mask overlay
- S1 VV Δ
- Alembic / persist hectares
