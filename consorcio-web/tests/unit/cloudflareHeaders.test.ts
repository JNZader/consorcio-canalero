import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('Cloudflare Pages security headers', () => {
  it('allows backend raster tiles in img-src for DEM and 3D map layers', () => {
    const headers = readFileSync(join(process.cwd(), 'public/_headers'), 'utf8');
    const cspLine = headers
      .split('\n')
      .find((line) => line.trim().startsWith('Content-Security-Policy:'));

    expect(cspLine).toContain('img-src');
    expect(cspLine).toContain('https://cc10demayo-api.javierzader.com');
    expect(cspLine).toContain('https://*.javierzader.com');
  });
});
