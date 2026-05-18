#!/usr/bin/env node
/**
 * gen-version.mjs
 *
 * Writes ``public/version.json`` with the current git SHA + build timestamp.
 * Consumed at runtime by ``useVersionCheck`` so the SPA can detect when the
 * deployed bundle is newer than the one the user has loaded and prompt them
 * to reload. Runs on every ``npm run build`` (Cloudflare Pages does that
 * for us); locally during dev it's harmless if the file is stale because
 * the dev server isn't long-running for end users.
 */
import { execSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(__dirname, '..', 'public', 'version.json');

function git(cmd) {
  try {
    return execSync(`git ${cmd}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
      .trim();
  } catch {
    return null;
  }
}

// In Cloudflare Pages the build runs in a shallow clone with the commit SHA
// exposed via env vars (CF_PAGES_COMMIT_SHA) — fall back to that when git
// isn't usable from the build dir.
const sha =
  git('rev-parse --short=12 HEAD') ??
  process.env.CF_PAGES_COMMIT_SHA?.slice(0, 12) ??
  'unknown';
const buildTime = new Date().toISOString();

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(
  outPath,
  `${JSON.stringify({ sha, buildTime }, null, 2)}\n`,
  'utf8'
);

console.log(`[gen-version] wrote ${outPath} (sha=${sha})`);
