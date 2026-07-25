# Tasks: Frontend Mutation Testing Expansion

## Overview

**Total Tasks**: 34  
**Phases**: 4 (Utilities → Hooks → Store/Components → CI/CD)  
**Estimated Duration**: 25-30 hours total  
**Success Criteria**: ≥80% mutation score per file, all batches complete with CI/CD integration  

---

## Phase 1: Utilities Batch (Batch 1) — 8 Tasks

Low-complexity utility functions with straightforward escape scenarios. Foundation for test patterns used in later batches.

- [ ] **1.1 Create src/lib/utils/__tests__/setup.ts with parametrization fixtures**
  - **AC**: 
    - File created at `src/lib/utils/__tests__/setup.ts`
    - Exports `boundaryValues` (zero, one, negative, max/min safe int)
    - Exports `commonStrings` (empty, whitespace, normal, uppercase, padded)
    - Exports at least 5 additional test data sets for utilities testing
    - No test execution, setup only
  - **Dependencies**: None (foundation task)
  - **Estimated Effort**: 1 hour
  - **Files Modified**: `src/lib/utils/__tests__/setup.ts` (new)
  - **Rollback**: Remove file

- [ ] **1.2 Write src/lib/utils/__tests__/formatters.test.ts (8-12 test cases, parametrized)**
  - **AC**:
    - Tests cover `toUpperCase`, `toLowerCase`, date formatting functions
    - Uses `describe.each()` for boundary value parametrization
    - Tests trim vs. no-trim behavior
    - Tests case handling (mixed case, special chars)
    - At least 10 test cases total
    - Mutation score ≥75% (measured locally)
  - **Dependencies**: 1.1 (setup fixtures)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `src/lib/utils/__tests__/formatters.test.ts` (new)
  - **Rollback**: Remove file; revert to baseline test coverage if exists

- [ ] **1.3 Write src/lib/utils/__tests__/validators.test.ts (10+ test cases, regex boundaries)**
  - **AC**:
    - Tests email validation (valid, invalid, edge cases)
    - Tests phone validation (different formats, lengths)
    - Tests URL validation (protocol variations)
    - Tests regex boundary conditions (include/exclude edge cases)
    - Tests conditional negation (if pattern.test() vs if !pattern.test())
    - At least 12 test cases total
    - Catches conditional negation mutations
    - Mutation score ≥75%
  - **Dependencies**: 1.1 (setup fixtures)
  - **Estimated Effort**: 2.5 hours
  - **Files Modified**: `src/lib/utils/__tests__/validators.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **1.4 Write src/lib/utils/__tests__/calculations.test.ts (arithmetic operator mutations)**
  - **AC**:
    - Tests addition, subtraction, multiplication, division
    - Tests rounding direction (Math.floor, Math.ceil, Math.round)
    - Tests zero handling and division by zero behavior
    - Tests initialization values and increment/decrement (+1 vs -1)
    - Tests boundary conditions (min/max, overflow)
    - At least 10 test cases total
    - Catches arithmetic operator mutations (+ to -, * to /)
    - Mutation score ≥75%
  - **Dependencies**: 1.1 (setup fixtures)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `src/lib/utils/__tests__/calculations.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **1.5 Write src/lib/utils/__tests__/constants.test.ts (enum/constant validation)**
  - **AC**:
    - Tests enum values (correct keys/values)
    - Tests constant definitions (no mutations to values)
    - Tests constant types (string, number, boolean, object)
    - Tests constant object shapes (keys match expected)
    - At least 8 test cases total
    - Mutation score ≥75%
  - **Dependencies**: 1.1 (setup fixtures)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: `src/lib/utils/__tests__/constants.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **1.6 Write src/lib/utils/__tests__/object-helpers.test.ts (10+ parametrized cases)**
  - **AC**:
    - Tests object merge (shallow, deep, overwrites)
    - Tests object clone (shallow, deep copies)
    - Tests pick/omit operations
    - Tests object mutation safety (immutability)
    - Tests edge cases (null, undefined, circular refs)
    - At least 12 test cases total
    - Parametrized for merge/clone variations
    - Mutation score ≥75%
  - **Dependencies**: 1.1 (setup fixtures)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `src/lib/utils/__tests__/object-helpers.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **1.7 Run Stryker on Batch 1 (stryker run stryker-batch-1.config.json)**
  - **AC**:
    - `stryker-batch-1.config.json` exists at project root
    - `stryker run stryker-batch-1.config.json` completes successfully
    - Mutation score ≥80% for all 5 utility files (or >95% aggregate)
    - HTML report generated in `coverage/mutation-report/batch-1.html`
    - Execution time <45 seconds
    - Zero killed tests (all pass)
    - No survived mutations beyond documented escape scenarios
  - **Dependencies**: 1.2, 1.3, 1.4, 1.5, 1.6 (all tests written)
  - **Estimated Effort**: 1.5 hours (includes config creation + run + fixes)
  - **Files Modified**: 
    - `stryker-batch-1.config.json` (new)
    - Test files may be adjusted based on Stryker report
  - **Rollback**: Remove config; revert test changes if mutation score regression

