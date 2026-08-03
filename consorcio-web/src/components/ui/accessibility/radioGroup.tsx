import { Box, SimpleGrid, Text } from '@mantine/core';
import type { KeyboardEvent, ReactNode } from 'react';
import { useState } from 'react';
import { AccessibleError } from './primitives';

interface RadioOption {
  readonly value: string;
  readonly label: string;
  readonly icon?: ReactNode;
}

// Alias (no interface): Mantine espera un StyleProp con index signature implicita,
// que TypeScript solo infiere para type aliases.
//
// Solo la forma responsive. Existio una rama numerica por compatibilidad, pero
// al sacar `columns={4}` de `ReportFormFields` se quedo sin un solo caller — y
// un numero suelto es justo lo que rompia el formulario en 360px (4 columnas
// fijas), asi que no vale la pena dejar la puerta abierta.
type ResponsiveColumns = {
  readonly base?: number;
  readonly sm?: number;
  readonly md?: number;
};

interface AccessibleRadioGroupProps {
  readonly name: string;
  readonly label: string;
  readonly options: RadioOption[];
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly error?: string | null;
  readonly required?: boolean;
  readonly columns?: ResponsiveColumns;
}

export function AccessibleRadioGroup({
  name,
  label,
  options,
  value,
  onChange,
  error,
  required = false,
  columns = { base: 2, sm: 4 },
}: AccessibleRadioGroupProps) {
  const [focusedIndex, setFocusedIndex] = useState(() => {
    const index = options.findIndex((option) => option.value === value);
    return index >= 0 ? index : 0;
  });

  const handleKeyDown = (event: KeyboardEvent, index: number) => {
    const len = options.length;
    let newIndex = index;

    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        newIndex = (index + 1) % len;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        newIndex = (index - 1 + len) % len;
        break;
      case ' ':
      case 'Enter':
        event.preventDefault();
        onChange(options[index].value);
        return;
      default:
        return;
    }

    setFocusedIndex(newIndex);
    const button = document.querySelector(`[data-radio-index="${newIndex}"]`);
    if (button instanceof HTMLElement) button.focus();
  };

  const labelId = `${name}-label`;
  const errorId = `${name}-error`;

  return (
    <Box>
      <Text id={labelId} fw={500} size="sm" mb="xs">
        {label} {required && <span style={{ color: 'var(--mantine-color-red-6)' }}>*</span>}
      </Text>

      <SimpleGrid
        cols={columns}
        spacing="sm"
        role="radiogroup"
        aria-labelledby={labelId}
        aria-describedby={error ? errorId : undefined}
        aria-required={required}
        aria-invalid={!!error}
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
              onKeyDown={(event) => handleKeyDown(event, index)}
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
      </SimpleGrid>

      <AccessibleError id={errorId} error={error} />
    </Box>
  );
}
