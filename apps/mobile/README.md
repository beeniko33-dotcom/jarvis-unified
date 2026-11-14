# Mobile companion

The status dashboard is an installable progressive web app. Run the localhost-only API and open `http://127.0.0.1:8787/dashboard` in a mobile browser on the same device as Jarvis, then use the browser's install/add-to-home-screen action.

The app is read-only. It caches only its static shell for offline launch; health and account responses are always fetched from the API and are never cached. It cannot connect to another device or a public server because the API deliberately remains localhost-only. No broker credentials belong in the client.