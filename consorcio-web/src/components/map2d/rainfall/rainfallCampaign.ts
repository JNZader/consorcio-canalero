/** Display window over one calendar-year series. Never a request parameter. */
export const CAMPAIGN_PRESET = {
  CALENDAR: 'calendario',
  CAMPAIGN: 'campana',
} as const;

export type CampaignPreset = (typeof CAMPAIGN_PRESET)[keyof typeof CAMPAIGN_PRESET];

/** spec "Campaign Display Preset": the preset is defined as *since September 1*. */
export const CAMPAIGN_START_MONTH_DAY = '09-01';