- [ ] **1.8 Document results in MUTATION_TESTING.md (Batch 1 summary)**
  - **AC**:
    - `MUTATION_TESTING.md` created at project root
    - Section "Batch 1: Utilities Completion" documents:
      - All 5 files listed with their mutation scores
      - Total test count (≥15)
      - Key mutation escape scenarios caught per file
      - Execution time (should be <45s)
      - Any notable patterns or techniques
    - Links to `coverage/mutation-report/batch-1.html`
    - Notes on Phase 2 readiness
  - **Dependencies**: 1.7 (Stryker report available)
  - **Estimated Effort**: 1 hour
  - **Files Modified**: `MUTATION_TESTING.md` (new)
  - **Rollback**: Remove or revert file

---

## Phase 2: Real Hooks Batch (Batch 2) — 11 Tasks

**ADAPTED TO REAL CONSORCIO-WEB HOOKS**: Tests for actual hooks with async, storage, API, Zustand, and GEE integrations.

- [ ] **2.1 Create src/hooks/__tests__/setup.ts with hook testing utilities**
   - **AC**:
     - File created at `src/hooks/__tests__/setup.ts`
     - Exports `renderHookWithProviders` wrapper function
     - Exports `mockLocalStorage` factory with getItem, setItem, removeItem, clear
     - Exports `setupFakeTimers` function returning runPending helper
     - Exports `mockFetchAPI` for async hook testing
     - Exports `mockAuthStore` factory (Zustand mock for useAuth)
     - Exports `mockSupabaseClient` factory (for useContactVerification)
     - Exports `mockLeafletMap` factory (for useMapReady)
     - All mocks use Vitest (`vi.fn()`, `vi.useFakeTimers()`)
     - No tests executed, setup only
   - **Dependencies**: None (foundation task for Batch 2)
   - **Estimated Effort**: 2 hours (more mocks needed for real hooks)
   - **Files Modified**: `src/hooks/__tests__/setup.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.2 Write src/hooks/__tests__/useAuth.test.ts (Zustand + role checking)**
   - **AC**:
     - Tests useAuth initialization (auto-initialize on mount)
     - Tests role checking utilities (hasRole, isAdmin, isOperador, isStaff, isCiudadano)
     - Tests canAccess with role arrays and empty allowedRoles
     - Tests login/logout/register async actions
     - Tests isAuthenticated derived state (user + !loading + initialized)
     - Tests role derivation from profile.rol
     - Tests useShallow selector (memoization)
     - Tests error state handling
     - Tests cleanup (mocks properly reset)
     - Uses `mockAuthStore` from setup
     - At least 14 test cases
     - Mutation score ≥80% (complex hook)
   - **Dependencies**: 2.1 (setup utilities, mockAuthStore)
   - **Estimated Effort**: 3 hours
   - **Files Modified**: `src/hooks/__tests__/useAuth.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.3 Write src/hooks/__tests__/useSelectedImage.test.ts (localStorage + validation)**
   - **AC**:
     - Tests loading from localStorage on mount
     - Tests JSON validation with isValidSelectedImage guard
     - Tests writing image with timestamp (selected_at)
     - Tests clearSelectedImage clears both state and storage
     - Tests custom event dispatch (selectedImageChange)
     - Tests storage event listener (other tab changes)
     - Tests invalid data cleanup (removeItem called)
     - Tests hasSelectedImage boolean flag
     - Tests useSelectedImageListener (read-only variant)
     - Tests getSelectedImageSync sync function
     - Uses `mockLocalStorage` from setup
     - At least 12 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockLocalStorage)
   - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useSelectedImage.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.4 Write src/hooks/__tests__/useJobStatus.test.ts (polling + async)**
   - **AC**:
     - Tests initial IDLE status with null jobId
     - Tests polling interval (2 second check)
     - Tests status transitions (PENDING → SUCCESS/FAILURE)
     - Tests SUCCESS status sets result and calls onCompleted callback
     - Tests FAILURE status sets error message
     - Tests polling stops on SUCCESS or FAILURE
     - Tests cleanup (clearInterval on unmount)
     - Tests API error handling with apiFetch mock
     - Tests dependency array (jobId changes trigger new polling)
     - Tests onCompleted callback dependency handling
     - Uses `mockFetchAPI` from setup
     - At least 12 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockFetchAPI)
     - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useJobStatus.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.5 Write src/hooks/__tests__/useMapReady.test.ts (Leaflet lifecycle)**
   - **AC**:
     - Tests invalidateSize called immediately on mount
     - Tests scheduled invalidations (0ms, 100ms, 300ms timeouts)
     - Tests requestAnimationFrame scheduling
     - Tests window resize listener (handleResize fires invalidateSize)
     - Tests document visibilitychange listener (visible state triggers invalidation)
     - Tests ResizeObserver for container size changes
     - Tests cleanup (all timeouts cleared, listeners removed)
     - Tests hasInitialized flag prevents double RAF firing
     - Uses `mockLeafletMap` from setup with invalidateSize mock
     - At least 10 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockLeafletMap)
   - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useMapReady.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.6 Write src/hooks/__tests__/useInfrastructure.test.ts (API fetching + Promise.all)**
   - **AC**:
     - Tests loading state transitions (false → true → false)
     - Tests fetchInfrastructure calls both API endpoints (Promise.all)
     - Tests assets and intersections state updates
     - Tests error handling (API failure, network error)
     - Tests createAsset action (POST request, state update)
     - Tests refresh function re-fetches data
     - Tests cleanup and dependency array behavior
     - Uses `mockFetchAPI` from setup
     - Mocks both `/infrastructure/assets` and `/infrastructure/potential-intersections`
     - At least 10 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockFetchAPI)
   - **Estimated Effort**: 2 hours
   - **Files Modified**: `src/hooks/__tests__/useInfrastructure.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.7 Write src/hooks/__tests__/useGEELayers.test.ts (GEE API + validation)**
   - **AC**:
     - Tests loading layers with layerNames option
     - Tests enabled option (disabled skips loading)
     - Tests parseFeatureCollection validation
     - Tests partial layer load (some layers fail, some succeed)
     - Tests error handling (no layers loaded sets error)
     - Tests reload function triggers fresh fetch
     - Tests layersArray derived state formatting
     - Tests dependency array (layerNames, enabled changes trigger reload)
     - Uses `mockFetchAPI` from setup
     - Mocks GEE endpoints for each layer
     - At least 11 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockFetchAPI)
   - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useGEELayers.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.8 Write src/hooks/__tests__/useImageComparison.test.ts (dual image state)**
   - **AC**:
     - Tests loading from localStorage with validation
     - Tests setLeftImage updates comparison state
     - Tests setRightImage updates comparison state
     - Tests setEnabled toggles comparison.enabled
     - Tests clearComparison clears state and storage
     - Tests custom event dispatch (imageComparisonChange)
     - Tests storage event listener (other tab changes)
     - Tests isReady flag (both images set)
     - Tests useImageComparisonListener (read-only variant)
     - Tests localStorage persistence across updates
     - Uses `mockLocalStorage` from setup
     - At least 12 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockLocalStorage)
   - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useImageComparison.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.9 Write src/hooks/__tests__/useContactVerification.test.ts (OAuth + email OTP)**
   - **AC**:
     - Tests contactoVerificado derivation from authStore user state
     - Tests loginWithGoogle OAuth flow with error handling
     - Tests sendMagicLink with email validation
     - Tests magic link sent state and email storage
     - Tests logout flow with Supabase signOut
     - Tests resetVerificacion clears magic link state
     - Tests onVerified callback with user email and name
     - Tests metodoVerificacion switching
     - Tests Mantine notifications calls
     - Uses `mockSupabaseClient` from setup
     - Uses `mockAuthStore` for user/profile state
     - At least 12 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockSupabaseClient, mockAuthStore)
   - **Estimated Effort**: 2.5 hours
   - **Files Modified**: `src/hooks/__tests__/useContactVerification.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.10 Write src/hooks/__tests__/useCaminosColoreados.test.ts (domain-specific)**
   - **AC**:
     - Tests loading caminos data from GEE endpoint
     - Tests parsing CaminosColoreados response structure
     - Tests consorcios array extraction
     - Tests metadata aggregation (total_tramos, total_consorcios, total_km)
     - Tests error handling (HTTP errors, network failures)
     - Tests reload function re-fetches all data
     - Tests FeatureCollection construction from response
     - Uses `mockFetchAPI` from setup
     - Mocks `/api/v1/gee/layers/caminos/coloreados` endpoint
     - At least 10 test cases
     - Mutation score ≥80%
   - **Dependencies**: 2.1 (setup utilities, mockFetchAPI)
   - **Estimated Effort**: 2 hours
   - **Files Modified**: `src/hooks/__tests__/useCaminosColoreados.test.ts` (new)
   - **Rollback**: Remove file

