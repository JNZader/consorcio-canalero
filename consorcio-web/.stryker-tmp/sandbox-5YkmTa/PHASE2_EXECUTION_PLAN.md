# Phase 2: Plan de Ejecución Final
## Alcanzar ≥70% Mutation Kill Rate en Todos los Hooks

**Status**: Esperando Stryker (ETA: 21:00 UTC)  
**Meta**: 9 hooks con ≥70% kill rate  
**Timeline**: ~4 horas

---

## I. ANÁLISIS INMEDIATO (Cuando Stryker termine)

### 1.1 Extraer Scores
```bash
cd ~/consorcio-canalero/consorcio-web
# El script de análisis se ejecutará automáticamente
```

**Buscar en resultados**:
- Hooks ≥70%: Verificar pero NO modificar
- Hooks 60-70%: Trabajo menor (1-2 tests)
- Hooks <60%: Prioridad alta (4-5 tests)

### 1.2 Crear Tabla de Prioridades
```
Prioridad | Hook                    | Score | Gap | Effort
---------|------------------------|-------|-----|--------
1        | useCaminosColoreados   | 45%   | 25% | HIGH
2        | useGEELayers           | 48%   | 22% | HIGH
3        | useInfrastructure      | 50%   | 20% | HIGH
4        | useContactVerification | 50%   | 20% | HIGH
5        | useAuth                | 55%   | 15% | MED
6        | useImageComparison     | 68%   | 2%  | LOW
7-9      | (Esperamos estar ≥70%) |       |     | DONE
```

---

## II. ITERACIÓN POR HOOK (30-40 min cada uno)

### 2.1 Para Cada Hook <70%:

**Paso 1: Revisar Mutaciones (5 min)**
- Abrir mutation report HTML
- Filtrar por hook específico
- Listar todas las mutaciones que sobrevivieron
- Agrupar por tipo:
  - Operadores lógicos (&&, ||)
  - Valores específicos
  - Condiciones invertidas
  - Return values

**Paso 2: Analizar Test Actual (5 min)**
- Abrir `tests/hooks/<hook>.test.ts`
- Identificar tests débiles:
  - `toBeDefined()`, `toBeTruthy()` (❌)
  - Falta de parametrización
  - Branching incompleto
  - No testean errores

**Paso 3: Aplicar Patrones (15 min)**

Usar estos patrones en orden de prioridad:

```javascript
// PATRÓN 1: Fortalecer aserciones
// ANTES
expect(data).toBeDefined()

// DESPUÉS
expect(data).toEqual(expectedValue)
expect(loading).toBe(false)
expect(error).toBeNull()
```

```javascript
// PATRÓN 2: Parametrizar variaciones
test.each([
  { input: valid, expected: result1 },
  { input: invalid, expected: result2 },
  { input: edge, expected: result3 },
])
```

```javascript
// PATRÓN 3: Cubrir error paths
test('should throw when...', () => {
  expect(() => fn(badInput)).toThrow()
})
```

```javascript
// PATRÓN 4: State transitions
// Initial, Loading, Success, Error states
test('transitions correctly', () => {
  expect(state.loading).toBe(true)  // Before
  await waitFor(...)
  expect(state.loading).toBe(false) // After
})
```

**Paso 4: Re-run Stryker (10 min)**
```bash
./run-stryker-for-hook.sh <hook-name>
```

**Paso 5: Verificar Mejora (5 min)**
- Score bajó? ❌ → Revisar qué salió mal
- Score igual? ⚠️ → Tests no matan esas mutaciones
- Score subió? ✅ → Éxito, pasar al siguiente hook

---

## III. ORDEN DE EJECUCIÓN

### Orden Recomendado (Menor → Mayor Score)

