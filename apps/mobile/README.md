# Mobile companion

The status dashboard is an installable progressive web app (PWA), so one codebase covers phones, tablets and desktops:

- **Android / Chrome / Edge:** open the dashboard and use *Install app* (or *Add to Home screen*). PNG 192/512 icons and a separate maskable icon are provided.
- **iOS / iPadOS (Safari):** *Share → Add to Home Screen*. The opaque 180 px `apple-touch-icon.png` is used because iOS ignores SVG touch icons.
- **Desktop (Chrome, Edge, Safari 17+):** use the install icon in the address bar.

Run the localhost-only API and open `http://127.0.0.1:8787/dashboard` in a browser on the same device as Jarvis.

The app is read-only. Its service worker caches only the static shell listed in `apps/dashboard/service-worker.js` (stale-while-revalidate, so shell updates arrive on the next launch). `/health`, `/status`, `/features` and every other API response bypass the service worker and are never cached; the page clears its displayed values whenever the API stops answering instead of showing stale data. It cannot connect to another device or a public server because the API deliberately remains localhost-only. No broker credentials belong in the client.

Native iOS/Android binaries are intentionally not built: the API is localhost-only and read-only, so a native shell would add an app-store surface and credential-handling risk without adding capability. Revisit only after paper validation and an owner decision.

To regenerate the icons from `apps/dashboard/icon.svg` geometry: `pip install pillow && python scripts/generate_dashboard_icons.py`.
