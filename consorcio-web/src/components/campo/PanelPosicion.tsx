/**
 * Campo (PR 6, S6) — the bottom position panel, presentational.
 *
 * Renders whatever the GPS analysis produced: the neutral class line, the
 * boundary warning when the fix sits within its accuracy of a class edge,
 * the tapped-point line, and the offline chip. No map, no state — the pure
 * surface the unit tests pin (and the piece the e2e asserts by text).
 */

import type { AnalisisPosicion } from './geometriaCampo';
import type { PaqueteCampo } from './tiposCampo';
import { FRASE_SIN_SENAL, fraseLimite, frasePosicion, tituloTema } from './tiposCampo';

export interface PanelPosicionProps {
  analisis: AnalisisPosicion | null;
  temaActivo: string | null;
  paquete: PaqueteCampo | null;
  sinSenal: boolean;
  gpsError: string | null;
  claseTocada: string | null;
  precisionM: number | null;
  onCentrar: () => void;
  onTema: (clave: string) => void;
}

export function PanelPosicion({
  analisis,
  temaActivo,
  paquete,
  sinSenal,
  gpsError,
  claseTocada,
  precisionM,
  onCentrar,
  onTema,
}: PanelPosicionProps) {
  const limite =
    analisis?.enLimite && analisis.vecino
      ? fraseLimite(analisis.clase?.clase ?? '', analisis.vecino.clase)
      : analisis?.enLimite
        ? `Estás en el límite de la clase ${analisis.clase?.clase ?? ''}`
        : null;

  return (
    <div className="campo-panel" data-testid="campo-panel">
      <div className="campo-chips">
        {paquete &&
          Object.keys(paquete.temas).map((clave) => (
            <button
              key={clave}
              type="button"
              className={`campo-chip${clave === temaActivo ? ' campo-chip-activo' : ''}`}
              data-testid={`campo-tema-${clave}`}
              aria-pressed={clave === temaActivo}
              onClick={() => onTema(clave)}
            >
              {tituloTema(clave, paquete)}
            </button>
          ))}
        {sinSenal && (
          <span className="campo-chip campo-chip-offline" data-testid="campo-offline">
            {FRASE_SIN_SENAL}
          </span>
        )}
      </div>

      {gpsError ? (
        <p className="campo-linea campo-error" data-testid="campo-gps-error" role="alert">
          {gpsError}
        </p>
      ) : (
        <p className="campo-linea" data-testid="campo-clase">
          {frasePosicion(analisis?.clase?.clase ?? null)}
        </p>
      )}

      {limite && (
        <p className="campo-linea campo-limite" data-testid="campo-limite" role="status">
          {limite}
        </p>
      )}

      {claseTocada && (
        <p className="campo-linea campo-nota" data-testid="campo-tap">
          En el punto tocado: clase {claseTocada}
        </p>
      )}

      {precisionM != null && (
        <p className="campo-linea campo-nota campo-precision">
          Precisión GPS ±{Math.round(precisionM)} m
        </p>
      )}

      <div className="campo-acciones">
        <button
          type="button"
          className="campo-boton"
          data-testid="campo-centrar"
          onClick={onCentrar}
        >
          Centrar en mí
        </button>
      </div>
    </div>
  );
}
