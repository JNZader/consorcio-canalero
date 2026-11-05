import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import styles from './dashboardCharts.module.css';

interface FinanceChartRow {
  readonly rubro: string;
  readonly proyectado: number;
  readonly real: number;
}

interface ReportSlice {
  readonly name: string;
  readonly value: number;
  readonly color: string;
}

interface FloodPoint {
  readonly fecha: string;
  readonly anegamiento: number;
}

const SLICE_CLASS: Record<string, string | undefined> = {
  'red.6': styles.sliceRed,
  'orange.6': styles.sliceOrange,
  'green.6': styles.sliceGreen,
};

function miles(value: unknown): string {
  const number = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(number)) return '';
  return `$${(number / 1000).toFixed(0)}k`;
}

function porcentaje(value: unknown): string {
  const number = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(number)) return '';
  return `${number}%`;
}

export function FinanceBudgetChart({ data }: { readonly data: readonly FinanceChartRow[] }) {
  return (
    <div className={styles.chart} data-testid="bar-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={[...data]} accessibilityLayer>
          <CartesianGrid strokeDasharray="5 5" />
          <XAxis dataKey="rubro" tickLine={false} />
          <YAxis tickLine tickFormatter={miles} />
          <Tooltip formatter={(value) => miles(value)} />
          <Bar dataKey="proyectado" name="Proyectado" className={styles.barProyectado} />
          <Bar dataKey="real" name="Real" className={styles.barReal} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ReportStatusChart({ data }: { readonly data: readonly ReportSlice[] }) {
  return (
    <div className={styles.donut} data-testid="donut-chart">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart accessibilityLayer>
          <Pie
            data={[...data]}
            dataKey="value"
            nameKey="name"
            innerRadius={65}
            outerRadius={90}
            paddingAngle={0}
            labelLine
            label={({ percent }) => `${((percent ?? 0) * 100).toFixed(0)}%`}
          >
            {data.map((slice) => (
              <Cell key={slice.name} className={SLICE_CLASS[slice.color]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function FloodHistoryChart({ data }: { readonly data: readonly FloodPoint[] }) {
  return (
    <div className={styles.chart} data-testid="line-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={[...data]} accessibilityLayer>
          <CartesianGrid strokeDasharray="5 5" />
          <XAxis dataKey="fecha" tickLine={false} />
          <YAxis tickLine tickFormatter={porcentaje} />
          <Tooltip formatter={(value) => porcentaje(value)} />
          <Line
            type="monotone"
            dataKey="anegamiento"
            name="Anegamiento (%)"
            strokeWidth={2}
            dot
            className={styles.lineAnegamiento}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
