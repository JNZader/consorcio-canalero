import {
  Accordion,
  Group,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import '@mantine/dates/styles.css';
import { useState } from 'react';

import { IconCalendar } from '../../ui/icons';
import { ImageExplorerCalendar } from './ImageExplorerCalendar';
import {
  type DetectDatePrefill,
  ImageExplorerExtremeEvents,
} from './ImageExplorerExtremeEvents';
import { ImageExplorerFloodAnalysis } from './ImageExplorerFloodAnalysis';
import { ImageExplorerInfoPanels } from './ImageExplorerInfoPanels';
import { EXPLORER_WORKSPACE_MIN_HEIGHT, ImageExplorerMap } from './ImageExplorerMap';
import { ImageExplorerPublishTray } from './ImageExplorerPublishTray';
import {
  IMAGE_EXPLORER_TAB_LABELS,
  IMAGE_EXPLORER_TABS,
  type ImageExplorerTab,
} from './imageExplorerTabs';
import { type ImageSensor, isOpticalSensor } from './imageExplorerUtils';
import { useImageExplorerController } from './useImageExplorerController';

export default function ImageExplorerPanel() {
  const controller = useImageExplorerController();
  const [tab, setTab] = useState<ImageExplorerTab>('escena');
  const [detectFloodDate, setDetectFloodDate] = useState<string | null>(null);
  const [detectNormalDate, setDetectNormalDate] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  function handleDetectFromEvent(prefill: DetectDatePrefill) {
    setSelectedEventId(prefill.eventId);
    setDetectFloodDate(prefill.floodDate);
    setDetectNormalDate(prefill.normalDate ?? null);
    setTab('detectar');
  }

  return (
    <Stack gap="md">
      <Paper p="md" withBorder radius="md">
        <Stack gap="sm">
          <Group justify="space-between" align="flex-end" wrap="wrap">
            <div>
              <Title order={4}>Explorador de imágenes</Title>
              <Text size="xs" c="dimmed">
                Escena, comparación o detección — publicá abajo y abrí el mapa.
              </Text>
            </div>
            <SegmentedControl
              value={tab}
              onChange={(v) => setTab(v as ImageExplorerTab)}
              data={IMAGE_EXPLORER_TABS.map((t) => ({
                value: t,
                label: IMAGE_EXPLORER_TAB_LABELS[t],
              }))}
              data-testid="image-explorer-tabs"
            />
          </Group>

          <ImageExplorerPublishTray
            selectedImage={controller.selectedImage}
            comparison={controller.comparison}
            comparisonReady={!!controller.comparisonReady}
            onClearSelectedImage={controller.clearSelectedImage}
            onClearComparison={controller.clearComparison}
          />

          <Group gap="md" wrap="wrap" justify="space-between">
            <SegmentedControl
              value={controller.sensor}
              onChange={(v) => {
                const nextSensor = v as ImageSensor;
                controller.setSensor(nextSensor);
                controller.setVisualization(isOpticalSensor(nextSensor) ? 'falso_color' : 'vv');
                controller.setCompositionMode(nextSensor === 'landsat7' ? 'composite' : 'scene');
                controller.setSelectedDay(null);
                controller.setResult(null);
              }}
              data={[
                { value: 'sentinel2', label: 'Sentinel-2 (óptico)' },
                { value: 'sentinel1', label: 'Sentinel-1 (SAR)' },
                { value: 'landsat9', label: 'Landsat 9' },
                { value: 'landsat8', label: 'Landsat 8' },
                { value: 'landsat7', label: 'Landsat 7' },
                { value: 'landsat5', label: 'Landsat 5' },
              ]}
            />

            <Group gap="md" wrap="wrap">
              <Select
                label="Visualización"
                value={controller.visualization}
                onChange={(v) => v && controller.setVisualization(v)}
                data={controller.visOptions}
                w={220}
                size="sm"
              />

              {controller.sensor === 'landsat7' && (
                <Select
                  label="Modo L7"
                  value={controller.compositionMode}
                  onChange={(v) => {
                    if (v === 'scene' || v === 'composite') {
                      controller.setCompositionMode(v);
                    }
                  }}
                  data={[
                    { value: 'scene', label: 'Escena individual (franjas)' },
                    { value: 'composite', label: 'Relleno SLC-off' },
                  ]}
                  description="Opcional. El relleno pide hasta 5 fechas vecinas a GEE."
                  w={210}
                  size="sm"
                />
              )}

              {isOpticalSensor(controller.sensor) && (
                <Select
                  label="Nubes max."
                  value={controller.maxCloud}
                  onChange={(v) => {
                    if (v) {
                      controller.setMaxCloud(v);
                      controller.setSelectedDay(null);
                      controller.setResult(null);
                    }
                  }}
                  data={[
                    { value: '20', label: '20%' },
                    { value: '40', label: '40%' },
                    { value: '60', label: '60%' },
                    { value: '80', label: '80%' },
                  ]}
                  w={100}
                  size="sm"
                />
              )}

              <Group gap="xs" mt="auto">
                <IconCalendar size={16} />
                <Text size="xs" c="dimmed">
                  {controller.sensor === 'sentinel1'
                    ? 'SAR funciona con nubes'
                    : 'Óptico: seleccioná un día con baja nubosidad'}
                </Text>
              </Group>
            </Group>
          </Group>
        </Stack>
      </Paper>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: controller.isMobile ? '1fr' : 'minmax(280px, 340px) 1fr',
          gap: 16,
          alignItems: 'stretch',
          minHeight: controller.isMobile ? undefined : EXPLORER_WORKSPACE_MIN_HEIGHT,
        }}
      >
        <div>
          {(tab === 'escena' || tab === 'comparar') && (
            <ImageExplorerCalendar
              year={controller.calendarYear}
              month={controller.calendarMonth}
              availableDates={controller.availableDatesSet}
              selectedDay={controller.selectedDay}
              loadingDates={controller.loadingDates}
              onSelectDay={controller.handleSelectDay}
              onPrevMonth={controller.handlePrevMonth}
              onNextMonth={controller.handleNextMonth}
              onMonthYearChange={controller.handleMonthYearChange}
            />
          )}

          {tab === 'comparar' && (
            <Paper p="sm" withBorder radius="md" mt="md">
              <Text size="sm" fw={500} mb={4}>
                Armá el par Antes / Después
              </Text>
              <Text size="xs" c="dimmed" mb="sm">
                Elegí un día en el calendario (preview a la derecha) y asignalo con Antes o
                Después. También podés partir de un evento abajo.
              </Text>
              <Group gap="xs">
                <BadgeLike
                  label={`Antes: ${controller.comparison?.left?.target_date ?? '—'}`}
                />
                <BadgeLike
                  label={`Después: ${controller.comparison?.right?.target_date ?? '—'}`}
                />
              </Group>
            </Paper>
          )}

          {tab === 'detectar' && (
            <div style={{ marginBottom: 16 }}>
              <ImageExplorerFloodAnalysis
                onSetLeftImage={controller.setLeftImage}
                onSetRightImage={controller.setRightImage}
                initialFloodDate={detectFloodDate}
                initialNormalDate={detectNormalDate}
              />
            </div>
          )}

          <Accordion
            mt="md"
            variant="separated"
            defaultValue={tab === 'detectar' ? 'eventos' : undefined}
          >
            <Accordion.Item value="eventos">
              <Accordion.Control>Eventos de lluvia extrema (atajos)</Accordion.Control>
              <Accordion.Panel>
                <ImageExplorerExtremeEvents
                  events={controller.historicFloods}
                  onLoadHistoricFlood={controller.loadHistoricFlood}
                  onTryShortlist={controller.loadShortlistScene}
                  shortlists={controller.shortlists}
                  pairs={controller.pairs}
                  loading={controller.loading}
                  onShowWaterMask={controller.updateWaterMask}
                  onDetectFlood={handleDetectFromEvent}
                  selectedEventId={selectedEventId}
                  embedded
                />
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>
          <ImageExplorerMap
            mapRef={controller.mapRef}
            loading={controller.loading}
            resultExists={!!controller.result}
            error={controller.error}
            onFitZona={controller.fitZona}
          />

          <ImageExplorerInfoPanels
            result={controller.result}
            isCurrentImageSelected={controller.isCurrentImageSelected}
            comparison={controller.comparison}
            onSelectImage={controller.handleSelectImage}
            onSetLeftImage={controller.handleSetLeftImage}
            onSetRightImage={controller.handleSetRightImage}
            selectedImage={controller.selectedImage}
            onClearSelectedImage={controller.clearSelectedImage}
            comparisonReady={!!controller.comparisonReady}
            onClearComparison={controller.clearComparison}
            sensor={controller.sensor}
            scenes={controller.scenes}
            selectedSceneId={controller.selectedSceneId}
            onSelectScene={controller.handleSelectScene}
            compositionMode={controller.compositionMode}
            hidePublishBanners
          />
        </div>
      </div>
    </Stack>
  );
}

function BadgeLike({ label }: { label: string }) {
  return (
    <Text
      size="xs"
      px={8}
      py={4}
      style={{
        background: 'var(--mantine-color-default-hover)',
        borderRadius: 4,
      }}
    >
      {label}
    </Text>
  );
}
