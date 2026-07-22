# Cloudflare Pages Deployment

## Connect Repository

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) > Workers & Pages > Create application > Pages
2. Connect your GitHub repository (`consorcio-canalero`)
3. Select the branch to deploy (e.g., `main` for production)

## Build Settings

| Setting | Value |
|---------|-------|
| Framework preset | Vite |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `consorcio-web` |

## Environment Variables

Set these in **Cloudflare Dashboard > Pages project > Settings > Environment variables**:

| Variable | Value | Notes |
|----------|-------|-------|
| `VITE_API_URL` | `https://api.consorcio.example.com` | Backend API base URL |
| `VITE_MARTIN_URL` | `https://tiles.consorcio.example.com` | Public Martin/vector tiles URL |

> **Node version**: Cloudflare Pages v3 uses Node 22 by default. No need to set `NODE_VERSION`.

Set different `VITE_API_URL` values for Production and Preview environments.

> **Important:** Vite bakes `VITE_*` env vars into the bundle at build time. They are NOT runtime secrets. Changing them requires a rebuild.

## SPA Routing

The file `consorcio-web/public/_redirects` handles client-side routing by redirecting all paths to `index.html` with a 200 status. Cloudflare Pages copies files from `public/` into the build output automatically via Vite.

## Security Headers

The file `consorcio-web/public/_headers` adds production headers to Cloudflare Pages responses, including:

- security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS)
- Content Security Policy for the API, tile providers and workers
- long-lived immutable caching for hashed assets
- short/no-cache rules for service worker files

## Custom Domain

1. Go to Pages project > Custom domains > Set up a custom domain
2. Add your domain (e.g., `app.consorcio.example.com`)
3. Cloudflare will automatically provision an SSL certificate

## Preview Deployments

Every push to a non-production branch generates a preview URL at `<branch>.<project>.pages.dev`. Use different `VITE_API_URL` values for Preview vs Production environments in the dashboard.

## GitHub Actions Quality Gates

Cloudflare Pages remains responsible for building and deploying the frontend from
the connected repository. GitHub Actions provides a separate, non-deploying
quality gate in `.github/workflows/frontend.yml`:

- pull requests to `main` and manual `workflow_dispatch` runs execute lint,
  unit tests, type checking, smoke tests, Stryker mutation tests, the Playwright
  accessibility matrix, and the production build
- Playwright comes from `package-lock.json`; CI installs the matching Chromium,
  Firefox, and WebKit engines and uploads the HTML/report artifacts
- the workflow never runs the production-writing E2E suite

The accessibility projects are defined in
`consorcio-web/tests/accessibility/playwright.config.ts`. Cloudflare preview
and production deployments still use the dashboard environment variables
documented above; the GitHub workflow does not deploy the frontend or store
`VITE_*` values as secrets.

After the first green pull-request run, configure branch protection in GitHub to
require the frontend and backend quality checks appropriate for `main`. That
remote repository setting is not created by these workflow files.

## PWA Considerations

The frontend uses `vite-plugin-pwa` which generates a service worker. This works with Cloudflare Pages out of the box. The service worker will be included in the `dist/` output.
