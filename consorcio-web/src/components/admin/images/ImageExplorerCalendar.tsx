import { ActionIcon, Group, Loader, Paper, Select, Text, UnstyledButton } from '@mantine/core';

import { IconArrowLeft, IconArrowRight } from '../../ui/icons';
import { DAY_NAMES, MONTH_NAMES } from './imageExplorerUtils';

interface ImageExplorerCalendarProps {
  year: number;
  month: number;
  availableDates: Set<string>;
  selectedDay: string | null;
  loadingDates: boolean;
  onSelectDay: (dateStr: string) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onMonthYearChange: (year: number, month: number) => void;
}

interface CalendarCellData {
  day: number;
  dateStr: string;
}

interface ImageExplorerCalendarCellProps {
  cell: CalendarCellData | null;
  index: number;
  availableDates: Set<string>;
  selectedDay: string | null;
  todayStr: string;
  onSelectDay: (dateStr: string) => void;
}

function ImageExplorerCalendarCell({
  cell,
  index,
  availableDates,
  selectedDay,
  todayStr,
  onSelectDay,
}: ImageExplorerCalendarCellProps) {
  if (!cell) return <div key={`empty-${index}`} />;

  const isAvailable = availableDates.has(cell.dateStr);
  const isSelected = selectedDay === cell.dateStr;
  const isFuture = cell.dateStr > todayStr;
  const isToday = cell.dateStr === todayStr;

  return (
    <UnstyledButton
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
        border: isSelected
          ? '2px solid var(--mantine-color-blue-6)'
          : isToday
            ? '1px solid var(--mantine-color-gray-4)'
            : '1px solid transparent',
        background: isSelected
          ? 'var(--mantine-color-blue-0)'
          : isAvailable && !isFuture
            ? 'var(--mantine-color-green-0)'
            : 'transparent',
        opacity: isFuture ? 0.3 : isAvailable ? 1 : 0.5,
        cursor: isAvailable && !isFuture ? 'pointer' : 'default',
        transition: 'all 150ms ease',
        position: 'relative',
      }}
    >
      <Text
        size="sm"
        fw={isSelected ? 700 : isAvailable ? 500 : 400}
        c={isSelected ? 'blue.7' : isAvailable ? 'dark' : 'dimmed'}
      >
        {cell.day}
      </Text>
      {isAvailable && !isFuture && (
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: isSelected ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-green-6)',
            position: 'absolute',
            bottom: 3,
          }}
        />
      )}
    </UnstyledButton>
  );
}

export function ImageExplorerCalendar(props: ImageExplorerCalendarProps) {
  const {
    year,
    month,
    availableDates,
    selectedDay,
    loadingDates,
    onSelectDay,
    onPrevMonth,
    onNextMonth,
    onMonthYearChange,
  } = props;
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const firstDay = new Date(year, month, 1);
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<CalendarCellData | null> = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({
      day: d,
      dateStr: `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
    });
  }
  const currentYear = today.getFullYear();
  const currentMonth = today.getMonth();
  const canGoNext = year < currentYear || (year === currentYear && month < currentMonth);
  const yearOptions = Array.from({ length: currentYear - 1984 + 1 }, (_, index) => {
    const optionYear = currentYear - index;
    return { value: String(optionYear), label: String(optionYear) };
  });
  const monthOptions = MONTH_NAMES.map((label, index) => ({
    value: String(index),
    label,
    disabled: year === currentYear && index > currentMonth,
  }));

  return (
    <Paper p="md" withBorder radius="md">
      <Group justify="space-between" mb="sm">
        <ActionIcon variant="subtle" onClick={onPrevMonth} aria-label="Mes anterior">
          <IconArrowLeft size={18} />
        </ActionIcon>
        <Group gap="xs">
          <Select
            aria-label="Seleccionar mes"
            value={String(month)}
            onChange={(value) => value != null && onMonthYearChange(year, Number(value))}
            data={monthOptions}
            size="xs"
            w={140}
            allowDeselect={false}
          />
          <Select
            aria-label="Seleccionar año"
            value={String(year)}
            onChange={(value) => {
              if (value == null) return;
              const nextYear = Number(value);
              const nextMonth =
                nextYear === currentYear && month > currentMonth ? currentMonth : month;
              onMonthYearChange(nextYear, nextMonth);
            }}
            data={yearOptions}
            size="xs"
            w={105}
            allowDeselect={false}
            searchable
            maxDropdownHeight={360}
            comboboxProps={{ withinPortal: true }}
          />
        </Group>
        <ActionIcon
          variant="subtle"
          onClick={onNextMonth}
          disabled={!canGoNext}
          aria-label="Mes siguiente"
        >
          <IconArrowRight size={18} />
        </ActionIcon>
      </Group>
      <div
        style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}
      >
        {DAY_NAMES.map((name) => (
          <Text key={name} ta="center" size="xs" fw={600} c="dimmed">
            {name}
          </Text>
        ))}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, 1fr)',
          gap: 2,
          position: 'relative',
        }}
      >
        {loadingDates && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              borderRadius: 'var(--mantine-radius-sm)',
            }}
          >
            <Loader size="sm" />
          </div>
        )}
        {cells.map((cell, idx) => (
          <ImageExplorerCalendarCell
            key={cell?.dateStr ?? `empty-${idx}`}
            cell={cell}
            index={idx}
            availableDates={availableDates}
            selectedDay={selectedDay}
            todayStr={todayStr}
            onSelectDay={onSelectDay}
          />
        ))}
      </div>
      <Group gap="lg" mt="sm">
        <Group gap={4}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--mantine-color-green-6)',
            }}
          />
          <Text size="xs" c="dimmed">
            Con imagenes ({availableDates.size})
          </Text>
        </Group>
        <Group gap={4}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--mantine-color-blue-6)',
            }}
          />
          <Text size="xs" c="dimmed">
            Seleccionado
          </Text>
        </Group>
      </Group>
    </Paper>
  );
}
