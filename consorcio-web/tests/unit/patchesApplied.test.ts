import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Every patch under `patches/` must actually be applied inside `node_modules`.
 *
 * `patch-package` only runs from the `postinstall` script, so a `node_modules`
 * tree that was installed before a patch landed on `main` stays silently
 * unpatched: checking out the branch does not re-run the install.
 *
 * The failure mode that motivated this guard is nasty and non-obvious. Without
 * the `@mantine/core` Transition patch, `useTransition` keeps scheduling real
 * `setTimeout` work under `env="test"`. Those timers fire AFTER the DOM
 * environment is torn down, so vitest reports
 * `ReferenceError: window is not defined` as an *unhandled* error attributed to
 * a random test file, and `vitest run` exits 1 with every single test green.
 * That poisons the pre-push CI simulation and trains people to use
 * `--no-verify`.
 *
 * This test turns that puzzle into one named, actionable failure: reinstall.
 */
const WEB_ROOT = join(import.meta.dirname, '..', '..');
const PATCHES_DIR = join(WEB_ROOT, 'patches');

interface MissingHunk {
  readonly patch: string;
  readonly target: string;
  readonly line: string;
}

/** Lines a patch adds, grouped by the `node_modules` file they belong to. */
function addedLinesByTarget(patchBody: string): Map<string, string[]> {
  const byTarget = new Map<string, string[]>();
  let target = '';

  for (const line of patchBody.split('\n')) {
    if (line.startsWith('+++ b/')) {
      target = line.slice('+++ b/'.length).trim();
      continue;
    }
    if (!target || !line.startsWith('+') || line.startsWith('+++')) {
      continue;
    }
    const added = line.slice(1).trim();
    if (added.length === 0) {
      continue;
    }
    const existing = byTarget.get(target);
    if (existing) {
      existing.push(added);
    } else {
      byTarget.set(target, [added]);
    }
  }

  return byTarget;
}

function patchFiles(): string[] {
  if (!existsSync(PATCHES_DIR)) {
    return [];
  }
  return readdirSync(PATCHES_DIR).filter((name) => name.endsWith('.patch'));
}

function missingHunks(): MissingHunk[] {
  const missing: MissingHunk[] = [];

  for (const patch of patchFiles()) {
    const body = readFileSync(join(PATCHES_DIR, patch), 'utf8');

    for (const [target, addedLines] of addedLinesByTarget(body)) {
      const targetPath = join(WEB_ROOT, target);
      if (!existsSync(targetPath)) {
        missing.push({ patch, target, line: '<file not found>' });
        continue;
      }
      const contents = readFileSync(targetPath, 'utf8');
      for (const line of addedLines) {
        if (!contents.includes(line)) {
          missing.push({ patch, target, line });
        }
      }
    }
  }

  return missing;
}

describe('patch-package patches', () => {
  it('are applied in node_modules (otherwise run `npm install`)', () => {
    expect(missingHunks()).toEqual([]);
  });

  it('finds at least one patch (otherwise the guard above is vacuous)', () => {
    expect(patchFiles().length).toBeGreaterThan(0);
  });
});
