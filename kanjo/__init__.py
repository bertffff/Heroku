# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Kanjo userbot.

The implementation package is still ``heroku``. This package is the
user-facing name: ``import kanjo``, ``from kanjo.loader import Modules`` and
``python -m kanjo`` all work. Database keys, session files and
``python -m heroku`` are unchanged.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

import heroku
from heroku.brand import (  # noqa: F401
    ASSET_BANNER,
    ASSET_FAVICON,
    ASSET_LOGO,
    ATTRIBUTION,
    EMOJI,
    KANJO_VERSION,
    NAME,
    REPO_URL,
    UPSTREAM_LABEL,
    display_version,
)

__all__ = [
    "ASSET_BANNER",
    "ASSET_FAVICON",
    "ASSET_LOGO",
    "ATTRIBUTION",
    "EMOJI",
    "KANJO_VERSION",
    "NAME",
    "REPO_URL",
    "UPSTREAM_LABEL",
    "display_version",
]


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, heroku_name: str):
        self.heroku_name = heroku_name

    def create_module(self, spec):
        module = importlib.import_module(self.heroku_name)
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        return None


class _KanjoFinder(importlib.abc.MetaPathFinder):
    """Resolve ``kanjo.*`` to the matching ``heroku.*`` module.

    ``kanjo`` itself and ``kanjo.__main__`` are real files. Everything else
    is the Heroku implementation, so ``from kanjo import loader`` works
    without a second copy of the code.
    """

    def find_spec(self, fullname, path, target=None):
        if fullname == "kanjo" or not fullname.startswith("kanjo."):
            return None
        if fullname == "kanjo.__main__":
            return None
        heroku_name = "heroku" + fullname[len("kanjo") :]
        try:
            heroku_spec = importlib.util.find_spec(heroku_name)
        except (ImportError, ValueError):
            return None
        if heroku_spec is None or heroku_spec.loader is None:
            return None
        return importlib.machinery.ModuleSpec(
            fullname,
            _AliasLoader(heroku_name),
            is_package=heroku_spec.submodule_search_locations is not None,
            origin=getattr(heroku_spec, "origin", None),
        )


if not any(isinstance(finder, _KanjoFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _KanjoFinder())

# Touch the implementation package so `import kanjo` cannot succeed without it.
_ = heroku
