import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DashboardEstadisticas } from '../../src/components/admin/management/DashboardEstadisticas';
import { apiFetch, statsApi } from '../../src/lib/api';

vi.mock('@mantine/charts', () => ({
  BarChart: () => <div data-testid="bar-chart" />,
  LineChart: () => <div data-testid="line-chart" />,
  DonutChart: () => <div data-testid="donut-chart" />,
}));

vi.mock('../../src/lib/query', () => ({
  useDashboardStats: vi.fn(),
  useMonitoringDashboard: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(),
  statsApi: {
    getHistorical: vi.fn(),
  },
}));

import { useDashboardStats, useMonitoringDashboard } from '../../src/lib/query';

const renderPanel = () =>
  render(
    <MantineProvider>
      <DashboardEstadisticas />
    </MantineProvider>
  );

describe('DashboardEstadisticas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders KPI cards and charts with fetched optional data', async () => {
    vi.mocked(useDashboardStats).mockReturnValue({
      stats: {
        denuncias: { pendiente: 2, en_revision: 3, resuelto: 1 },
        denuncias_nuevas_semana: 4,
      },
    } as never);
    vi.mocked(useMonitoringDashboard).mockReturnValue({ data: { summary: {} } } as never);

    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ total_ingresos: 1000, total_gastos: 250 } as never)
      .mockResolvedValueOnce([{ rubro: 'Mantenimiento', proyectado: 100, real: 80 }] as never);
    vi.mocked(statsApi.getHistorical).mockResolvedValue({
      items: [
        { fecha: '2026-01-01', porcentaje_area: 8 },
        { fecha: '2026-02-01', porcentaje_area: 10 },
      ],
    } as never);

    renderPanel();

    expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();
    expect(screen.getByText('Reportes Activos')).toBeInTheDocument();
    expect(screen.getByText(/Ejecuci.n Presupuestaria por Rubro/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/25%/)).toBeInTheDocument();
      expect(screen.getByText(/4/)).toBeInTheDocument();
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.getByTestId('donut-chart')).toBeInTheDocument();
    });
  });

  it('shows fallback empty states when optional calls fail', async () => {
    vi.mocked(useDashboardStats).mockReturnValue({ stats: undefined } as never);
    vi.mocked(useMonitoringDashboard).mockReturnValue({ data: undefined } as never);

    vi.mocked(apiFetch).mockRejectedValue(new Error('network'));
    vi.mocked(statsApi.getHistorical).mockRejectedValue(new Error('network'));

    renderPanel();

    expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Sin datos de presupuesto por rubro')).toBeInTheDocument();
      expect(screen.getByText('Sin datos de estado de reportes')).toBeInTheDocument();
      expect(screen.getByText(/Sin datos de evoluci.n satelital/)).toBeInTheDocument();
    });
  });

  describe('budget calculations', () => {
    it.each([
      [250, 1000, '25%'],   // 250/1000 = 25%
      [100, 400, '25%'],    // 100/400 = 25%
      [100, 500, '20%'],    // 100/500 = 20%
      [50, 200, '25%'],     // 50/200 = 25%
    ])('calculates correct budget ratio: gastos=%d / ingresos=%d = %s', async (gastos, ingresos, expectedRatio) => {
      vi.mocked(useDashboardStats).mockReturnValue({
        stats: {
          denuncias: { pendiente: 1, en_revision: 1, resuelto: 1 },
          denuncias_nuevas_semana: 1,
        },
      } as never);
      vi.mocked(useMonitoringDashboard).mockReturnValue({ data: { summary: {} } } as never);

      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ total_ingresos: ingresos, total_gastos: gastos } as never)
        .mockResolvedValueOnce([{ rubro: 'Test', proyectado: 100, real: 80 }] as never);
      vi.mocked(statsApi.getHistorical).mockResolvedValue({ items: [] } as never);

      renderPanel();

      expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();
      expect(await screen.findByText(expectedRatio)).toBeInTheDocument();
    });
  });

  describe('reportes activos calculations', () => {
    it.each([
      [2, 3, 5],           // pendiente + en_revision = 2 + 3 = 5
      [5, 10, 15],         // 5 + 10 = 15
      [10, 1, 11],         // 10 + 1 = 11
    ])('calculates active reports: pendiente=%d + en_revision=%d = %d', async (pendiente, en_revision, expected) => {
      vi.mocked(useDashboardStats).mockReturnValue({
        stats: {
          denuncias: { pendiente, en_revision, resuelto: 1 },
          denuncias_nuevas_semana: 2,
        },
      } as never);
      vi.mocked(useMonitoringDashboard).mockReturnValue({ data: { summary: {} } } as never);

      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ total_ingresos: 1000, total_gastos: 250 } as never)
        .mockResolvedValueOnce([{ rubro: 'Test', proyectado: 100, real: 80 }] as never);
      vi.mocked(statsApi.getHistorical).mockResolvedValue({ items: [] } as never);

      renderPanel();

      expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();
      expect(await screen.findByText(String(expected))).toBeInTheDocument();
    });
  });

  describe('flood history parsing', () => {
    it('calculates flood variation correctly with multiple data points', async () => {
      vi.mocked(useDashboardStats).mockReturnValue({
        stats: {
          denuncias: { pendiente: 1, en_revision: 1, resuelto: 1 },
          denuncias_nuevas_semana: 1,
        },
      } as never);
      vi.mocked(useMonitoringDashboard).mockReturnValue({ data: { summary: {} } } as never);

      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ total_ingresos: 1000, total_gastos: 250 } as never)
        .mockResolvedValueOnce([{ rubro: 'Test', proyectado: 100, real: 80 }] as never);
      
      // Data with porcentaje_area values
      vi.mocked(statsApi.getHistorical).mockResolvedValue({
        items: [
          { fecha: '2026-01-01', porcentaje_area: 10 },
          { fecha: '2026-02-01', porcentaje_area: 15 },
        ],
      } as never);

      renderPanel();

      expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();
      // Average of 10 and 15 is 12.5%
      await waitFor(() => {
        expect(screen.getByText(/12\.5%/)).toBeInTheDocument();
      });
    });

    it('uses monitoring summary data as fallback for flood percentage', async () => {
      vi.mocked(useDashboardStats).mockReturnValue({
        stats: {
          denuncias: { pendiente: 1, en_revision: 1, resuelto: 1 },
          denuncias_nuevas_semana: 1,
        },
      } as never);
      vi.mocked(useMonitoringDashboard).mockReturnValue({
        data: { summary: { porcentaje_problematico: 8.5 } },
      } as never);

      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ total_ingresos: 1000, total_gastos: 250 } as never)
        .mockResolvedValueOnce([{ rubro: 'Test', proyectado: 100, real: 80 }] as never);
      
      vi.mocked(statsApi.getHistorical).mockResolvedValue({ items: [] } as never);

      renderPanel();

      expect(await screen.findByText(/Resumen de Gesti.n/)).toBeInTheDocument();
      // Should show fallback value from monitoring data
      await waitFor(() => {
        expect(screen.getByText(/8\.5%/)).toBeInTheDocument();
      });
    });
  });
});
