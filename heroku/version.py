"""Represents current userbot version"""

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

# Compatibility tuple for `# scope: heroku_min`. This is the Heroku 2.2.0
# baseline Kanjo was rebranded from. Do not lower it: modules that require
# Heroku 1.x/2.x would refuse to load. The user-facing string is
# "Kanjo 1.0.0" from heroku.brand.display_version().
__version__ = (2, 2, 0)

import os

from .brand import apply_env_aliases, env_flag

apply_env_aliases()
NO_GIT = env_flag("NO_GIT")
if not NO_GIT:
    import git
else:
    git = None

if NO_GIT:
    branch = "master"
else:
    try:
        assert git is not None
        with git.Repo(
            path=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ) as repo:
            branch = repo.active_branch.name
    except Exception:
        branch = "master"
