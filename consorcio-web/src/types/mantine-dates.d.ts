/**
 * Module augmentation for @mantine/dates to fix type issues.
 * The default types expect string values, but we use Date objects.
 */

import '@mantine/dates';

declare module '@mantine/dates' {
  // Fix: Allow Date | null for onChange when valueFormat is not specified
  export interface DatePickerInputProps {
    onChange?: ((value: Date | null) => void) | ((value: [Date | null, Date | null]) => void);
  }

  // Fix: Allow Date | null for DateInput onChange
  export interface DateInputProps {
    onChange?: (value: Date | null) => void;
  }
}