- [ ] **2.11 Run Stryker on Batch 2 and update MUTATION_TESTING.md**
   - **AC**:
     - `stryker-batch-2.config.json` created at project root
     - `stryker run stryker-batch-2.config.json` completes successfully
     - Mutation score ≥80% for all 9 REAL hooks
     - HTML report generated in `coverage/mutation-report/batch-2.html`
     - Execution time <2 minutes (larger test set)
     - Zero killed tests
     - `MUTATION_TESTING.md` updated with Batch 2 section:
       - All 9 hooks listed with mutation scores (useAuth, useSelectedImage, useJobStatus, useMapReady, useInfrastructure, useGEELayers, useImageComparison, useContactVerification, useCaminosColoreados)
       - Total test count (≥70 for real hooks)
       - Key patterns caught: Zustand mocking, localStorage validation, polling, OAuth flows, GEE integration, FeatureCollection parsing
       - Execution time logged
       - Phase 3 readiness notes
   - **Dependencies**: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10 (all 9 hook tests)
   - **Estimated Effort**: 2.5 hours (config + run + fixes + doc)
   - **Files Modified**: 
     - `stryker-batch-2.config.json` (new)
     - `MUTATION_TESTING.md` (updated with real hook results)
     - Hook test files may be adjusted based on Stryker report
   - **Rollback**: Remove config; revert test changes if regression

