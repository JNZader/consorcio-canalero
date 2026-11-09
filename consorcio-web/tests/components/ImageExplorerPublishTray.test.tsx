import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const navigateMock = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}));

import { ImageExplorerPublishTray } from '../../src/components/admin/images/ImageExplorerPublishTray';
import {
  consumeMapPreferredView,
  MAP_PREFERRED_VIEW_KEY,
} from '../../src/lib/mapPreferredView';
import type { SelectedImage } from '../../src/hooks/useSelectedImage';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const sampleImage = {
  tile_url: 'https://ee/tiles/{z}/{x}/{y}',
  target_date: '2024-01-10',
  sensor: 'Sentinel-2',
  visualization: 'rgb',
  visualization_description: 'RGB',
  collection: 'S2',
  images_count: 1,
  dates_available: ['2024-01-10'],
} as SelectedImage;

describe('ImageExplorerPublishTray', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    sessionStorage.removeItem(MAP_PREFERRED_VIEW_KEY);
  });

  it('disables Abrir en mapa when nothing is published', () => {
    render(
      <ImageExplorerPublishTray
        selectedImage={null}
        comparison={null}
        comparisonReady={false}
        onClearSelectedImage={vi.fn()}
        onClearComparison={vi.fn()}
      />,
      { wrapper }
    );
    expect(screen.getByTestId('open-in-map-cta')).toBeDisabled();
  });

  it('opens /mapa in single mode when only an image is published', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerPublishTray
        selectedImage={sampleImage}
        comparison={null}
        comparisonReady={false}
        onClearSelectedImage={vi.fn()}
        onClearComparison={vi.fn()}
      />,
      { wrapper }
    );

    await user.click(screen.getByTestId('open-in-map-cta'));
    expect(consumeMapPreferredView()).toBe('single');
    expect(navigateMock).toHaveBeenCalledWith({ to: '/mapa' });
  });

  it('opens /mapa in comparison mode when a pair is ready', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerPublishTray
        selectedImage={null}
        comparison={{
          enabled: true,
          left: sampleImage,
          right: { ...sampleImage, target_date: '2024-01-20' },
        }}
        comparisonReady
        onClearSelectedImage={vi.fn()}
        onClearComparison={vi.fn()}
      />,
      { wrapper }
    );

    await user.click(screen.getByTestId('open-in-map-cta'));
    expect(consumeMapPreferredView()).toBe('comparison');
    expect(navigateMock).toHaveBeenCalledWith({ to: '/mapa' });
  });
});
