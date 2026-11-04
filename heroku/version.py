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

__version__ = (2, 2, 0)

import os

NO_GIT = os.environ.get("HEROKU_NO_GIT") == "1"
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
