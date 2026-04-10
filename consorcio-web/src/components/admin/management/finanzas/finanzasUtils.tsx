import { Badge, Card, Group, Text, ThemeIcon } from '@mantine/core';
import type { ComponentType, ReactNode } from 'react';
import type { Balance, Gasto, Ingreso } from './finanzasTypes';
import { IconArrowDownRight, IconArrowUpRight, IconReportMoney } from '../../../ui/icons';

export const normalizeArray = <T,>(response: T[] | { items: T[] }): T[] =>
  Array.isArray(response) ? response : (response.items ?? []);

export function getFinanzasOptions(gastos: Gasto[], ingresos: Ingreso[], defaultCategories: string[], defaultSources: string[]) {
  const cats = [...new Set(gastos.map((g) => g.categoria).filter(Boolean))];
  const srcs = [...new Set(ingresos.map((i) => i.fuente).filter(Boolean))];

  return {
    categoryOptions: cats.length > 0 ? cats : defaultCategories,
    sourceOptions: srcs.length > 0 ? srcs : defaultSources,
  };
}

export function buildOptionData(options: string[]) {
  return options.map((option) => ({ value: option, label: option }));
}

export function addNormalizedOption(options: string[], rawValue: string) {
  const normalized = rawValue.trim().toLowerCase();
  if (!normalized) {
    return { normalized: '', nextOptions: options, changed: false };
  }

  const exists = options.some((option) => option.toLowerCase() === normalized);
  const nextOptions = exists
    ? options
    : [...options, normalized].sort((a, b) => a.localeCompare(b));

  return {
    normalized,
    nextOptions,
    changed: !exists,
  };
}

export function getBalanceCards(balance: Balance | null, currentYear: number) {
  return [
    {
      key: 'ingresos',
      title: 'Ingresos Totales',
      color: 'green',
      amount: balance?.total_ingresos ?? 0,
      description: `Cuotas e ingresos operativos ano ${currentYear}`,
      icon: IconArrowUpRight,
    },
    {
      key: 'gastos',
      title: 'Gastos Operativos',
      color: 'red',
      amount: balance?.total_gastos ?? 0,
      description: 'Obras, sueldos y mantenimiento',
      icon: IconArrowDownRight,
    },
    {
      key: 'caja',
      title: 'Caja Actual',
      color: 'blue',
      amount: balance?.balance ?? 0,
      description: 'Saldo disponible en cuenta',
      icon: IconReportMoney,
      bg: balance && balance.balance < 0 ? 'red.0' : 'blue.0',
    },
  ];
}

export function renderCategoriaBadge(categoria: string) {
  return (
    <Badge variant="light" color="gray">
      {categoria.toUpperCase()}
    </Badge>
  );
}

export function renderFuenteBadge(fuente: string) {
  return (
    <Badge variant="light" color="green">
      {fuente.toUpperCase()}
    </Badge>
  );
}

export function renderBalanceCard({
  title,
  color,
  amount,
  description,
  icon: Icon,
  bg,
}: Readonly<{
  title: string;
  color: string;
  amount: number;
  description: string;
  icon: ComponentType<{ size?: number }>;
  bg?: string;
}>): ReactNode {
  return (
    <Card withBorder padding="lg" radius="md" bg={bg}>
      <Group justify="space-between">
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          {title}
        </Text>
        <ThemeIcon color={color} variant="light">
          <Icon size={16} />
        </ThemeIcon>
      </Group>
      <Text size="xl" fw={700} mt="md">
        ${amount.toLocaleString()}
      </Text>
      <Text size="xs" c="dimmed">
        {description}
      </Text>
    </Card>
  );
}