---

## Phase 3: Store & Components Batch (Batch 3) — 10 Tasks

High-complexity store reducers, React components with integration points. Tests mock child components and providers.

- [ ] **3.1 Create src/components/__tests__/setup.tsx with component testing utilities**
  - **AC**:
    - File created at `src/components/__tests__/setup.tsx`
    - Exports `renderComponent` wrapper function with provider support
    - Exports `mockChildComponent` factory for mocking child components
    - Exports `screen` and `within` utilities from @testing-library/react
    - Exports mock context provider (AuthProvider, AppProvider, etc.)
    - Exports default mock props for common component types
    - All mocks use Vitest (`vi.fn()`)
    - No tests executed, setup only
  - **Dependencies**: None (foundation task for Batch 3)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: `src/components/__tests__/setup.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.2 Write src/store/__tests__/authStore.test.ts (reducer testing)**
  - **AC**:
    - Tests initial state
    - Tests login action (state mutation to authenticated)
    - Tests logout action (state reset)
    - Tests error action (error state captured)
    - Tests token mutation/update
    - Tests user data in state
    - Tests selector functions
    - Tests state immutability (reducers don't mutate input)
    - At least 12 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `src/store/__tests__/authStore.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **3.3 Write src/store/__tests__/appStore.test.ts (complex store logic)**
  - **AC**:
    - Tests global app state (theme, layout, notifications, etc.)
    - Tests multiple reducers/slices
    - Tests selector composition
    - Tests middleware dispatch calls (if applicable)
    - Tests async actions (thunks, if used)
    - Tests state persistence (if integrated with storage)
    - Tests action type mutations
    - At least 15 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 2.5 hours
  - **Files Modified**: `src/store/__tests__/appStore.test.ts` (new)
  - **Rollback**: Remove file

