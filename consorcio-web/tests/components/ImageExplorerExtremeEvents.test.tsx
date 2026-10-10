/**
 * Operator bridge: CHIRPS extreme events → GEE search CTA.
 * Does not own the D9 palette contract (still asserted in ImageExplorerInfoPanels.test.tsx
 * against this same component once floods leave InfoPanels).
 */
import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  chirpsZoneMmLine,
  ImageExplorerExtremeEvents,
} from '../../src/components/admin/images/ImageExplorerExtremeEvents';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const candidate = {
  id: 'ext_20150312',
  name: 'Lluvia extrema 12-15 de marzo 2015',
  date: '2015-03-14',
  description:
    'Ventanas que superaron el umbral: d3 (p99.8). Percentil maximo 99.8 sobre 1991-2025. CHIRPS ordena de forma relativa: no es una medicion en milimetros.',
  severity: 'alta',
  imagery_candidate: true,
  imagery_note: 'Candidato a imagen satelital: Sentinel-2 y Sentinel-1 disponibles.',
};

const noImagery = {
  id: 'ext_19940101',
  name: 'Lluvia extrema 1994',
  date: '1994-01-01',
  description: 'CHIRPS ordena de forma relativa: no es una medicion en milimetros.',
  severity: 'media',
  imagery_candidate: false,
  imagery_note: 'Sin imagen satelital util (anterior a 2015).',
};

describe('chirpsZoneMmLine', () => {
  it('renders d1 and d7 as a CHIRPS zone range', () => {
    expect(
      chirpsZoneMmLine({
        d1: { peak_total_mm: 94.03 },
        d7: { peak_total_mm: 121.26 },
      })
    ).toBe('CHIRPS zona: 94 mm (1 d) – 121 mm (7 d)');
  });

  it('omits the line when fired_windows has no millimetres', () => {
    expect(chirpsZoneMmLine(null)).toBeNull();
    expect(chirpsZoneMmLine({ d3: { peak_total_mm: 150 } })).toBeNull();
  });
});

describe('ImageExplorerExtremeEvents', () => {
  it('renders the operator title and CHIRPS search help', () => {
    render(
      <ImageExplorerExtremeEvents events={[candidate]} onLoadHistoricFlood={() => {}} />,
      { wrapper }
    );

    expect(screen.getByText('Eventos de lluvia extrema')).toBeInTheDocument();
    expect(screen.getByText(/publicá con Usar esta imagen/i)).toBeInTheDocument();
  });

  it('searches GEE only from the Buscar imagen button of a candidate', async () => {
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(<ImageExplorerExtremeEvents events={[candidate]} onLoadHistoricFlood={onLoad} />, {
      wrapper,
    });

    await user.click(screen.getByRole('button', { name: 'Buscar imagen' }));
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(onLoad).toHaveBeenCalledWith('ext_20150312');
  });

  it('shows every event by default and can hide those without Sentinel', async () => {
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(
      <ImageExplorerExtremeEvents events={[candidate, noImagery]} onLoadHistoricFlood={onLoad} />,
      { wrapper }
    );

    expect(screen.getByText(candidate.name)).toBeInTheDocument();
    expect(screen.getByText(noImagery.name)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sin imagen satelital útil' })).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: 'Solo con imagen Sentinel' }));

    expect(screen.getByText(candidate.name)).toBeInTheDocument();
    expect(screen.queryByText(noImagery.name)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Buscar imagen' }));
    expect(onLoad).toHaveBeenCalledWith(candidate.id);
  });

  it('treats a missing imagery_candidate as searchable (legacy three-literal cards)', async () => {
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(
      <ImageExplorerExtremeEvents
        events={[
          {
            id: 'mar_2015',
            name: 'Inundacion Marzo 2015',
            date: '2015-03-15',
            description: 'x',
            severity: 'alta',
          },
        ]}
        onLoadHistoricFlood={onLoad}
      />,
      { wrapper }
    );

    await user.click(screen.getByRole('button', { name: 'Buscar imagen' }));
    expect(onLoad).toHaveBeenCalledWith('mar_2015');
  });

  it('sorts visible events by date descending', () => {
    render(
      <ImageExplorerExtremeEvents
        events={[
          { ...candidate, id: 'older', name: 'older', date: '2015-03-14' },
          { ...candidate, id: 'newer', name: 'newer', date: '2017-02-20' },
        ]}
        onLoadHistoricFlood={() => {}}
      />,
      { wrapper }
    );

    const names = screen.getAllByText(/^(older|newer)$/).map((node) => node.textContent);
    expect(names).toEqual(['newer', 'older']);
  });

  it('shows the CHIRPS d1–d7 millimetre range on the card', () => {
    render(
      <ImageExplorerExtremeEvents
        events={[
          {
            ...candidate,
            fired_windows: {
              d1: { peak_total_mm: 94.03 },
              d7: { peak_total_mm: 121.26 },
            },
          },
        ]}
        onLoadHistoricFlood={() => {}}
      />,
      { wrapper }
    );
    expect(screen.getByText('CHIRPS zona: 94 mm (1 d) – 121 mm (7 d)')).toBeInTheDocument();
  });

  it('offers Probar este for each ranked shortlist scene, not the composite search',
    async () => {
      const onLoad = vi.fn();
      const onTry = vi.fn();
      const user = userEvent.setup();
      const row = {
        rank: 1,
        sensor: 'sentinel1',
        scene_id: 'S1_VV',
        scene_date: '2015-03-15',
        days_from_peak: 0,
        cloud_pct: null,
        score: 90,
        visualization: 'vv_flood',
      };
      render(
        <ImageExplorerExtremeEvents
          events={[candidate]}
          onLoadHistoricFlood={onLoad}
          onTryShortlist={onTry}
          shortlists={{ [candidate.id]: [row] }}
        />,
        { wrapper }
      );

      expect(screen.getByLabelText('Escenas ranqueadas')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Probar este' }));
      expect(onTry).toHaveBeenCalledTimes(1);
      expect(onTry).toHaveBeenCalledWith(row);
      expect(onLoad).not.toHaveBeenCalled();
    }
  );

  it('loads the persisted pre scene from Antes', async () => {
    const onTry = vi.fn();
    const user = userEvent.setup();
    const pre = {
      rank: 1,
      sensor: 'landsat8',
      scene_id: 'PRE',
      scene_date: '2015-02-20',
      days_from_peak: -22,
      cloud_pct: 8,
      score: 40,
      visualization: 'rgb',
    };
    render(
      <ImageExplorerExtremeEvents
        events={[candidate]}
        onLoadHistoricFlood={() => {}}
        onTryShortlist={onTry}
        pairs={{ [candidate.id]: { pre, post: null } }}
      />,
      { wrapper }
    );
    await user.click(screen.getByRole('button', { name: /Antes · L8 2015-02-20/ }));
    expect(onTry).toHaveBeenCalledWith(pre);
  });
});
