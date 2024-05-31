# Cambfurs Catbot
Telegram bot for the Cambridge Furs telegram.

## Building
```
pip install -e .
```

## Configuring
Catbot requires a single configuration file `config.toml` containing the following fields:
```toml
bot_token = "<YOUR TELEGRAM BOT TOKEN>"
main_chat_id = -1234567890
admin_chat_id = -1234567890
waiting_room_chat_id = -1234567890
```

## Contributing

We use two tools to help validate our python, `ruff` and `mypy`.

```
ruff check main.py
mypy main.py
```
