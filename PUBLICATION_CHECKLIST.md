# Publication Checklist

Before pushing this repository to GitHub, verify the following:

- `.env` is not present. Only `.env.example` should be committed.
- `bot.log` and `*.log` files are not present.
- `.venv/`, `__pycache__/`, and `*.pyc` files are not present.
- `data/qdrant_storage/` is not present. It is generated locally by Qdrant.
- `data/docs/` contains only sample Markdown documents, not real internal policies.
- Telegram bot token, user IDs, private URLs, customer names, credentials, and API keys do not appear in the repository.

Suggested final scan:

```bash
find . \( -name '.env' -o -name '.venv' -o -name '__pycache__' -o -name '*.pyc' -o -name '*.log' -o -name 'qdrant_storage' \) -print
rg -n "TELEGRAM_BOT_TOKEN=[0-9]|sk-[A-Za-z0-9]|Bearer [A-Za-z0-9]|PRIVATE KEY|password|secret" .
```

If either command prints real sensitive values, remove them before committing.
