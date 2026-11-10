[English](README.md) · [Русский](README.ru.md)

<p align="center">
  <img src="assets/banner.png" alt="Kanjo" width="640">
</p>

# Kanjo

Kanjo is a Telegram userbot. It runs on your account, loads modules, and keeps a small inline bot for buttons and forms.

Kanjo is based on Heroku Userbot (github.com/coddrago/Heroku), itself a fork of Hikka (github.com/hikariatama/Hikka); licensed AGPL-3.0.

This repository is [bertffff/Heroku](https://github.com/bertffff/Heroku). The GitHub name is still Heroku. The program you see is Kanjo 1.0.0, built on the Heroku 2.2.0 module API. The Python package stays `heroku`, so existing installs and modules do not need a migration.

## What you get

- Command prefix `.` (changeable), modules, inline forms, lists and galleries.
- Obfuscated WebSocket transport when raw MTProto TCP is blocked. See [docs/DEPLOY.md](docs/DEPLOY.md).
- A terminal that asks for sudo in chat and does not keep a root shell lying around. Details in [docs/SECURITY.md](docs/SECURITY.md).
- `eval` and `translate` stay unloaded until you opt in.
- Inline bot extras (disabled buttons, ephemeral replies, drafts, link previews) described in [docs/INLINE_API.md](docs/INLINE_API.md).
- Hikka, FTG, GeekTG and Heroku modules. `from .. import loader, utils`, `import heroku`, `import hikka`, `@loader.tds` and `self.inline` keep working. See [docs/MODULES.md](docs/MODULES.md).

## Install

Python 3.10 or newer. API id and hash come from [my.telegram.org](https://my.telegram.org). Do not commit them.

### Docker

```bash
git clone https://github.com/bertffff/Heroku Kanjo
cd Kanjo
docker compose build
docker compose run --rm kanjo
docker compose up -d
```

The service is `kanjo`, the image is `kanjo:local`. Session and config stay in the `heroku-data` volume, so a volume created before the rename is reused. `python -m heroku` inside the image still starts the same program; the image command is `python -m kanjo`.

`docker.sh` clones this repository and runs the same compose file.

### VPS and systemd

New installs: [docs/kanjo.service](docs/kanjo.service), user `kanjo`, data in `/var/lib/kanjo`.

If you already run `heroku.service` from `/opt/heroku`, leave that unit in place. It still starts `python -m heroku`. The file [docs/heroku.service](docs/heroku.service) is that legacy unit.

Full steps: [docs/DEPLOY.md](docs/DEPLOY.md).

### Bare metal

```bash
git clone https://github.com/bertffff/Heroku Kanjo
cd Kanjo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m kanjo
```

`python3 -m heroku` is the same process. The installer accepts both:

```bash
curl -fsSL https://raw.githubusercontent.com/bertffff/Heroku/master/install.sh | bash
```

A second run starts the checkout it already finds, including a directory named `Heroku`. Root: `bash -s -- --root`. `HEROKU_FORCE_INSTALL=1` or `KANJO_FORCE_INSTALL=1` reinstalls.

## Configuration

Blank values are ignored. For each pair below, a non-empty `HEROKU_*` value wins. `KANJO_*` is used only when the Heroku variable is unset or blank.

| Purpose | Names |
| --- | --- |
| Transport `auto`, `tcp`, or `ws` | `HEROKU_TRANSPORT`, `KANJO_TRANSPORT` |
| Skip git | `HEROKU_NO_GIT=1`, `KANJO_NO_GIT=1` |
| Load `eval` and/or `translate` | `HEROKU_OPTIONAL_MODULES`, `KANJO_OPTIONAL_MODULES` (comma-separated) |
| Installer clone URL, venv, branch, minimal mode, force | `HEROKU_REPO_URL` / `KANJO_REPO_URL`, and the same pattern for `VENV_DIR`, `BRANCH`, `MINIMAL`, `FORCE_INSTALL` |

API credentials: `api_id` and `api_hash`, or `API_ID` and `API_HASH`.

`auto` uses the WebSocket transport when `SAND_EGRESS_TUNNEL_PROXY_ADDR` is set or when `127.0.0.1:8791` accepts TCP. Otherwise it uses direct TCP. `--proxy-host` still overrides the transport.

Database keys such as `heroku.main` and `heroku.inline`, session files `heroku-<id>.session`, `config.json`, `config-<id>.json` and `.modules_cache` are not renamed.

## Updating

Inside the userbot, `.update` fetches this repository only. The URL is `REPO_URL` in `heroku/brand.py` (`https://github.com/bertffff/Heroku`). Change that constant if the repository moves. There is no background autoupdate and no pull from `Heroku-userbot/Heroku`.

## Several accounts

One process and one data directory per account. Docker: another compose project or another volume. systemd: another `--data-root` and another unit. Do not put two accounts in one process.

## Security

Kanjo can run code and shell commands as the user that started it. Read [docs/SECURITY.md](docs/SECURITY.md) before you load modules from the internet. Telegram does not support userbots; a ban is possible.

## Modules

Core module ids (`HerokuInfo`, `Settings`, `Loader`, …) are unchanged, so `.help HerokuInfo` still finds them. A short writing guide is [docs/MODULES.md](docs/MODULES.md). The default third-party module catalog is upstream's (`https://raw.githubusercontent.com/coddrago/modules/main`). It is a module source, not a Kanjo support channel, and it can be changed in `.config` for Loader (`MODULES_REPO`). Extra catalogs go in `ADDITIONAL_REPOS`.

## Credits and license

Kanjo is based on Heroku Userbot (github.com/coddrago/Heroku), itself a fork of Hikka (github.com/hikariatama/Hikka); licensed AGPL-3.0.

Copyright lines of Dan Gazizullin (Hikka) and Codrago (Heroku) stay in the source. Kanjo contributors (bertffff, 2026) are added beside them. See [NOTICE](NOTICE) and [LICENSE](LICENSE).

Colors, the seal and 🎴 are described in [docs/BRAND.md](docs/BRAND.md).
