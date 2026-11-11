import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useEffect, useState } from 'react';
import { applyBrand, getActiveBrandId } from '../../lib/applyBrand';
import {
  BRAND_CHANGE_EVENT,
  BRAND_PRESET_LIST,
  DEFAULT_BRAND_ID,
  type BrandId,
  type BrandPreset,
} from '../../lib/brandPresets';
import { showNotification } from '../../lib/notifications';
import { IconCheck, IconColorSwatch, IconInfoCircle } from '../ui/icons';
import { PageHeader } from '../ui/PageHeader';
import ProtectedRoute from './ProtectedRoute';

function SwatchRow({ preset }: { preset: BrandPreset }) {
  return (
    <Group gap={6} wrap="nowrap" aria-hidden="true">
      {preset.swatches.map((swatch) => (
        <Box
          key={swatch.label}
          title={`${swatch.label}: ${swatch.hex}`}
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: swatch.hex,
            border: '1px solid color-mix(in srgb, var(--cc-color-border) 80%, transparent)',
            flexShrink: 0,
          }}
        />
      ))}
    </Group>
  );
}

function PreviewChrome({ preset }: { preset: BrandPreset }) {
  return (
    <Stack gap="xs" mt="sm">
      <Group gap="xs">
        <Button size="compact-sm" color="institucional" variant="filled">
          Primario filled
        </Button>
        <Button size="compact-sm" color="institucional" variant="light">
          Light
        </Button>
        <Button size="compact-sm" color="institucional" variant="outline">
          Outline
        </Button>
      </Group>
      <Group gap="xs">
        <Badge color="institucional" variant="filled">
          Marca
        </Badge>
        <Badge color="exito" variant="light">
          Éxito
        </Badge>
        <Badge color="alerta" variant="light">
          Alerta
        </Badge>
        <Badge color="orange" variant="light">
          Aviso
        </Badge>
        {preset.accent ? (
          <Badge
            variant="filled"
            style={{
              background: preset.accent,
              // Oro/ámbar portal fails AA with white — dark ink on the chip.
              color: 'var(--mantine-color-dark-9)',
            }}
          >
            Acento
          </Badge>
        ) : null}
      </Group>
      <Text size="sm" c="dimmed">
        Texto atenuado · agua UI {preset.water}
        {preset.accent ? ` · acento ${preset.accent}` : ''}
      </Text>
    </Stack>
  );
}

function ThemeLabContent() {
  const [activeId, setActiveId] = useState<BrandId>(() => getActiveBrandId());

  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ brandId?: BrandId }>).detail;
      if (detail?.brandId) setActiveId(detail.brandId);
      else setActiveId(getActiveBrandId());
    };
    globalThis.addEventListener(BRAND_CHANGE_EVENT, onChange);
    return () => globalThis.removeEventListener(BRAND_CHANGE_EVENT, onChange);
  }, []);

  const selectBrand = (id: BrandId) => {
    applyBrand(id);
    setActiveId(id);
    const preset = BRAND_PRESET_LIST.find((p) => p.id === id);
    showNotification(
      'Marca aplicada',
      preset ? `«${preset.name}» quedó activa en este navegador.` : 'Preset aplicado.',
      'institucional'
    );
  };

  return (
    <Container size="xl" py="md">
      <PageHeader
        title="Laboratorio de tema"
        subtitle="Probá packs de marca en vivo. Solo este navegador; las rampas científicas del mapa no se tocan."
      />

      <Alert
        mb="lg"
        color="institucional"
        variant="light"
        icon={<IconInfoCircle size={18} />}
        title="Preview local"
      >
        La elección se guarda en <code>localStorage</code> (
        <code>cc-brand-id</code>). No es preferencia de servidor ni cambia el
        tema canónico en <code>theme.ts</code> hasta que elijas un pack y lo
        promovamos. Volvé a «Río limpio» para el default de producción.
      </Alert>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
        {BRAND_PRESET_LIST.map((preset) => {
          const selected = preset.id === activeId;
          return (
            <Card
              key={preset.id}
              padding="lg"
              radius="md"
              withBorder
              style={{
                borderColor: selected
                  ? 'var(--mantine-color-institucional-6)'
                  : undefined,
                boxShadow: selected
                  ? '0 0 0 1px var(--mantine-color-institucional-6)'
                  : undefined,
              }}
            >
              <Group justify="space-between" align="flex-start" mb="xs">
                <div>
                  <Group gap="xs" mb={4}>
                    <IconColorSwatch
                      size={20}
                      color="var(--mantine-color-institucional-6)"
                      aria-hidden="true"
                    />
                    <Title order={4}>{preset.name}</Title>
                    {preset.id === DEFAULT_BRAND_ID ? (
                      <Badge size="sm" variant="outline" color="gray">
                        Default
                      </Badge>
                    ) : null}
                  </Group>
                  <Text size="sm" c="dimmed">
                    {preset.tagline}
                  </Text>
                </div>
                {selected ? (
                  <Badge
                    leftSection={<IconCheck size={12} />}
                    color="institucional"
                    variant="filled"
                  >
                    Activo
                  </Badge>
                ) : null}
              </Group>

              <SwatchRow preset={preset} />

              <Text size="sm" mt="md">
                {preset.notes}
              </Text>

              <PreviewChrome preset={preset} />

              <Button
                mt="md"
                fullWidth
                variant={selected ? 'light' : 'filled'}
                color="institucional"
                disabled={selected}
                onClick={() => selectBrand(preset.id)}
                leftSection={<IconColorSwatch size={16} />}
              >
                {selected ? 'Preset activo' : `Aplicar «${preset.name}»`}
              </Button>
            </Card>
          );
        })}
      </SimpleGrid>
    </Container>
  );
}

export default function ThemeLabPanel() {
  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <ThemeLabContent />
    </ProtectedRoute>
  );
}
