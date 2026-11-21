import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const controllerMock = vi.hoisted(() => ({
  isMobile: false,
  mapRef: { current: null },
  fitZona: vi.fn(),
  loading: false,
  loadingDates: false,
  error: null,
  result: null,
  calendarYear: 2026,
  calendarMonth: 2,
  availableDatesSet: new Set<string>(),
  selectedDay: null,
  maxCloud: '80',
  visualization: 'falso_color',
  sensor: 'sentinel2' as const,
  compositionMode: 'scene' as const,
  scenes: [],
  selectedSceneId: null,
  historicFloods: [],
  shortlists: {},
  pairs: {},
  selectedImage: null,
  comparison: null,
  comparisonReady: false,
  visOptions: [{ value: 'falso_color', label: 'Falso color' }],
  isCurrentImageSelected: false,
  setSensor: vi.fn(),
  setVisualization: vi.fn(),
  setMaxCloud: vi.fn(),
  setCompositionMode: vi.fn(),
  setSelectedDay: vi.fn(),
  setResult: vi.fn(),
  clearSelectedImage: vi.fn(),
  clearComparison: vi.fn(),
  handleSelectDay: vi.fn(),
  handleSelectScene: vi.fn(),
  handlePrevMonth: vi.fn(),
  handleNextMonth: vi.fn(),
  handleMonthYearChange: vi.fn(),
  handleSelectImage: vi.fn(),
  handleSetLeftImage: vi.fn(),
  handleSetRightImage: vi.fn(),
  setLeftImage: vi.fn(),
  setRightImage: vi.fn(),
  loadHistoricFlood: vi.fn(),
  loadShortlistScene: vi.fn(),
  publishPairFromShortlist: vi.fn(),
  updateWaterMask: vi.fn(),
}));

const { floodAnalysisMountCount, floodAnalysisUnmountCount } = vi.hoisted(() => ({
  floodAnalysisMountCount: vi.fn(),
  floodAnalysisUnmountCount: vi.fn(),
}));

vi.mock('../../src/components/admin/images/useImageExplorerController', () => ({
  useImageExplorerController: () => controllerMock,
}));

vi.mock('../../src/components/admin/images/ImageExplorerFloodAnalysis', async () => {
  const { useEffect } = await import('react');
  return {
    ImageExplorerFloodAnalysis: () => {
      useEffect(() => {
        floodAnalysisMountCount();
        return () => {
          floodAnalysisUnmountCount();
        };
      }, []);
      return <div data-testid="image-explorer-detect-panel">Detect</div>;
    },
  };
});

import ImageExplorerPanel from '../../src/components/admin/images/ImageExplorerPanel';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

describe('ImageExplorerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps ImageExplorerFloodAnalysis mounted after switching away from Detectar tab', async () => {
    const user = userEvent.setup();
    render(<ImageExplorerPanel />, { wrapper });

    expect(floodAnalysisMountCount).not.toHaveBeenCalled();

    await user.click(screen.getByRole('radio', { name: 'Detectar' }));
    expect(screen.getByTestId('image-explorer-detect-panel')).toBeVisible();
    expect(floodAnalysisMountCount).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: 'Escena' }));
    expect(screen.getByTestId('image-explorer-detect-panel')).not.toBeVisible();
    expect(floodAnalysisUnmountCount).not.toHaveBeenCalled();

    await user.click(screen.getByRole('radio', { name: 'Detectar' }));
    expect(screen.getByTestId('image-explorer-detect-panel')).toBeVisible();
    expect(floodAnalysisMountCount).toHaveBeenCalledTimes(1);
  });
});
