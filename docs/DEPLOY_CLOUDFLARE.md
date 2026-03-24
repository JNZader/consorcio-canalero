# Cloudflare Pages Deployment

## Connect Repository

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) > Workers & Pages > Create application > Pages
2. Connect your GitHub repository (`consorcio-canalero`)
3. Select the branch to deploy (e.g., `main` for production)

## Build Settings

| Setting | Value |
|---------|-------|
| Framework preset | None |
| Build command | `cd consorcio-web && npm install --legacy-peer-deps && npm run build` |
| Build output directory | `consorcio-web/dist` |
| Root directory | `/` (project root) |

> **Note:** `--legacy-peer-deps` is required because some dependencies have peer dependency conflicts.

## Environment Variables

Set these in **Cloudflare Dashboard > Pages project > Settings > Environment variables**:

| Variable | Value | Notes |
|----------|-------|-------|
| `VITE_API_URL` | `https://your-backend-url.com` | Backend API base URL |
| `NODE_VERSION` | `20` | Required for the build |

Set different `VITE_API_URL` values for Production and Preview environments.

> **Important:** Vite bakes `VITE_*` env vars into the bundle at build time. They are NOT runtime secrets. Changing them requires a rebuild.

## SPA Routing

The file `consorcio-web/public/_redirects` handles client-side routing by redirecting all paths to `index.html` with a 200 status. Cloudflare Pages copies files from `public/` into the build output automatically via Vite.

## Security Headers

The file `consorcio-web/public/_headers` adds security headers to all responses:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(self)`

## Wrangler Config (Optional)

A `consorcio-web/wrangler.toml` is included for local development with `wrangler pages dev`. The dashboard configuration takes precedence for deployed builds.

## Custom Domain

1. Go to Pages project > Custom domains > Set up a custom domain
2. Add your domain (e.g., `app.consorcio.example.com`)
3. Cloudflare will automatically provision an SSL certificate

## Preview Deployments

Every push to a non-production branch generates a preview URL at `<branch>.<project>.pages.dev`. Use different `VITE_API_URL` values for Preview vs Production environments in the dashboard.

## GitHub Actions

No GitHub Actions workflows are currently present in the repository. Cloudflare Pages handles CI/CD via its own build system triggered by git pushes.

## PWA Considerations

The frontend uses `vite-plugin-pwa` which generates a service worker. This works with Cloudflare Pages out of the box. The service worker will be included in the `dist/` output.
