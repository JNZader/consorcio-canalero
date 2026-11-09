# visual-polish-audit

Objective: Apply the remaining visual-audit polish backlog (Theme Lab already shipped in #685).
Branch: `feat/visual-polish-audit`
Delivery: single-pr
Test runner: `pnpm --filter consorcio-web test` (focused) + typecheck

## Specs

- S1: Dedupe `mapColorTokens` case twins (9 pairs) to one casing; update call sites; keep `mapCssVariable` guard.
- S2: Remap residual Mantine stock `color=` / `c=` in non-map UI to semantic palettes (`exito`/`alerta`/`institucional`/`agua`/`orange`). Exclude map2d/map/terrain scientific/data chrome. Destructive Menu.Item/Button may use `alerta`. Keep gray for muted/empty where appropriate.
- S3: Adopt `--cc-color-*` in header/home/footer (and global focus/required where brand maps cleanly).
- S4: Fix button hierarchy in AdminDashboard + TramitesPanel (one filled primary CTA; secondary outline/light).
- S5: Add `PageHeader` on ProfilePanel, ParticipacionPage, PrivacyPolicyPage, LoginForm, ForgotPasswordForm, ResetPasswordForm, VerifyEmailPage, FormularioReporte, FormularioSugerencia. HomePage/MapaPage stay custom. Reports/Sugerencias keep ParticipacionPanel ownership.
- S6: Leave StatusBadge AA contrast as-is (already verified).

## Tasks

- T1 S1 — tokens dedupe — inline — done
- T2 S2 — stock→semantic remaps — inline — done
- T3 S3 — CSS `--cc-*` aliases — inline — done
- T4 S4 — AdminDashboard/Tramites CTA hierarchy — inline — done
- T5 S5 — PageHeader on missing screens — inline — done
- T6 S1-S5 — verify typecheck/tests/browser smoke — inline — done (typecheck + designTokens; no browser smoke)

## Log

- L1: User asked if the rest of the visual-audit corrections were done; answered no (only Theme Lab #685). User chose full backlog: "Todo el backlog visual del audit" then confirmed "Sí, implementá todo el backlog ahora".
- L2 (2026-11-08): Implemented T1–T5 on `feat/visual-polish-audit`. Evidence:
  - **T1/S1**: Removed 9 uppercase twins from `mapColorTokens` in `consorcio-web/src/lib/theme.ts`; kept lowercase keys + `seenMapVars`/`mapCssVariable`. Call sites updated in mapStyles, kmzLayerRegistry, canalesLayers, pilarVerdeLayers, mapLayerEffectHelpers, terrainVectorLayerEffects, SugerenciasPanel, designTokens.test.
  - **T2/S2**: Non-map stock `color=`/`c=` (green|blue|red|teal|yellow|cyan|violet[+shade]) **49 → 0** (excluding `routeTree.gen.tsx` + map2d/map/terrain). 60 substitutions across 30 component files → exito/alerta/institucional/agua/orange. Map chrome intentionally untouched.
  - **T3/S3**: Added `--cc-color-brand-deep` / `--cc-color-brand-edge` in `cssVariablesResolver`. header → surface/border; footer → brand-deep/edge; home focus → `--cc-color-primary`; global focus blue→institucional, required → `--cc-color-danger`, attrib links → institucional.
  - **T4/S4**: AdminDashboard: single `variant="filled"` CTA (Descargar datos JSON); import/export demoted to outline/light. TramitesPanel: Nuevo/Crear `filled`+institucional; PDF outline; seguimiento light.
  - **T5/S5**: PageHeader on ProfilePanel, ParticipacionPage (center), PrivacyPolicyPage, LoginForm (center), Forgot/Reset/VerifyEmail, FormularioReporte, FormularioSugerencia. HomePage/MapaPage untouched; Reports/Sugerencias still under ParticipacionPanel.
  - **Verify**: `pnpm exec tsc --noEmit` clean; `pnpm exec vitest run tests/unit/designTokens.test.ts` 9/9 pass. No commit/push/build.
  - **Files**: 52 modified under consorcio-web + odd task file (160+/147-).
- L3 (2026-11-08): R2 readability review → 2 WARNING fixed before commit: FormularioReporte/Sugerencia `order={2}` (avoid nested h1 under Participación); ImageExplorer/ReportDetail/ProximaReunion stock green/blue CSS vars aligned to exito/institucional. designTokens 9/9 still green.
