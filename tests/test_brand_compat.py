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

"""Kanjo name, Heroku package shim, hikka import alias, and env aliases."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import unittest

from heroku.brand import (
    ATTRIBUTION,
    KANJO_VERSION,
    REPO_URL,
    UPSTREAM_LABEL,
    apply_env_aliases,
    display_version,
    env_get,
)
from heroku.network.transport import cli_transport_default
from heroku.version import __version__


class BrandTest(unittest.TestCase):
    def test_display_version_and_compat_tuple(self):
        self.assertEqual(display_version(), "Kanjo 1.0.0")
        self.assertEqual(KANJO_VERSION, (1, 0, 0))
        self.assertEqual(__version__, (2, 2, 0))
        self.assertEqual(UPSTREAM_LABEL, "Heroku 2.2.0")
        self.assertIn("github.com/coddrago/Heroku", ATTRIBUTION)
        self.assertIn("github.com/hikariatama/Hikka", ATTRIBUTION)
        self.assertIn("AGPL-3.0", ATTRIBUTION)

    def test_repo_url_is_one_constant(self):
        self.assertEqual(REPO_URL, "https://github.com/bertffff/Heroku")
        import heroku.main  # noqa: F401  -- finish the loader import cycle
        from heroku.modules.updater import UpdaterMod

        self.assertEqual(UpdaterMod.FORK_ORIGIN, REPO_URL)


class PackageShimTest(unittest.TestCase):
    def test_heroku_and_kanjo_and_hikka_import(self):
        import heroku.main  # noqa: F401  -- finish the loader import cycle
        from heroku import loader as heroku_loader

        self.assertTrue(hasattr(heroku_loader, "Modules"))

        import builtins

        import heroku.loader  # installs the hikka -> heroku import hook

        self.assertTrue(hasattr(heroku.loader, "Modules"))
        import kanjo
        from kanjo.loader import Modules

        self.assertIs(Modules, heroku_loader.Modules)
        self.assertEqual(kanjo.NAME, "Kanjo")
        self.assertEqual(kanjo.REPO_URL, REPO_URL)

        # Modules write `import hikka`, which goes through builtins.__import__.
        hikka_version = builtins.__import__("hikka.version", fromlist=["__version__"])
        heroku_version = importlib.import_module("heroku.version")
        self.assertIs(hikka_version, heroku_version)
        self.assertEqual(hikka_version.__version__, (2, 2, 0))
        namespace: dict = {}
        exec("import hikka.loader as hikka_loader", namespace)  # noqa: S102
        self.assertIs(namespace["hikka_loader"].Modules, heroku_loader.Modules)


class EnvAliasTest(unittest.TestCase):
    def test_kanjo_transport_when_heroku_is_unset(self):
        self.assertEqual(cli_transport_default({"KANJO_TRANSPORT": "ws"}), "ws")
        self.assertEqual(env_get("TRANSPORT", environ={"KANJO_TRANSPORT": "tcp"}), "tcp")

    def test_heroku_transport_wins(self):
        environ = {"HEROKU_TRANSPORT": "tcp", "KANJO_TRANSPORT": "ws"}
        self.assertEqual(cli_transport_default(environ), "tcp")
        self.assertEqual(env_get("NO_GIT", environ={"HEROKU_NO_GIT": "0", "KANJO_NO_GIT": "1"}), "0")

    def test_blank_heroku_falls_through_to_kanjo(self):
        environ = {"HEROKU_OPTIONAL_MODULES": "  ", "KANJO_OPTIONAL_MODULES": "eval"}
        self.assertEqual(env_get("OPTIONAL_MODULES", environ=environ), "eval")

    def test_apply_copies_alias_without_clobbering(self):
        copied = {"KANJO_NO_GIT": "1", "KANJO_BRANCH": "dev"}
        apply_env_aliases(copied)
        self.assertEqual(copied["HEROKU_NO_GIT"], "1")
        self.assertEqual(copied["HEROKU_BRANCH"], "dev")

        kept = {"HEROKU_TRANSPORT": "tcp", "KANJO_TRANSPORT": "ws"}
        apply_env_aliases(kept)
        self.assertEqual(kept["HEROKU_TRANSPORT"], "tcp")

    def test_entrypoint_help_mentions_kanjo(self):
        env = os.environ.copy()
        env["HEROKU_NO_GIT"] = "1"
        for module in ("kanjo", "heroku"):
            proc = subprocess.run(
                [sys.executable, "-m", module, "--help"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=90,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Kanjo", proc.stdout)
            self.assertIn("python -m heroku", proc.stdout)


if __name__ == "__main__":
    unittest.main()
