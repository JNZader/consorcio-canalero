import { Group, Paper, SegmentedControl, Select, Stack, Text } from '@mantine/core';
import '@mantine/dates/styles.css';

import { IconCalendar } from '../../ui/icons';
import { ImageExplorerCalendar } from './ImageExplorerCalendar';
import { ImageExplorerInfoPanels } from './ImageExplorerInfoPanels';
import { ImageExplorerMap } from './ImageExplorerMap';
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
              controller.setSensor(v as 'sentinel2' | 'sentinel1');
              controller.setVisualization(v === 'sentinel2' ? 'rgb' : 'vv');
              controller.setSelectedDay(null);
              controller.setResult(null);
            }}
            data={[
              { value: 'sentinel2', label: 'Sentinel-2 (Optico)' },
              { value: 'sentinel1', label: 'Sentinel-1 (SAR)' },
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

            {controller.sensor === 'sentinel2' && (
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
                {controller.sensor === 'sentinel1' ? 'SAR funciona con nubes' : 'Selecciona un dia del calendario'}
              </Text>
            </Group>
          </Group>
        </Group>
      </Paper>

      <div style={{ display: 'grid', gridTemplateColumns: controller.isMobile ? '1fr' : 'minmax(280px, 340px) 1fr', gap: 16 }}>
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
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <ImageExplorerMap
            mapRef={controller.mapRef}
            loading={controller.loading}
            resultExists={!!controller.result}
            error={controller.error}
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
          />
        </div>
      </div>
    </Stack>
  );
}
