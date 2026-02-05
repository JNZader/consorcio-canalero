/**
 * Componentes y utilidades de accesibilidad
 * WCAG 2.1 AA Compliance Helpers
 */

import { Alert, Box, Button, Group, Stack, Text, TextInput } from '@mantine/core';
import { type ElementType, type ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { logger } from '../../lib/logger';

// ============================================
// LIVE REGION PROVIDER
// Para anuncios a screen readers
// ============================================

interface LiveRegionContextType {
  announce: (message: string, priority?: 'polite' | 'assertive') => void;
}

const LiveRegionContext = createContext<LiveRegionContextType | null>(null);

export function LiveRegionProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [politeMessage, setPoliteMessage] = useState('');
  const [assertiveMessage, setAssertiveMessage] = useState('');
  // Track timeout IDs for cleanup
  const politeTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const assertiveTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      politeTimeoutsRef.current.forEach(clearTimeout);
      assertiveTimeoutsRef.current.forEach(clearTimeout);
    };
  }, []);

  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    if (priority === 'assertive') {
      setAssertiveMessage('');
      // Pequeno delay para asegurar que el cambio se detecte
      const timeout1 = setTimeout(() => setAssertiveMessage(message), 50);
      const timeout2 = setTimeout(() => setAssertiveMessage(''), 1000);
      // Track timeouts for cleanup
      assertiveTimeoutsRef.current.push(timeout1, timeout2);
    } else {
      setPoliteMessage('');
      const timeout1 = setTimeout(() => setPoliteMessage(message), 50);
      const timeout2 = setTimeout(() => setPoliteMessage(''), 1000);
      // Track timeouts for cleanup
      politeTimeoutsRef.current.push(timeout1, timeout2);
    }
  }, []);

  return (
    <LiveRegionContext.Provider value={{ announce }}>
      {children}

      {/* Live region para anuncios corteses (no interrumpen) */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        style={{
          position: 'absolute',
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        {politeMessage}
      </div>

      {/* Live region para anuncios urgentes (interrumpen) */}
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
        style={{
          position: 'absolute',
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        {assertiveMessage}
      </div>
    </LiveRegionContext.Provider>
  );
}

export function useLiveRegion() {
  const context = useContext(LiveRegionContext);
  if (!context) {
    // Fallback silencioso si no hay provider
    return {
      announce: (_message: string, _priority?: 'polite' | 'assertive') => {},
    };
  }
  return context;
}

// ============================================
// VISUALLY HIDDEN (SR-ONLY)
// ============================================

interface VisuallyHiddenProps {
  readonly children: ReactNode;
  readonly as?: ElementType;
}

export function VisuallyHidden({ children, as: Component = 'span' }: VisuallyHiddenProps) {
  return (
    <Component
      style={{
        position: 'absolute',
        width: 1,
        height: 1,
        padding: 0,
        margin: -1,
        overflow: 'hidden',
        clip: 'rect(0, 0, 0, 0)',
        whiteSpace: 'nowrap',
        border: 0,
      }}
    >
      {children}
    </Component>
  );
}

// ============================================
// ACCESSIBLE FORM ERROR
// ============================================

interface AccessibleErrorProps {
  readonly id: string;
  readonly error: string | null | undefined;
  readonly className?: string;
}

export function AccessibleError({ id, error, className }: AccessibleErrorProps) {
  if (!error) return null;

  return (
    <Alert
      id={id}
      color="red"
      variant="light"
      mt="xs"
      role="alert"
      aria-live="assertive"
      className={className}
      styles={{
        root: {
          borderLeft: '4px solid var(--mantine-color-red-6)',
        },
      }}
    >
      <Text size="sm">{error}</Text>
    </Alert>
  );
}

// ============================================
// ACCESSIBLE LOADING STATE
// ============================================

interface AccessibleLoaderProps {
  readonly loading: boolean;
  readonly loadingText?: string;
  readonly children: ReactNode;
  readonly announcement?: boolean;
}

export function AccessibleLoader({
  loading,
  loadingText = 'Cargando contenido',
  children,
  announcement = true,
}: AccessibleLoaderProps) {
  const { announce } = useLiveRegion();

  useEffect(() => {
    if (announcement) {
      if (loading) {
        announce(loadingText);
      } else {
        announce('Contenido cargado');
      }
    }
  }, [loading, loadingText, announcement, announce]);

  if (loading) {
    return (
      <Box py="xl" aria-live="polite" aria-busy="true">
        <Stack align="center" gap="md">
          <Box
            style={{
              width: 40,
              height: 40,
              border: '3px solid var(--mantine-color-gray-3)',
              borderTopColor: 'var(--mantine-color-blue-6)',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }}
            aria-hidden="true"
          />
          <Text size="sm" c="gray.6">
            {loadingText}...
          </Text>
        </Stack>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </Box>
    );
  }

  return <>{children}</>;
}

// ============================================
// SKIP LINKS
// ============================================

interface SkipLink {
  readonly href: string;
  readonly label: string;
}

interface SkipLinksProps {
  readonly links?: SkipLink[];
}

const DEFAULT_SKIP_LINKS: SkipLink[] = [
  { href: '#main-content', label: 'Saltar al contenido principal' },
  { href: '#primary-nav', label: 'Saltar a navegacion' },
  { href: '#footer', label: 'Saltar al pie de pagina' },
];

export function SkipLinks({ links = DEFAULT_SKIP_LINKS }: SkipLinksProps) {
  return (
    <Box
      component="nav"
      aria-label="Enlaces de salto"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        zIndex: 10000,
      }}
    >
      {links.map((link, index) => (
        <a
          key={link.href}
          href={link.href}
          style={{
            position: 'absolute',
            top: -100,
            left: index * 180,
            background: 'var(--mantine-color-blue-filled)',
            color: 'white',
            padding: '8px 16px',
            textDecoration: 'none',
            fontWeight: 500,
            borderRadius: '0 0 4px 4px',
            transition: 'top 0.2s',
            zIndex: 10000,
          }}
          onFocus={(e) => {
            e.currentTarget.style.top = '0';
          }}
          onBlur={(e) => {
            e.currentTarget.style.top = '-100px';
          }}
        >
          {link.label}
        </a>
      ))}
    </Box>
  );
}

// ============================================
// ACCESSIBLE COORDINATES INPUT
// (Alternativa accesible para seleccion de mapa)
// ============================================

interface CoordinatesInputProps {
  readonly onCoordinatesChange: (lat: number, lng: number) => void;
  readonly currentLat?: number | null;
  readonly currentLng?: number | null;
  readonly onAddressSearch?: (address: string) => Promise<{ lat: number; lng: number } | null>;
}

export function CoordinatesInput({
  onCoordinatesChange,
  currentLat,
  currentLng,
  onAddressSearch,
}: CoordinatesInputProps) {
  const [manualLat, setManualLat] = useState(currentLat?.toString() || '');
  const [manualLng, setManualLng] = useState(currentLng?.toString() || '');
  const [searchAddress, setSearchAddress] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { announce } = useLiveRegion();

  const handleManualSubmit = () => {
    const lat = Number.parseFloat(manualLat);
    const lng = Number.parseFloat(manualLng);

    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      setError('Por favor, ingresa coordenadas validas (numeros decimales)');
      announce('Error: coordenadas invalidas', 'assertive');
      return;
    }

    if (lat < -90 || lat > 90) {
      setError('La latitud debe estar entre -90 y 90');
      announce('Error: latitud fuera de rango', 'assertive');
      return;
    }

    if (lng < -180 || lng > 180) {
      setError('La longitud debe estar entre -180 y 180');
      announce('Error: longitud fuera de rango', 'assertive');
      return;
    }

    setError(null);
    onCoordinatesChange(lat, lng);
    announce(`Ubicacion establecida: latitud ${lat.toFixed(4)}, longitud ${lng.toFixed(4)}`);
  };

  const handleAddressSearch = async () => {
    if (!onAddressSearch || !searchAddress.trim()) {
      return;
    }

    setSearching(true);
    setError(null);
    announce('Buscando direccion...');

    try {
      const result = await onAddressSearch(searchAddress);
      if (result) {
        onCoordinatesChange(result.lat, result.lng);
        setManualLat(result.lat.toString());
        setManualLng(result.lng.toString());
        announce(
          `Direccion encontrada: latitud ${result.lat.toFixed(4)}, longitud ${result.lng.toFixed(4)}`
        );
      } else {
        setError('No se encontro la direccion. Intenta con otra busqueda.');
        announce('Direccion no encontrada', 'assertive');
      }
    } catch (err) {
      logger.error('Error al buscar direccion:', err);
      setError('Error al buscar la direccion');
      announce('Error en la busqueda', 'assertive');
    } finally {
      setSearching(false);
    }
  };

  return (
    <Stack gap="md">
      {/* Entrada manual de coordenadas */}
      <Box
        component="fieldset"
        style={{
          border: '1px solid var(--mantine-color-gray-4)',
          padding: '1rem',
          borderRadius: 8,
        }}
      >
        <Text component="legend" size="sm" fw={500} mb="xs">
          Opcion 1: Ingresar coordenadas manualmente
        </Text>
        <Group gap="sm" align="flex-end">
          <TextInput
            label="Latitud"
            placeholder="-32.63"
            value={manualLat}
            onChange={(e) => setManualLat(e.target.value)}
            aria-describedby="lat-format-help"
            style={{ flex: 1 }}
            inputMode="decimal"
          />
          <TextInput
            label="Longitud"
            placeholder="-62.68"
            value={manualLng}
            onChange={(e) => setManualLng(e.target.value)}
            aria-describedby="lng-format-help"
            style={{ flex: 1 }}
            inputMode="decimal"
          />
          <Button onClick={handleManualSubmit} variant="light">
            Establecer
          </Button>
        </Group>
        <Text id="lat-format-help" size="xs" c="gray.6" mt="xs">
          Formato: numeros decimales (ej: -32.63000 para latitud sur)
        </Text>
      </Box>

      {/* Busqueda por direccion */}
      {onAddressSearch && (
        <Box
          component="fieldset"
          style={{
            border: '1px solid var(--mantine-color-gray-4)',
            padding: '1rem',
            borderRadius: 8,
          }}
        >
          <Text component="legend" size="sm" fw={500} mb="xs">
            Opcion 2: Buscar por direccion
          </Text>
          <Group gap="sm">
            <TextInput
              placeholder="Ej: Ruta 9 km 312, Bell Ville, Cordoba"
              value={searchAddress}
              onChange={(e) => setSearchAddress(e.target.value)}
              aria-label="Direccion a buscar"
              style={{ flex: 1 }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleAddressSearch();
                }
              }}
            />
            <Button onClick={handleAddressSearch} loading={searching} variant="light">
              Buscar
            </Button>
          </Group>
        </Box>
      )}

      {/* Mensajes de error */}
      <AccessibleError id="coords-error" error={error} />

      {/* Coordenadas actuales */}
      {currentLat && currentLng && (
        <Alert color="green" variant="light">
          <Text size="sm">
            <strong>Ubicacion seleccionada:</strong> {currentLat.toFixed(5)},{' '}
            {currentLng.toFixed(5)}
          </Text>
        </Alert>
      )}
    </Stack>
  );
}

