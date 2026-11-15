# Dashboard (status-only)

Static read-only status page, served by `python main.py --serve` at `/dashboard` and installable as a PWA on Android, iOS and desktop (see `apps/mobile/README.md`).

- `index.html`, `dashboard.css`, `dashboard.js` — the status page; values are cleared whenever the API stops answering. There is no inline script or style, so `/dashboard` is served with a strict same-origin Content-Security-Policy. Keep it that way: new code goes in the `.js` and `.css` files, and any new asset must be added to the service worker shell.
- `manifest.webmanifest`, `service-worker.js` — install metadata and shell-only offline cache.
- `icon.svg`, `icons/` — vector icon plus generated PNGs (`scripts/generate_dashboard_icons.py`).

No order placement UI. No remote API keys. Future Next.js port from `jarvistrader` can replace this skeleton after paper validation.
