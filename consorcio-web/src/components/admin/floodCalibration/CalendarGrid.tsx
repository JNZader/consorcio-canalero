import { ActionIcon, Group, Loader, Paper, Text, Tooltip } from '@mantine/core';

import { IconArrowLeft, IconArrowRight } from '../../ui/icons';
import { DAY_NAMES, getRainfallColor, getRainfallLabel, MONTH_NAMES } from './floodCalibrationUtils';

interface CalendarGridProps {
  year: number;
  month: number;
  availableDates: Set<string>;
  selectedDay: string | null;
  loadingDates: boolean;
  onSelectDay: (dateStr: string) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  rainfallByDate?: Record<string, number>;
}

export function CalendarGrid({
  year,
  month,
  availableDates,
  selectedDay,
  loadingDates,
  onSelectDay,
  onPrevMonth,
  onNextMonth,
  rainfallByDate = {},
}: CalendarGridProps) {
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const firstDay = new Date(year, month, 1);
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<{ day: number; dateStr: string } | null> = [];

  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({
      day: d,
      dateStr: `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
    });
  }

  const canGoNext =
    year < today.getFullYear() || (year === today.getFullYear() && month < today.getMonth());

  return (
    <Paper p="md" withBorder radius="md">
      <Group justify="space-between" mb="sm">
        <ActionIcon variant="subtle" onClick={onPrevMonth} aria-label="Mes anterior">
          <IconArrowLeft size={18} />
        </ActionIcon>
        <Text fw={600} size="lg">
          {MONTH_NAMES[month]} {year}
        </Text>
        <ActionIcon variant="subtle" onClick={onNextMonth} disabled={!canGoNext} aria-label="Mes siguiente">
          <IconArrowRight size={18} />
        </ActionIcon>
      </Group>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
        {DAY_NAMES.map((name) => (
          <Text key={name} ta="center" size="xs" fw={600} c="dimmed">
            {name}
          </Text>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, position: 'relative' }}>
        {loadingDates && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10, borderRadius: 'var(--mantine-radius-sm)' }}>
            <Loader size="sm" />
          </div>
        )}
        {cells.map((cell, idx) => {
          if (!cell) return <div key={`empty-${idx}`} />;
          const isAvailable = availableDates.has(cell.dateStr);
          const isSelected = selectedDay === cell.dateStr;
          const isFuture = cell.dateStr > todayStr;
          const rainfallMm = rainfallByDate[cell.dateStr];
          const rainfallBg = getRainfallColor(rainfallMm);

          const button = (
            <button
              type="button"
              key={cell.dateStr}
              disabled={!isAvailable || isFuture}
              onClick={() => isAvailable && !isFuture && onSelectDay(cell.dateStr)}
              style={{
                aspectRatio: '1',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--mantine-radius-sm)',
                border: isSelected ? '2px solid var(--mantine-color-blue-6)' : '1px solid transparent',
                background: isSelected
                  ? 'var(--mantine-color-blue-0)'
                  : rainfallBg
                    ? rainfallBg
                    : isAvailable && !isFuture
                      ? 'var(--mantine-color-green-0)'
                      : 'transparent',
                opacity: isFuture ? 0.3 : isAvailable ? 1 : 0.5,
                cursor: isAvailable && !isFuture ? 'pointer' : 'default',
                transition: 'all 150ms ease',
                position: 'relative',
              }}
            >
              <Text size="sm" fw={isSelected ? 700 : isAvailable ? 500 : 400} c={isSelected ? 'blue.7' : rainfallMm != null && rainfallMm > 30 ? 'white' : isAvailable ? 'dark' : 'dimmed'}>
                {cell.day}
              </Text>
              {isAvailable && !isFuture && (
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: isSelected ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-green-6)', position: 'absolute', bottom: 3 }} />
              )}
            </button>
          );

          if (rainfallMm != null && rainfallMm > 0) {
            return (
              <Tooltip key={cell.dateStr} label={`${rainfallMm.toFixed(1)} mm — ${getRainfallLabel(rainfallMm)}`} position="top" withArrow>
                {button}
              </Tooltip>
            );
          }
          return button;
        })}
      </div>
    </Paper>
  );
}