// ============================================
// ACCESSIBLE RADIO GROUP
// Con navegacion por flechas
// ============================================

interface RadioOption {
  readonly value: string;
  readonly label: string;
  readonly icon?: ReactNode;
}

interface AccessibleRadioGroupProps {
  readonly name: string;
  readonly label: string;
  readonly options: RadioOption[];
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly error?: string | null;
  readonly required?: boolean;
  readonly columns?: number;
}

export function AccessibleRadioGroup({
  name,
  label,
  options,
  value,
  onChange,
  error,
  required = false,
  columns = 4,
}: AccessibleRadioGroupProps) {
  const [focusedIndex, setFocusedIndex] = useState(() => {
    const idx = options.findIndex((opt) => opt.value === value);
    return idx >= 0 ? idx : 0;
  });

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    const len = options.length;
    let newIndex = index;

    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault();
        newIndex = (index + 1) % len;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault();
        newIndex = (index - 1 + len) % len;
        break;
      case ' ':
      case 'Enter':
        e.preventDefault();
        onChange(options[index].value);
        return;
      default:
        return;
    }

    setFocusedIndex(newIndex);
    // Focus en el nuevo elemento - querySelector returns Element | null
    const button = document.querySelector(`[data-radio-index="${newIndex}"]`);
    if (button instanceof HTMLElement) {
      button.focus();
    }
  };

  const labelId = `${name}-label`;
  const errorId = `${name}-error`;

  return (
    <Box>
      <Text
        id={labelId}
        fw={500}
        size="sm"
        mb="xs"
        style={required ? { '::after': { content: '" *"', color: 'red' } } : undefined}
      >
        {label} {required && <span style={{ color: 'var(--mantine-color-red-6)' }}>*</span>}
      </Text>

      <Box
        role="radiogroup"
        aria-labelledby={labelId}
        aria-describedby={error ? errorId : undefined}
        aria-required={required}
        aria-invalid={!!error}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${columns}, 1fr)`,
          gap: '0.5rem',
        }}
      >
        {options.map((option, index) => {
          const isSelected = value === option.value;
          const isFocusable = focusedIndex === index;

          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={isSelected}
              aria-label={option.label}
              tabIndex={isFocusable ? 0 : -1}
              data-radio-index={index}
              onClick={() => {
                onChange(option.value);
                setFocusedIndex(index);
              }}
              onKeyDown={(e) => handleKeyDown(e, index)}
              onFocus={() => setFocusedIndex(index)}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '0.25rem',
                padding: '1rem',
                border: `2px solid ${isSelected ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-gray-4)'}`,
                borderRadius: 8,
                background: isSelected ? 'var(--mantine-color-blue-0)' : 'transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {option.icon && <span aria-hidden="true">{option.icon}</span>}
              <Text size="sm" fw={500}>
                {option.label}
              </Text>
            </button>
          );
        })}
      </Box>

      <AccessibleError id={errorId} error={error} />
    </Box>
  );
}

// ============================================
// FOCUS TRAP HOOK
// ============================================

export function useFocusTrap(isActive: boolean, containerRef: React.RefObject<HTMLElement>) {
  useEffect(() => {
    if (!isActive || !containerRef.current) return;

    const container = containerRef.current;
    const focusableElements = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    // Guardar el elemento previamente enfocado
    const previouslyFocused = document.activeElement;

    // Enfocar el primer elemento
    firstElement.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);

    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      // Restaurar foco anterior - check if it's an HTMLElement before calling focus
      if (previouslyFocused instanceof HTMLElement) {
        previouslyFocused.focus();
      }
    };
  }, [isActive, containerRef]);
}

// ============================================
// REDUCIR MOVIMIENTO HOOK
// ============================================

export function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = globalThis.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handler = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  return prefersReducedMotion;
}
