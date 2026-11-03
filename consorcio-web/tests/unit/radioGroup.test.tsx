import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AccessibleRadioGroup } from '../../src/components/ui/accessibility';

describe('<AccessibleRadioGroup /> scoped focus & dark-mode contrast (A11Y-06)', () => {
  it('scopes ArrowDown/ArrowRight focus within each radio group ref container when multiple groups exist', () => {
    const onChangeFirst = vi.fn();
    const onChangeSecond = vi.fn();

    render(
      <MantineProvider env="test">
        <div>
          <AccessibleRadioGroup
            name="group-one"
            label="Grupo Uno"
            value="g1-a"
            onChange={onChangeFirst}
            options={[
              { value: 'g1-a', label: 'Uno A' },
              { value: 'g1-b', label: 'Uno B' },
            ]}
          />
          <AccessibleRadioGroup
            name="group-two"
            label="Grupo Dos"
            value="g2-a"
            onChange={onChangeSecond}
            options={[
              { value: 'g2-a', label: 'Dos A' },
              { value: 'g2-b', label: 'Dos B' },
            ]}
          />
        </div>
      </MantineProvider>
    );

    const groups = screen.getAllByRole('radiogroup');
    expect(groups).toHaveLength(2);

    const secondGroupFirstRadio = within(groups[1]!).getByRole('radio', { name: 'Dos A' });
    const secondGroupSecondRadio = within(groups[1]!).getByRole('radio', { name: 'Dos B' });

    secondGroupFirstRadio.focus();
    expect(secondGroupFirstRadio).toHaveFocus();

    fireEvent.keyDown(secondGroupFirstRadio, { key: 'ArrowDown' });
    expect(secondGroupSecondRadio).toHaveFocus();
  });

  it('uses theme-aware --mantine-color-blue-light instead of hardcoded light blue-0 for selected option', () => {
    render(
      <MantineProvider env="test" defaultColorScheme="dark">
        <AccessibleRadioGroup
          name="dark-group"
          label="Tema oscuro"
          value="opt-1"
          onChange={() => undefined}
          options={[
            { value: 'opt-1', label: 'Seleccionada' },
            { value: 'opt-2', label: 'No seleccionada' },
          ]}
        />
      </MantineProvider>
    );

    const selectedRadio = screen.getByRole('radio', { name: 'Seleccionada' });
    expect(selectedRadio.getAttribute('style')).toContain('var(--mantine-color-blue-light)');
    expect(selectedRadio.getAttribute('style')).not.toContain('var(--mantine-color-blue-0)');
  });
});
