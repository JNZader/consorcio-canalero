import { Group, Paper, SegmentedControl, Select, Stack, Text } from '@mantine/core';
import '@mantine/dates/styles.css';

import { IconCalendar } from '../../ui/icons';
import { ImageExplorerCalendar } from './ImageExplorerCalendar';
import { ImageExplorerInfoPanels } from './ImageExplorerInfoPanels';
import { ImageExplorerMap } from './ImageExplorerMap';
import { type ImageSensor, isOpticalSensor } from './imageExplorerUtils';
import { useImageExplorerController } from './useImageExplorerController';

export default function ImageExplorerPanel() {
  const controller = useImageExplorerController();

  return (
    <Stack gap="md">
      <Paper p="md" withBorder radius="md">
        <Group gap="md" wrap="wrap" justify="space-between">
          <SegmentedControl
            value={controller.sensor}
            onChange={(v) => {
              const nextSensor = v as ImageSensor;
              controller.setSensor(nextSensor);
              controller.setVisualization(isOpticalSensor(nextSensor) ? 'rgb' : 'vv');
              controller.setCompositionMode('scene');
              controller.setSelectedDay(null);
              controller.setResult(null);
            }}
            data={[
              { value: 'sentinel2', label: 'Sentinel-2 (óptico)' },
              { value: 'sentinel1', label: 'Sentinel-1 (SAR)' },
              { value: 'landsat8', label: 'Landsat 8' },
              { value: 'landsat7', label: 'Landsat 7' },
              { value: 'landsat5', label: 'Landsat 5' },
            ]}
          />

          <Group gap="md" wrap="wrap">
            <Select
              label="Visualizacion"
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
                    // Solo el modo. NO se limpia el día ni el resultado: el
                    // controlador ya vuelve a pedir la imagen al cambiar
                    // `compositionMode` (está en las dependencias de
                    // `fetchImageForDate`), así que limpiar obligaba a volver
                    // al calendario y elegir de nuevo la MISMA fecha para ver
                    // el otro modo.
                    controller.setCompositionMode(v);
                  }
                }}
                data={[
                  { value: 'scene', label: 'Escena individual' },
                  { value: 'composite', label: 'Compuesto experimental' },
                ]}
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
                  : 'Óptico: selecciona un día con baja nubosidad'}
              </Text>
            </Group>
          </Group>
        </Group>
      </Paper>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: controller.isMobile ? '1fr' : 'minmax(280px, 340px) 1fr',
          gap: 16,
        }}
      >
        <div>
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
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
            historicFloods={controller.historicFloods}
            onLoadHistoricFlood={controller.loadHistoricFlood}
            selectedImage={controller.selectedImage}
            onClearSelectedImage={controller.clearSelectedImage}
            comparisonReady={!!controller.comparisonReady}
            onClearComparison={controller.clearComparison}
            sensor={controller.sensor}
            scenes={controller.scenes}
            selectedSceneId={controller.selectedSceneId}
            onSelectScene={controller.handleSelectScene}
            compositionMode={controller.compositionMode}
          />
        </div>
      </div>
    </Stack>
  );
}
