import { ColorSwatch, Group, Stack, Text } from '@mantine/core';

interface PieChartData {
  readonly label: string;
  readonly value: number;
  readonly color: string;
}

interface PieChartProps {
  readonly data: PieChartData[];
  readonly size?: number;
  readonly showLegend?: boolean;
  readonly title?: string;
}

export default function PieChart({ data, size = 180, showLegend = true, title }: PieChartProps) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) return null;

  const radius = size / 2;
  const center = radius;

  // Calculate pie slices
  let cumulativeAngle = -90; // Start from top
  const slices = data.map((item) => {
    const percentage = (item.value / total) * 100;
    const angle = (percentage / 100) * 360;
    const startAngle = cumulativeAngle;
    const endAngle = cumulativeAngle + angle;
    cumulativeAngle = endAngle;

    // Convert angles to radians
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;

    // Calculate arc path
    const x1 = center + radius * Math.cos(startRad);
    const y1 = center + radius * Math.sin(startRad);
    const x2 = center + radius * Math.cos(endRad);
    const y2 = center + radius * Math.sin(endRad);

    const largeArc = angle > 180 ? 1 : 0;

    const pathD =
      percentage === 100
        ? // Full circle (two arcs)
          `M ${center} ${center - radius}
           A ${radius} ${radius} 0 1 1 ${center} ${center + radius}
           A ${radius} ${radius} 0 1 1 ${center} ${center - radius}`
        : `M ${center} ${center}
           L ${x1} ${y1}
           A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}
           Z`;

    return {
      ...item,
      percentage,
      pathD,
    };
  });

  return (
    <Stack gap="sm" align="center">
      {title && (
        <Text size="sm" fw={600} ta="center">
          {title}
        </Text>
      )}

      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="Grafico circular de distribucion de datos"
      >
        {slices.map((slice) => (
          <path key={slice.label} d={slice.pathD} fill={slice.color} stroke="white" strokeWidth="2" />
        ))}
        {/* Center circle for donut effect */}
        <circle cx={center} cy={center} r={radius * 0.5} fill="var(--mantine-color-body)" />
      </svg>

      {showLegend && (
        <Stack gap="xs" w="100%">
          {slices
            .filter((s) => s.percentage > 0)
            .map((slice) => (
              <Group key={slice.label} justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  <ColorSwatch color={slice.color} size={12} withShadow={false} />
                  <Text size="xs" lineClamp={1}>
                    {slice.label}
                  </Text>
                </Group>
                <Text size="xs" fw={600} c="gray.6">
                  {slice.percentage.toFixed(1)}%
                </Text>
              </Group>
            ))}
        </Stack>
      )}
    </Stack>
  );
}
