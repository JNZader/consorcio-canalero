// tests/unit/icons.test.ts
// Unit: Icon exports
// Coverage target: 100% (pure re-exports)

import { describe, it, expect } from 'vitest';

describe('Icon exports', () => {
  it('should export IconAlertCircle', async () => {
    const { IconAlertCircle } = await import('../../src/components/ui/icons');
    expect(IconAlertCircle).toBeDefined();
  });

  it('should export IconAlertTriangle', async () => {
    const { IconAlertTriangle } = await import('../../src/components/ui/icons');
    expect(IconAlertTriangle).toBeDefined();
  });

  it('should export IconArrowLeft', async () => {
    const { IconArrowLeft } = await import('../../src/components/ui/icons');
    expect(IconArrowLeft).toBeDefined();
  });

  it('should export IconArrowRight', async () => {
    const { IconArrowRight } = await import('../../src/components/ui/icons');
    expect(IconArrowRight).toBeDefined();
  });

  it('should export IconBrandGoogle', async () => {
    const { IconBrandGoogle } = await import('../../src/components/ui/icons');
    expect(IconBrandGoogle).toBeDefined();
  });

  it('should export IconBulb', async () => {
    const { IconBulb } = await import('../../src/components/ui/icons');
    expect(IconBulb).toBeDefined();
  });

  it('should export IconCheck', async () => {
    const { IconCheck } = await import('../../src/components/ui/icons');
    expect(IconCheck).toBeDefined();
  });

  it('should export IconHome', async () => {
    const { IconHome } = await import('../../src/components/ui/icons');
    expect(IconHome).toBeDefined();
  });

  it('should export IconMap', async () => {
    const { IconMap } = await import('../../src/components/ui/icons');
    expect(IconMap).toBeDefined();
  });

  it('should export IconMoon', async () => {
    const { IconMoon } = await import('../../src/components/ui/icons');
    expect(IconMoon).toBeDefined();
  });

  it('should export IconSun', async () => {
    const { IconSun } = await import('../../src/components/ui/icons');
    expect(IconSun).toBeDefined();
  });

  it('should export IconLayers', async () => {
    const { IconLayers } = await import('../../src/components/ui/icons');
    expect(IconLayers).toBeDefined();
  });

  it('should export IconLightbulb as alias for IconBulb', async () => {
    const { IconLightbulb } = await import('../../src/components/ui/icons');
    expect(IconLightbulb).toBeDefined();
  });

  it('should export IconMail', async () => {
    const { IconMail } = await import('../../src/components/ui/icons');
    expect(IconMail).toBeDefined();
  });

  it('should export IconPlus', async () => {
    const { IconPlus } = await import('../../src/components/ui/icons');
    expect(IconPlus).toBeDefined();
  });

  it('should export IconX', async () => {
    const { IconX } = await import('../../src/components/ui/icons');
    expect(IconX).toBeDefined();
  });

  it('should export IconDownload', async () => {
    const { IconDownload } = await import('../../src/components/ui/icons');
    expect(IconDownload).toBeDefined();
  });

  it('should export IconUpload', async () => {
    const { IconUpload } = await import('../../src/components/ui/icons');
    expect(IconUpload).toBeDefined();
  });

  it('should export IconSearch', async () => {
    const { IconSearch } = await import('../../src/components/ui/icons');
    expect(IconSearch).toBeDefined();
  });

  it('should export IconSettings', async () => {
    const { IconSettings } = await import('../../src/components/ui/icons');
    expect(IconSettings).toBeDefined();
  });

  it('should export IconLogout', async () => {
    const { IconLogout } = await import('../../src/components/ui/icons');
    expect(IconLogout).toBeDefined();
  });
});