- [ ] **3.4 Write src/components/Modal/__tests__/index.test.tsx (simple component, event handling)**
  - **AC**:
    - Tests modal rendering (visible/hidden based on isOpen prop)
    - Tests close button click handler
    - Tests Escape key closes modal
    - Tests portal rendering (or appropriate container)
    - Tests children rendering
    - Tests event handler invocation
    - Uses renderComponent from setup
    - At least 10 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: `src/components/Modal/__tests__/index.test.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.5 Write src/components/Form/__tests__/index.test.tsx (complex component, field arrays)**
  - **AC**:
    - Tests form field rendering (input, select, textarea types)
    - Tests field array operations (add field, remove field, move field)
    - Tests conditional field rendering
    - Tests validation error messages
    - Tests submit button state (disabled if invalid)
    - Tests form submission handler
    - Tests field binding (value, onChange)
    - Uses renderComponent with form context
    - At least 15 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 3 hours
  - **Files Modified**: `src/components/Form/__tests__/index.test.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.6 Write src/components/DataTable/__tests__/index.test.tsx (data-driven, sorting/filtering)**
  - **AC**:
    - Tests table rendering with columns and rows
    - Tests column header rendering
    - Tests sort direction mutations (asc → desc)
    - Tests sorting by different columns
    - Tests filtering by column value
    - Tests pagination integration (offset/limit)
    - Tests empty state (no data)
    - Tests conditional rendering of elements
    - Uses renderComponent
    - At least 15 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 3 hours
  - **Files Modified**: `src/components/DataTable/__tests__/index.test.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.7 Write src/components/Layout/__tests__/index.test.tsx (layout conditionals)**
  - **AC**:
    - Tests conditional rendering of layout sections (header, sidebar, main, footer)
    - Tests responsive behavior (mobile vs desktop rendering)
    - Tests navigation rendering and linking
    - Tests conditional sections based on props
    - Tests nested layout composition
    - At least 10 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1 (setup utilities)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `src/components/Layout/__tests__/index.test.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.8 Write src/pages/Dashboard/__tests__/index.test.tsx (page-level integration)**
  - **AC**:
    - Tests page mounting and data fetching
    - Tests loading state display
    - Tests error state display
    - Tests data rendering and list items
    - Tests filtering/sorting interactions
    - Tests empty state display
    - Tests navigation/routing integration
    - Uses renderComponent with all providers (auth, app, etc.)
    - At least 12 test cases
    - Mutation score ≥75%
  - **Dependencies**: 3.1, 3.2, 3.3 (store setup, component patterns)
  - **Estimated Effort**: 2.5 hours
  - **Files Modified**: `src/pages/Dashboard/__tests__/index.test.tsx` (new)
  - **Rollback**: Remove file

