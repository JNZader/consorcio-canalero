import { Tooltip, useMantineColorScheme } from '@mantine/core';
import { useCallback, useEffect, useState, useTransition } from 'react';
import { IconButton } from './ui/IconButton';
import { IconMoon, IconSun } from './ui/icons';

export default function ThemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const [mounted, setMounted] = useState(false);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = colorScheme === 'dark';

  // Cambiar tema usando startTransition para no bloquear la UI
  const handleToggle = useCallback(() => {
    startTransition(() => {
      setColorScheme(isDark ? 'light' : 'dark');
    });
  }, [isDark, setColorScheme]);

  // aria-label dinamico segun estado actual (WCAG 4.1.2)
  const ariaLabel = isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';

  if (!mounted) {
    return (
      <IconButton
        variant="subtle"
        size="lg"
        radius="md"
        color="gray"
        aria-label="Cargando preferencia de tema"
      >
        <div style={{ width: 18, height: 18 }} />
      </IconButton>
    );
  }

  return (
    <Tooltip label={isDark ? 'Modo claro' : 'Modo oscuro'}>
      <IconButton
        onClick={handleToggle}
        variant="subtle"
        size="lg"
        radius="md"
        color="gray"
        aria-label={ariaLabel}
        loading={isPending}
      >
        {isDark ? <IconSun size={18} /> : <IconMoon size={18} />}
      </IconButton>
    </Tooltip>
  );
}
