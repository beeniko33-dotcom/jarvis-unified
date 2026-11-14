# Local containers

Run `docker compose up --build` from the repository root. The container uses its explicit `--container-bind` mode and Compose publishes port 8787 only on the host loopback address. Do not change the `127.0.0.1` port binding. The API and PWA are available at `http://127.0.0.1:8787`.

The optional Telegram status bot is enabled with `docker compose --profile telegram up --build` and the `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` environment variables. It sends fixed health text only and has no trading commands.

This is a local development setup, not a public deployment. It has no persistent broker state, authentication, TLS, or remote-access configuration. Do not expose the port to a network or run the container with an unbound/public port mapping.