import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(import.meta.dirname, '../..');
const stylesDir = join(root, 'node_modules/@mantine/core/styles');

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (name === 'node_modules' || name === 'dist') continue;
    if (existsSync(path) && name.endsWith('.ts') === false && name.endsWith('.tsx') === false) {
      try {
        readdirSync(path);
        sourceFiles(path, out);
      } catch {
        // archivo
      }
      continue;
    }
    if (name.endsWith('.ts') || name.endsWith('.tsx')) out.push(path);
  }
  return out;
}

function importedComponents(): Set<string> {
  const names = new Set<string>();
  const re = /import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['"]@mantine\/core['"]/g;
  for (const file of sourceFiles(join(root, 'src'))) {
    const text = readFileSync(file, 'utf8');
    for (const match of text.matchAll(re)) {
      if (match[0].startsWith('import type')) continue;
      for (const part of match[1].split(',')) {
        const raw = part.trim();
        if (!raw || raw.startsWith('type ')) continue;
        const name = raw.split(/\s+as\s+/)[0].trim();
        if (/^[A-Z]/.test(name)) names.add(name);
      }
    }
  }
  return names;
}

describe('superficie CSS de Mantine', () => {
  it('no importa el bundle monolítico y cubre cada componente que tiene CSS', () => {
    const imports = readFileSync(join(root, 'src/styles/mantine-imports.ts'), 'utf8');
    expect(imports).not.toMatch(/import '@mantine\/core\/styles\.css'/);
    expect(imports).toMatch(/@mantine\/core\/styles\/baseline\.css/);
    expect(imports).toMatch(/@mantine\/core\/styles\/default-css-variables\.css/);
    expect(imports).toMatch(/@mantine\/core\/styles\/global\.css/);
    expect(imports).not.toMatch(/@mantine\/charts/);
    expect(existsSync(stylesDir)).toBe(true);

    const missing: string[] = [];
    for (const name of importedComponents()) {
      if (!existsSync(join(stylesDir, `${name}.css`))) continue;
      if (!imports.includes(`@mantine/core/styles/${name}.css`)) missing.push(name);
    }
    expect(missing).toEqual([]);
  });
});
