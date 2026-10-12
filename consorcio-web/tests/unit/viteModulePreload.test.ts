import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { filterHtmlModulePreloadDeps } from '../../vite.modulePreload';

const here = dirname(fileURLToPath(import.meta.url));

describe('filterHtmlModulePreloadDeps', () => {
  it('keeps the shell vendors and drops charts/dropzone/maplibre', () => {
    expect(
      filterHtmlModulePreloadDeps([
        'assets/vendor-mantine-CuUNZ9dC.js',
        'assets/vendor-mantine-dates-fQk3pufK.js',
        'assets/vendor-mantine-charts-DCOwFEV6.js',
        'assets/vendor-mantine-dropzone-DNmXbY_E.js',
        'assets/vendor-maplibre-BvR9Qrq-.js',
        'assets/vendor-router-De6djhwO.js',
      ]),
    ).toEqual([
      'assets/vendor-mantine-CuUNZ9dC.js',
      'assets/vendor-mantine-dates-fQk3pufK.js',
      'assets/vendor-router-De6djhwO.js',
    ]);
  });
});

describe('shell does not static-import dropzone', () => {
  it('moves dropzone CSS off mantine-imports', () => {
    const imports = readFileSync(join(here, '../../src/styles/mantine-imports.ts'), 'utf8');
    const photo = readFileSync(
      join(here, '../../src/components/report-form/PhotoSection.tsx'),
      'utf8',
    );
    expect(imports).not.toMatch('@mantine/dropzone');
    expect(photo).toMatch("@mantine/dropzone/styles.css");
  });
});
