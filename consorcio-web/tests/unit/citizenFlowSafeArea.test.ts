/**
 * El flujo de denuncia declara viewport-fit=cover y deja padding de
 * safe-area en el chrome fijo y en la barra inferior del formulario.
 * Con inset 0 el padding extra es 0; en un teléfono con notch deja de serlo.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('safe area del flujo de denuncia', () => {
  it('declara viewport-fit=cover en el meta viewport', () => {
    const html = readFileSync('index.html', 'utf8');
    expect(html).toContain(
      'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"'
    );
  });

  it('suma el inset en header, footer, toasts y la barra de envío', () => {
    const header = readFileSync('src/styles/components/header.module.css', 'utf8');
    const footer = readFileSync('src/styles/components/footer.module.css', 'utf8');
    const form = readFileSync('src/styles/components/form.module.css', 'utf8');
    const globalCss = readFileSync('src/styles/global.css', 'utf8');

    expect(header).toContain('padding-top: env(safe-area-inset-top, 0px)');
    expect(header).toContain('padding-left: env(safe-area-inset-left, 0px)');
    expect(footer).toContain('env(safe-area-inset-bottom, 0px)');
    expect(footer).toContain('env(safe-area-inset-left, 0px)');
    expect(form).toContain('env(safe-area-inset-bottom, 0px)');
    expect(form).toContain('env(safe-area-inset-right, 0px)');
    expect(globalCss).toContain('margin-top: env(safe-area-inset-top, 0px)');
    expect(globalCss).toMatch(/\.skip-link:focus\s*\{[^}]*env\(safe-area-inset-top, 0px\)/);
  });
});