```
Hook 1: useCaminosColoreados (est. 45%)
  └─ Mutaciones escapadas: API parsing, metadata extraction
  └─ Fix: Parametrizar response shapes, specific values
  └─ Time: 40 min
  └─ Target: 70%

Hook 2: useGEELayers (est. 48%)
  └─ Mutaciones escapadas: Feature parsing, validation logic
  └─ Fix: Test cada path de validación, boundary conditions
  └─ Time: 35 min
  └─ Target: 70%

Hook 3: useInfrastructure (est. 50%)
  └─ Mutaciones escapadas: Promise.all, endpoint assignments
  └─ Fix: Parametrizar diferentes órdenes de resolución
  └─ Time: 30 min
  └─ Target: 70%

Hook 4: useContactVerification (est. 50%)
  └─ Mutaciones escapadas: OAuth/OTP state flows
  └─ Fix: Parametrizar cada estado, error cases
  └─ Time: 30 min
  └─ Target: 70%

Hook 5: useAuth (est. 55%)
  └─ Mutaciones escapadas: Role logic, store selectors
  └─ Fix: Specific values, all role combinations
  └─ Time: 25 min
  └─ Target: 70%

Hook 6: useImageComparison (est. 68%)
  └─ Mutaciones escapadas: State preservation edge cases
  └─ Fix: 1-2 parametrized tests
  └─ Time: 10 min
  └─ Target: 75%+

Hooks 7-9: Probablemente ≥70% ya
  └─ Verificar
  └─ Si <70%: Aplicar mismo proceso
```

### Timeline Estimado
```
21:00 - 21:15   Análisis de resultados
21:15 - 22:00   Hook 1 (useCaminosColoreados)  ✅ 70%
22:00 - 22:35   Hook 2 (useGEELayers)         ✅ 70%
22:35 - 23:05   Hook 3 (useInfrastructure)    ✅ 70%
23:05 - 23:40   Hook 4 (useContactVerification) ✅ 70%
23:40 - 00:05   Hook 5 (useAuth)              ✅ 70%
00:05 - 00:15   Hook 6 (useImageComparison)   ✅ 75%+
00:15 - 00:30   Verificar hooks 7-9, fix si needed
00:30 - 00:45   Lock CI/CD + documentar
```

---

## IV. CHECKPOINTS

- [ ] Stryker completó
- [ ] Análisis inicial: X hooks <70%
- [ ] Hook #1 al 70%
- [ ] Hook #2 al 70%
- [ ] Hook #3 al 70%
- [ ] Hook #4 al 70%
- [ ] Hook #5 al 70%
- [ ] Todos los 9 hooks ≥70%
- [ ] CI/CD gates actualizados
- [ ] Changes committed y documentados

---

## V. CONTINGENCY PLANS

### Si Hook tarda >40 min:
- Pausar, revisar si el patrón es correcto
- Podría necesitar más de 1-2 tests
- Considerar revertir últimos cambios y re-approach

### Si Score baja después de cambios:
- Tests nuevo pueden estar fallando
- Verificar: `npm test tests/hooks/<hook>.test.ts --run`
- Revert cambios, analizar por qué falla

### Si Stryker tarda >80 min total:
- Podría haber timeout en mutation execution
- Check: `tail -f mutation-phase-2-results.log`
- May need to re-run

### Si No Alcanzamos 70% en Algunos Hooks:
- Documentar el estado actual
- Identificar qué mutaciones específicas escapan
- Crear Phase 2 Iteration 2 para próxima sesión
- Mínimo aceptable: 60% (pero intentaremos 70%)

---

## VI. HERRAMIENTAS DISPONIBLES

### Scripts
```bash
./run-stryker-for-hook.sh <hook>    # Re-run Stryker rápido
npm test tests/hooks/               # Verificar tests pasan
```

### Documentación
- `/tmp/test-strengthening-patterns.md` - Patrones detallados
- `PHASE2_TO_70_PLAN.md` - Plan iterativo
- Este archivo - Plan de ejecución

### Monitoreo
```bash
tail -f mutation-phase-2-results.log    # Ver progreso Stryker
tail -f /tmp/stryker-analysis.log       # Ver análisis automático
```

---

## VII. ÉXITO FINAL

**Criterios de Éxito**:
- ✅ 9/9 hooks ≥70%
- ✅ Todos los tests siguen pasando
- ✅ CI/CD gates actualizados
- ✅ Changes documentados en commit

**Resultado esperado**:
- Phase 2 COMPLETADO
- Ready para Phase 3 (Components mutation testing)
- Frontend mutation testing consolidado

---

**Fase 2 Status**: EJECUCIÓN  
**Timeline**: Hoy antes de medianoche  
**Next**: Phase 3 Components (320+ files)

