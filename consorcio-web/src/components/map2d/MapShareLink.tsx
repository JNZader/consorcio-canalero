import { Button, Group, Modal, Text } from '@mantine/core';
import QRCode from 'qrcode';
import { useEffect, useState } from 'react';

async function copyCurrentUrl(): Promise<boolean> {
  const url = window.location.href;
  try {
    await navigator.clipboard.writeText(url);
    return true;
  } catch {
    return false;
  }
}

/** QR of the permalink. The copy/QR buttons live in Herramientas, not on the map. */
export function MapShareQrModal({
  opened,
  onClose,
}: {
  readonly opened: boolean;
  readonly onClose: () => void;
}) {
  const [svg, setSvg] = useState('');
  const url = typeof window === 'undefined' ? '' : window.location.href;

  useEffect(() => {
    if (!opened) return;
    let cancelled = false;
    void QRCode.toString(url || 'https://consorcio.local/mapa', { type: 'svg', margin: 1 }).then(
      (markup) => {
        if (!cancelled) setSvg(markup);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [opened, url]);

  return (
    <Modal opened={opened} onClose={onClose} title="Link para el campo" size="sm">
      <Text size="xs" mb="sm">
        El código incluye la cámara, las capas y la selección que están en la dirección.
      </Text>
      <div data-testid="map-share-qr-svg" dangerouslySetInnerHTML={{ __html: svg }} />
    </Modal>
  );
}

/** Field copy of the permalink, including whatever the address bar already carries. */
export function MapShareLink() {
  const [opened, setOpened] = useState(false);
  const [copied, setCopied] = useState(false);

  return (
    <>
      <Group gap={6} mt={6}>
        <Button
          size="compact-xs"
          variant="light"
          data-testid="map-copy-link"
          onClick={() => {
            void copyCurrentUrl().then(setCopied);
          }}
        >
          {copied ? 'Link copiado' : 'Copiar link'}
        </Button>
        <Button
          size="compact-xs"
          variant="subtle"
          data-testid="map-share-qr"
          onClick={() => setOpened(true)}
        >
          QR
        </Button>
      </Group>
      <MapShareQrModal opened={opened} onClose={() => setOpened(false)} />
    </>
  );
}
