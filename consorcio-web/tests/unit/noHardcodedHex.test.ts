import { globSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * UI-04 bleed-stop. MapLibre paint, admin maps, and Google brand SVGs stay hex.
 * App chrome (Header/Footer/Login/…) must not grow new #rrggbb literals.
 */
const HEX = /#[0-9A-Fa-f]{3,8}\b/;
const SKIP =
  /\/(map2d|terrain|map|admin|report-form|verification)\/|RasterLegend\.tsx$/;

describe('UI-04 no new hex in app chrome', () => {
  it('forbids #rrggbb in components outside map/admin paint', () => {
    const files = globSync('src/components/**/*.{ts,tsx}', { cwd: process.cwd() });
    expect(files.length).toBeGreaterThan(20);

    const offenders: string[] = [];
    for (const file of files) {
      const posix = file.replaceAll('\\', '/');
      if (SKIP.test(`/${posix}`)) continue;
      const src = readFileSync(file, 'utf-8');
      if (HEX.test(src)) offenders.push(posix);
    }

    expect(offenders).toEqual([]);
  });
});