- [ ] **3.9 Run Stryker on Batch 3 and update MUTATION_TESTING.md**
  - **AC**:
    - `stryker-batch-3.config.json` created at project root
    - `stryker run stryker-batch-3.config.json` completes successfully
    - Mutation score ≥80% for all store and component files (or >95% aggregate)
    - HTML report generated in `coverage/mutation-report/batch-3.html`
    - Execution time <2 minutes
    - Zero killed tests
    - `MUTATION_TESTING.md` updated with Batch 3 section:
      - All 9 files listed with mutation scores
      - Total test count (≥30+)
      - Component-specific patterns caught (portal, event handlers, conditionals)
      - Store patterns (reducer, selector mutations)
      - Execution time logged
  - **Dependencies**: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8 (all store/component tests)
  - **Estimated Effort**: 2 hours (config + run + fixes + doc)
  - **Files Modified**: 
    - `stryker-batch-3.config.json` (new)
    - `MUTATION_TESTING.md` (updated)
    - Test files may be adjusted
  - **Rollback**: Remove config; revert test changes if regression

- [ ] **3.10 Create MUTATION_ROLLBACK.md runbook**
  - **AC**:
    - File created at project root: `MUTATION_ROLLBACK.md`
    - Documents pre-batch checkpoints (baseline tagging, feature branch naming)
    - Documents during-batch rollback steps (identify problematic test, fix, re-run)
    - Documents post-batch rollback (full batch revert, post-mortem)
    - Documents emergency rollback (git revert command, offline analysis)
    - Documents batch monitoring (execution time, score regression thresholds)
    - Includes command examples (git revert, stryker run, report links)
    - Includes team escalation steps
    - Clear, actionable language for on-call engineer
  - **Dependencies**: 1.8, 2.10, 3.9 (all batch results available)
  - **Estimated Effort**: 1 hour
  - **Files Modified**: `MUTATION_ROLLBACK.md` (new)
  - **Rollback**: Remove file

---

## Phase 4: CI/CD Integration — 6 Tasks

Configure GitHub Actions workflow to run mutation testing per batch, enforce thresholds, and generate reports.

- [ ] **4.1 Update .github/workflows/test.yml to add Batch 1 & 2 steps**
  - **AC**:
    - `.github/workflows/test.yml` updated (or new workflow file)
    - Workflow triggers on PR and push to main/develop
    - Step 1: Run Batch 1 tests and Stryker (stryker run stryker-batch-1.config.json)
    - Step 2: Run Batch 2 tests and Stryker (stryker run stryker-batch-2.config.json)
    - Step 3: Upload batch HTML reports as workflow artifacts
    - Steps report mutation scores in job summary
    - Workflow fails if any batch ≥80% score not met
    - Batch 1 + 2 completes in <2 minutes total
    - Jobs use appropriate Node.js version and caching
  - **Dependencies**: None (independent CI/CD task)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `.github/workflows/test.yml` (new or updated)
  - **Rollback**: Remove workflow steps or revert file

- [ ] **4.2 Configure threshold enforcement (fail on >5% drop)**
  - **AC**:
    - GitHub branch protection rule enforces mutation score check
    - Check fails if score drops >5% from baseline
    - Baseline mutation scores recorded in `.github/mutation-baseline.json` (or similar)
    - Workflow step compares current vs baseline
    - Clear failure message shows regression breakdown
    - Only applies to PRs (not direct pushes to main)
    - Allows bypass with admin approval if needed
  - **Dependencies**: 4.1 (workflow exists)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: 
    - `.github/workflows/test.yml` (updated with check step)
    - `.github/mutation-baseline.json` (new)
  - **Rollback**: Remove branch protection rule and baseline file

