import { Alert, Center, Image, Loader } from '@mantine/core';
import type { ImageProps } from '@mantine/core';
import { useEffect, useState } from 'react';

import { fetchAuthenticatedBlob } from '../../lib/api';

export interface AuthenticatedImageProps extends Omit<ImageProps, 'alt' | 'src'> {
  readonly alt: string;
  readonly src: string;
}

interface ImageLoadState {
  error: boolean;
  loading: boolean;
  objectUrl: string | null;
}

const INITIAL_STATE: ImageLoadState = {
  error: false,
  loading: true,
  objectUrl: null,
};

export function AuthenticatedImage({ alt, src, ...imageProps }: AuthenticatedImageProps) {
  const [state, setState] = useState<ImageLoadState>(INITIAL_STATE);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setState(INITIAL_STATE);

    void fetchAuthenticatedBlob(src, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = window.URL.createObjectURL(blob);
        setState({ error: false, loading: false, objectUrl });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof Error && error.name === 'AbortError') return;
        setState({ error: true, loading: false, objectUrl: null });
      });

    return () => {
      controller.abort();
      if (objectUrl) {
        window.URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src]);

  if (state.loading) {
    return (
      <Center role="status" aria-label="Cargando imagen protegida" mih={100}>
        <Loader size="sm" />
      </Center>
    );
  }

  if (state.error || !state.objectUrl) {
    return (
      <Alert color="red" role="alert">
        No se pudo cargar la imagen protegida.
      </Alert>
    );
  }

  return <Image {...imageProps} src={state.objectUrl} alt={alt} />;
}
