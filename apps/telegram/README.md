# Telegram status bot

Optional read-only integration, started with `python -m apps.telegram.bot` or `docker compose --profile telegram up --build`. Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the process environment.

Only `/health` and `/status` are supported. Updates are accepted only from the configured chat ID. Replies contain a fixed paper-only health message; account balances, positions, commands, and credentials are not sent to Telegram. No order-changing operation is exposed.

The bot polls Telegram over HTTPS and checks the local API at `127.0.0.1:8787`. Keep its token in a local secret store or environment, never in git or chat.