- [ ] **4.3 Set up HTML report upload/archival**
  - **AC**:
    - Stryker HTML reports uploaded as workflow artifacts
    - Reports available for download on PR (for 30 days)
    - Reports linked in PR comment (via GitHub Actions)
    - Batch 1 report: `coverage/mutation-report/batch-1.html`
    - Batch 2 report: `coverage/mutation-report/batch-2.html`
    - Batch 3 report: `coverage/mutation-report/batch-3.html`
    - Reports include index, mutation details, and summary tables
    - PR comment automatically generated with report links
  - **Dependencies**: 4.1 (workflow steps generate reports)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: 
    - `.github/workflows/test.yml` (add artifact upload step)
    - `.github/workflows/comment-mutation-report.yml` (new workflow for PR comment)
  - **Rollback**: Remove artifact upload steps and comment workflow

- [ ] **4.4 Create MUTATION_TESTING.md comprehensive documentation**
  - **AC**:
    - File created at project root: `MUTATION_TESTING.md`
    - Section "Overview" explains mutation testing approach and batches
    - Section "Batch Results" includes:
      - Batch 1 results (5 files, scores, test count, execution time)
      - Batch 2 results (8 files, scores, test count, execution time)
      - Batch 3 results (9 files, scores, test count, execution time)
    - Section "Escape Scenarios" documents caught mutations per batch
    - Section "Testing Patterns" includes code examples from setup.ts files
    - Section "CI/CD Integration" explains workflow triggers and thresholds
    - Section "Performance Benchmarks" includes execution time targets
    - Section "Maintenance" covers adding new files, regression detection
    - Links to batch reports and runbook
    - Team contribution guidelines
  - **Dependencies**: 1.8, 2.10, 3.9 (batch results to summarize)
  - **Estimated Effort**: 2 hours
  - **Files Modified**: `MUTATION_TESTING.md` (consolidate + finalize)
  - **Rollback**: Remove or revert file

- [ ] **4.5 Test full CI/CD flow with sample PR**
  - **AC**:
    - Create feature branch from main: `test/mutation-ci-validation`
    - Make minor change to a single utility file test (add one test case)
    - Commit and push to origin
    - PR created against main
    - GitHub Actions workflow triggered automatically
    - Batch 1 Stryker runs successfully (<45s)
    - Batch 2 Stryker runs successfully (<1m 15s)
    - All checks pass (mutation score ≥80% both batches)
    - HTML reports generated and uploaded as artifacts
    - PR comment posted with report links
    - Reports accessible via artifact download
    - Merge PR to main
    - CI passes on merge
    - Verify mutation score baseline updated (if applicable)
  - **Dependencies**: 4.1, 4.2, 4.3 (CI/CD configured and ready)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: None (test PR only)
  - **Rollback**: Delete test PR branch and close PR

- [ ] **4.6 Team review, sign-off, and documentation completion**
  - **AC**:
    - Team lead reviews all three batch results (scores, patterns, effort)
    - Team lead reviews CI/CD configuration (workflow, thresholds, artifacts)
    - Team lead reviews documentation (MUTATION_TESTING.md, MUTATION_ROLLBACK.md)
    - All 20+ target files achieve ≥80% mutation score
    - Total test count ≥70 (15 + 25 + 30)
    - No regressions on main branch
    - Team sign-off recorded (e.g., comment in main PR or meeting notes)
    - Runbook shared with on-call rotation
    - Baseline mutation scores locked in `.github/mutation-baseline.json`
    - Next phase of mutation testing (new files, higher targets) documented as future work
  - **Dependencies**: 4.1, 4.2, 4.3, 4.4, 4.5 (full CI/CD pipeline complete)
  - **Estimated Effort**: 1.5 hours
  - **Files Modified**: None (review + approval only)
  - **Rollback**: N/A (approval task; rollback earlier tasks if rejected)

---

## Summary Table

