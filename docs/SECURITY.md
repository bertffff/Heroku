# Security notes

[English](SECURITY.md) · [Русский](SECURITY.ru.md)

Kanjo runs as the Unix user that started it and talks to Telegram as that Telegram account. A module is Python executed in that process. Treat a module from someone you do not know the way you would treat a shell script from them.

## What stays off until you ask

`eval` and `translate` are not loaded at startup. Turn them on with `HEROKU_OPTIONAL_MODULES` or `KANJO_OPTIONAL_MODULES` (the Kanjo name applies when the Heroku one is unset or blank), or with `optional_modules` in `config.json`. The terminal module is installed. It is meant for the owner: it prompts for sudo in the chat instead of assuming a passwordless root shell, and command output is streamed back to you.

## What the process protects on disk

`config.json` and `config-<id>.json` are written mode `0600`. `sessions/` is mode `0700`. Logs and error reports redact tokens the process knows about. That is not a promise that a hostile module cannot read the session: it runs in the same interpreter.

An unencrypted session proxy socket is refused unless `HEROKU_ALLOW_INSECURE_PROXY=1` or `KANJO_ALLOW_INSECURE_PROXY=1`. Leave that off unless you are pointing at a proxy you run yourself.

Do not start Kanjo as root. The entrypoint stops and asks you to make another user. `--root` is the explicit override.

## Modules and links

Downloads of modules and translations are HTTPS. Basic auth is sent only to the repository you configured, not to every host. The default module catalog is the Heroku-compatible index. It is a file source. It is not a support chat, and Kanjo does not join the old Heroku channels for you.

`.dlmod` and `.loadmod` will run whatever file you point them at. Read it first. If a module asks to join a channel, the prompt says why and waits.

## Inline bot

Buttons and forms are owner-gated unless a module widens that. A new bot is created only when you do not already have one; its username looks like `kanjo_xxxxxx_bot`. An existing bot token in `heroku.inline` is reused and not renamed.

There is no HTTP control panel in this tree. Account login for an extra account is an inline form, and it is owner-only.

## Telegram

Userbots are not a Telegram product. Automation on a user account can violate their terms and can get the account limited. Do not use Kanjo to spam, to evade a ban, or to touch accounts that are not yours.

## Upstream

Kanjo is based on Heroku Userbot (github.com/coddrago/Heroku), itself a fork of Hikka (github.com/hikariatama/Hikka); licensed AGPL-3.0.

Donation links and the old support chats are not shown in the interface. The place to read the code is https://github.com/bertffff/Heroku.
