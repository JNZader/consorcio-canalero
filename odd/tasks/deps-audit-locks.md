# Close the audit gate and the two incomplete Dependabot bumps

Branch: `feat/deps-audit-locks` (backend) and PR 578's Dependabot branch (Mantine patch). Delivery: `single-pr` for the backend closure, because the hashed locks are one generated artifact and cannot be sliced under 400 lines. Test runner: `./gee-backend/venv/bin/python -m pytest` for the lock contracts; `npm test` is CI for the Mantine filename. Do not merge. Do not edit PR 577, 579, or 580.

## Specs

S1. The hashed runtime and dev locks must satisfy `certifi>=2026.10.19` and `Pillow>=13.0.0`. The 2026-10-21 lint job failed pip-audit on certifi 2026.7.22 (PYSEC-2026-4320, fix 2026.10.19) and pillow 12.3.0 (fix 13.0.0) while ruff itself passed. Regenerate with the `uv pip compile` commands in the `requirements.txt` header.

S2. The supported SQLAlchemy combination moves to 2.1.5 together: `requirements.txt` (`sqlalchemy[asyncio]>=2.1.5,<2.2.0`), `requirements-geo.txt` (`sqlalchemy>=2.1.5,<2.2.0`), `overrides.txt` (`sqlalchemy[asyncio]==2.1.5` and the BE-12 comment), and `tests/new/test_sqlalchemy_supported_combination.py`. `fastapi-users` stays 15.0.5 and `fastapi-users-db-sqlalchemy` stays 7.0.0. Both locks pin `sqlalchemy==2.1.5`.

S3. `gee-backend/requirements-rag.txt` stays on `transformers>=4.40.0`. PR 577 is not updated.

S4. PR 578: the vendored Mantine patch file is named `@mantine+core+9.7.3.patch`, the hunks still apply to `@mantine/core` 9.7.3, and `tests/unit/patchesApplied.test.ts` CI-03 can match that name to the installed version. The other 18 bumps in that PR stay as Dependabot wrote them.

S5. Do not merge any PR. Push the branches and watch CI. Do not put the lock bump inside PR 579 or PR 580.

## Tasks

- T1. S1, S2. inline. Backend manifests, override, test, and both locks. Commit `ce6fc0e2` on `feat/deps-audit-locks`. Pre-commit `javi-forge ci --quick` passed. The installed-version SQLAlchemy assertion is still CI-only.
- T2. S4. inline. Rename and re-check the Mantine patch on the PR 578 branch. Commit `eeb44ad7`, pushed onto `dependabot/npm_and_yarn/consorcio-web/npm-minor-patch-8a88e95c72`.
- T3. S3, S5. inline. Open or update the PRs, watch CI, leave 577, 579, and 580's diffs alone.

## Log

L1. 2026-10-21. User: "has los cambios necesarios y ve monitoreando que quede todo bien"

L2. The necessary changes are the ones named in the review of PRs 576-580: an own backend closure for certifi and pillow, a finished SQLAlchemy 2.1.5 bump (locks plus the pin test), and a Mantine 9.7.3 patch filename. PR 577 stays held because the transformers floor was not remeasured against the cross-encoder. Pillow 13.0.0 drops Python 3.10 and refuses to save mode `I` as PNG. This app's `fromarray` calls pass uint8 RGB/RGBA, which is not the removed dtype-changing mode. One backend PR holds S1 and S2 because a second lock regeneration would conflict with the first. That diff exceeds the 400-line planning heuristic; the excess is the generated hash set.

L3. 2026-10-21. Both locks were regenerated with the documented `uv pip compile` commands (`--python-version 3.14 --universal --generate-hashes --overrides overrides.txt`). The only version changes versus `3dd9297c` are `certifi` 2026.7.22 to 2026.10.19, `pillow` 12.3.0 to 13.0.0, and `sqlalchemy` 2.1.4 to 2.1.5, in both locks. `./gee-backend/venv/bin/pytest tests/new/test_sqlalchemy_supported_combination.py tests/test_requirements_lock_sync.py -k 'not test_installed_versions_match_the_supported_combination'` reported 7 passed and 1 deselected in 0.81s. The deselected test reads the installed distribution; the active venv is still SQLAlchemy 2.1.4, so that assertion is left to CI, which installs from the lock. Work-unit commit: `ce6fc0e2`. Pre-commit quick CI passed, including backend ruff and frontend typecheck. Frontend biome warnings in that run are pre-existing and were not introduced by this commit.

L4. 2026-10-21. PR 578 patch rename. `git mv` of `@mantine+core+9.7.2.patch` to `@mantine+core+9.7.3.patch` (0 line changes). `node scripts/apply-patches.mjs` on a fresh `npm ci` of that branch printed `aplicado` for get-env, both Transition builds, and the two Stryker patches. `npx vitest run tests/unit/patchesApplied.test.ts` then passed 3/3, including CI-03 against installed `@mantine/core` 9.7.3. The first vitest failed the "are applied" case because this machine has `npm config ignore-scripts=true`, so `npm ci` did not run postinstall. CI does run it. Commit `eeb44ad7` pushed. The other 18 Dependabot bumps were not edited.