| Phase | Tasks | Focus | Total Effort |
|-------|-------|-------|--------------|
| **Phase 1: Utilities** | 8 | Foundation, parametrization patterns | ~12 hours |
| **Phase 2: Real Hooks** | 11 | Zustand, storage, API, GEE, OAuth, polling, Leaflet | ~23 hours |
| **Phase 3: Store/Components** | 10 | Integration, complex components, reducers | ~20 hours |
| **Phase 4: CI/CD** | 6 | Workflow, thresholds, documentation | ~10 hours |
| **TOTAL** | **35** | **Real codebase + comprehensive mutation coverage** | **~65 hours** |

*Estimated effort assumes 1 developer, standard development pace, no major blockers.*
*Phase 2 effort increased due to real hook complexity (Zustand, OAuth, GEE, etc.).*

---

## Implementation Order & Dependencies

### Critical Path

1. **Phase 1 Foundation** (1.1) → All Phase 1 tests (1.2–1.6) → Stryker Batch 1 (1.7) → Documentation (1.8)
2. **Phase 2 Foundation** (2.1) → Phase 2 real hook tests (2.2–2.10) → Stryker Batch 2 (2.11)
3. **Phase 3 Foundation** (3.1) → Phase 3 tests (3.2–3.8) → Stryker Batch 3 (3.9) → Rollback Doc (3.10)
4. **Phase 4 CI/CD** (parallel with Phase 3 completion): Workflow (4.1) → Thresholds (4.2) → Upload (4.3) → Main Doc (4.4) → Validation (4.5) → Sign-off (4.6)

### Parallelization Opportunities

- **Phase 1 tests** (1.2–1.6) can be written in parallel after 1.1 is complete
- **Phase 2 tests** (2.2–2.10) can be written in parallel after 2.1 is complete (9 real hook tests)
- **Phase 3 tests** (3.2–3.8) can be written in parallel after 3.1 is complete
- **Phase 4 steps** (4.1–4.3) can be worked in parallel; 4.4 must follow 3.9; 4.5 depends on 4.1–4.3

### Recommended Wave Execution

| Wave | Tasks | Duration | Notes |
|------|-------|----------|-------|
| **Wave 1** | 1.1, 2.1, 3.1 | ~5 hours | Setup/fixture tasks (foundation) — 2.1 needs more mocks |
| **Wave 2** | 1.2–1.6, 2.2–2.10, 3.2–3.8 (parallel) | ~45 hours | Test writing (longest phase) — 9 real hooks in Phase 2 |
| **Wave 3** | 1.7, 2.11, 3.9, 3.10 (sequential) | ~7 hours | Stryker runs + rollback doc |
| **Wave 4** | 4.1–4.6 (mostly parallel) | ~9 hours | CI/CD setup + validation + sign-off |

---

## Rollback Strategy Summary

Each phase has specific rollback steps documented in individual tasks. General rollback strategy:

- **During Phase**: If mutation score <75% on any file, revert last 1–2 test commits, debug, re-write tests
- **After Phase**: If aggregate score <80%, pause, analyze Stryker report for escape patterns, adjust mocking strategy
- **Post-Merge**: If CI regression detected, revert entire batch merge commit, post-mortem, re-submit
- **Emergency**: Use `MUTATION_ROLLBACK.md` runbook for quick recovery steps

---

## Success Criteria

✅ **Implementation Complete When**:

1. All 35 tasks marked complete
2. All 20+ target files achieve ≥80% mutation score
3. Total test count ≥75 (15 + 70 + 30+)
4. Phase 2: All 9 REAL hooks tested (useAuth, useSelectedImage, useJobStatus, useMapReady, useInfrastructure, useGEELayers, useImageComparison, useContactVerification, useCaminosColoreados)
5. CI/CD workflow configured and tested
6. All batch HTML reports generated and archived
7. Documentation (MUTATION_TESTING.md, MUTATION_ROLLBACK.md) complete and shared
8. Team sign-off recorded
9. No regressions on main branch

**Estimated Timeline**: 6–8 working days (1 developer, assuming no major blockers)
