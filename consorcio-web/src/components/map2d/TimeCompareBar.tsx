import { Button, Group, NativeSelect, SegmentedControl, Text } from '@mantine/core';
import { useState } from 'react';
import { useImageComparison } from '../../hooks/useImageComparison';
import type { SelectedImage } from '../../hooks/useSelectedImage';
import { useSelectedImage } from '../../hooks/useSelectedImage';
import {
  fetchAnnualSentinel,
  fetchJrcOccurrence,
  fetchJrcYear,
  fetchMonthlySentinel,
  MONTHS_ES,
  monthOptions,
  type TimeProduct,
  tileThumbnailUrl,
  yearOptions,
} from '../../lib/api/timeLayers';
import styles from '../../styles/components/map.module.css';
import type { ViewMode } from './ViewModePanel';

interface TimeCompareBarProps {
  readonly onViewModeChange: (mode: ViewMode) => void;
}

function timeLayerErrorMessage(error: unknown): string {
  const status =
    typeof error === 'object' && error !== null && 'status' in error
      ? Number((error as { status: unknown }).status)
      : 0;
  if (status === 401 || status === 403) {
    return 'Para comparar fechas tenés que entrar como operador.';
  }
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo armar la imagen. Probá otro año.';
}

async function loadYear(product: TimeProduct, year: number): Promise<SelectedImage> {
  return product === 's2' ? fetchAnnualSentinel(year) : fetchJrcYear(year);
}

export function TimeCompareBar({ onViewModeChange }: TimeCompareBarProps) {
  const { setSelectedImage } = useSelectedImage();
  const { setLeftImage, setRightImage } = useImageComparison();
  const [product, setProduct] = useState<TimeProduct>('s2');
  const [beforeYear, setBeforeYear] = useState('2018');
  const [afterYear, setAfterYear] = useState(String(new Date().getFullYear()));
  const [month, setMonth] = useState(1);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const years = yearOptions(product);
  const beforeValue = years.includes(Number(beforeYear)) ? beforeYear : String(years.at(-1));
  const afterValue = years.includes(Number(afterYear)) ? afterYear : String(years[0]);
  const yearData = years.map((year) => ({ value: String(year), label: String(year) }));

  async function compareYears() {
    setBusy(true);
    setError(null);
    try {
      const [before, after] = await Promise.all([
        loadYear(product, Number(beforeValue)),
        loadYear(product, Number(afterValue)),
      ]);
      setLeftImage(before);
      setRightImage(after);
      onViewModeChange('comparison');
    } catch (err) {
      setError(timeLayerErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function showMonth(nextMonth: number) {
    setMonth(nextMonth);
    setBusy(true);
    setError(null);
    try {
      const image = await fetchMonthlySentinel(Number(afterValue), nextMonth);
      setSelectedImage(image);
      onViewModeChange('single');
      const preview = tileThumbnailUrl(image.tile_url);
      if (preview) {
        setThumbs((current) => ({ ...current, [`${afterValue}-${nextMonth}`]: preview }));
      }
    } catch (err) {
      setError(timeLayerErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function showRecurrence() {
    setBusy(true);
    setError(null);
    try {
      setSelectedImage(await fetchJrcOccurrence());
      onViewModeChange('single');
    } catch (err) {
      setError(timeLayerErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const availableMonths = monthOptions(Number(afterValue));
  const activeMonth = availableMonths.includes(month) ? month : (availableMonths.at(-1) ?? 1);

  return (
    <div data-testid="time-compare-bar">
      <Group gap="xs" align="flex-end" wrap="wrap">
        <SegmentedControl
          size="xs"
          value={product}
          onChange={(value) => setProduct(value as TimeProduct)}
          data={[
            { value: 's2', label: 'Sentinel-2 anual' },
            { value: 'jrc', label: 'Agua JRC' },
          ]}
          aria-label="Producto para comparar fechas"
        />
        <NativeSelect
          size="xs"
          label="Antes"
          data={yearData}
          value={beforeValue}
          onChange={(event) => setBeforeYear(event.currentTarget.value)}
          disabled={busy}
        />
        <NativeSelect
          size="xs"
          label="Después"
          data={yearData}
          value={afterValue}
          onChange={(event) => setAfterYear(event.currentTarget.value)}
          disabled={busy}
        />
        <Button size="xs" loading={busy} onClick={() => void compareYears()}>
          Ver comparación
        </Button>
        {product === 'jrc' ? (
          <Button size="xs" variant="default" loading={busy} onClick={() => void showRecurrence()}>
            Recurrencia histórica
          </Button>
        ) : null}
      </Group>
      {product === 's2' ? (
        <div style={{ marginTop: 8 }}>
          <Text size="xs" component="label" htmlFor="s2-month-slider">
            Mes {MONTHS_ES[activeMonth - 1]} {afterValue}
          </Text>
          <input
            id="s2-month-slider"
            data-testid="s2-month-slider"
            type="range"
            min={1}
            max={availableMonths.length}
            value={availableMonths.indexOf(activeMonth) + 1}
            disabled={busy}
            onChange={(event) => {
              const next = availableMonths[Number(event.currentTarget.value) - 1];
              if (next) void showMonth(next);
            }}
            aria-valuetext={`${MONTHS_ES[activeMonth - 1]} ${afterValue}`}
            style={{ width: '100%' }}
          />
          {/* Six columns so Ene–Dic always wrap onto two rows. A single
              44px-wide row used to clip Dic against the canvas edge. */}
          <div className={styles.monthGrid} role="group" aria-label="Miniaturas del año">
            {MONTHS_ES.map((label, index) => {
              const item = index + 1;
              const enabled = availableMonths.includes(item);
              const src = thumbs[`${afterValue}-${item}`];
              return (
                <button
                  key={label}
                  type="button"
                  data-testid={`s2-month-${item}`}
                  aria-pressed={item === activeMonth}
                  onClick={() => void showMonth(item)}
                  disabled={!enabled || busy}
                  title={enabled ? label : `${label} todavía no tiene imagen`}
                  className={styles.monthCell}
                >
                  {src ? <img src={src} alt="" width={40} height={28} /> : label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      {error ? (
        <Text size="xs" c="red" mt={6} role="alert">
          {error}
        </Text>
      ) : (
        <Text size="xs" c="dimmed" mt={6}>
          Comparar fechas
        </Text>
      )}
    </div>
  );
}
