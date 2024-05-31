# Cambfurs Catbot
Telegram bot for the Cambridge Furs group.

## Building
```
pip install -e .
```

### Permissions
CatBot expects to be in three groups:
1) a **main group** where CatBot has these **admin** permissions:
    * Add Users
    * Pin Messages
2) an **admin group** where CatBot has these **user** permissions:
    * Send Messages
3) a **waiting room group** where CatBot has these **user** permissions:
    * Send Messages

Catbot expects [Privacy Mode](https://core.telegram.org/bots/features#privacy-mode) to be turned off.
That way it can read messages you give it in the admin group and waiting room group without being admin.

### `config.toml`
Catbot requires a single configuration file `config.toml` containing the following fields:
```toml
bot_token = "<YOUR TELEGRAM BOT TOKEN>"
main_group_id = -1234567890
admin_group_id = -1234567890
waiting_room_group_id = -1234567890
```
For security reasons, this file must never be checked in.

## Contributing

### Automated checkers
We use two tools to help validate our python, `ruff` and `mypy`.
```
ruff check main.py
mypy main.py
```

### Design principles
1) **Beginner Friendly**
    CatBot aims to be easy to understand and to modify by beginners.
    It is for this reason that it is implemented in Python.
2) **No Caching**
    CatBot is a low-volume telegram bot, it is therefore not necessary to cache information.
    This prevents stale data bugs.
3) **Fixed Groups**
    CatBot does not require the flexibility of being added to arbitrary groups.
    It knows about the three groups it will be in, and has different behaviour for each.
4) **[Least Privilege](https://en.wikipedia.org/wiki/Principle_of_least_privilege)**
    This limits the damage that any bug can do.

### Roadmap
- [x] `/say` command for use in the admin group to have catbot put a message in the main group
- [x] Allow new users to join the main chat using the `/approve @username` command in the waiting room.
- [x] Welcome message in the main chat
- [ ] Welcome message in the waiting room
- [ ] Meet announcements generated from ical
- [ ] Ability to edit welcome messages.
- [ ] The ability to edit messages sent by `/say`
