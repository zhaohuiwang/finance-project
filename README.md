## Steps to setup project Direcotry including monorepo and hierarchy of projects
###  A: The standard uv workspace setup
* There is only one shared virtual environment. It lives at the workspace root level → my-monorepo/.venv/
* All workspace members (your my-dev-project, the github-lib, and any future ones) install their dependencies into this single .venv.
* The packages from other workspace members are installed editable (-e) so code changes are immediately visible.
* One example workspace member = pure GitHub clone (you can git pull / submodule update --remote anytime)
* One example workspace member = your own dev project
* Your dev project always installs the local workspace version of the GitHub package (never the remote PyPI or git+https://github.com...)
* "Workspaces are not suited for cases in which members have conflicting requirements, or desire a separate virtual environment for each member." — official uv documentation

Final directory structure
```Bash
my-monorepo/     # ← git init here — single repo for the whole org/team
├── .git/                   # one shared git history
├── .gitignore              # ignore all .venv/ folders
├── uv.lock
├── .gitmodules             # configuration file
├── README.md
├── github-lib
│   ├── lumibot             # ← pure GitHub source (submodule)
│   └── schwabdev
├── documents
├── personal_project_1      # e.g. alpaca
│   ├── pyproject.toml
    ├── scripts
│   └── ...
└── personal_project_2      # e.g. schwab-trader 
    ├── pyproject.toml
    ├── scripts
    └── ... 
```

Create the monorepo root
```Bash
mkdir my-monorepo && cd my-monorepo
git init
```

Create pyproject.toml (this is the workspace root), do not use `uv init`:
```Bash
[project]
name = "my-monorepo"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []   # optional

[tool.uv]
package = false          # Makes this a pure workspace root (not installable)

```

Add the pure GitHub workspace as a submodule (this is the key to “purely from github”)
```Bash
git submodule add https://github.com/tylerebowers/Schwabdev.git github-lib/schwabdev
git submodule update --init
```
This step creates a dir github-lib and clone the specified git repo into it, and also creates a .gitmodules file, with the following content
```Bash
[submodule "github-lib"]
	path = github-lib/schwabdev
	url = https://github.com/tylerebowers/Schwabdev.git
```
Now github-lib/ contains the exact code from GitHub, with its own .git folder.
You can update it anytime with:
```Bash
git submodule update --remote github-lib
# or
cd github-lib && git pull
```

Create your development project
```Bash
uv init my-dev-project
```
project `my-dev-project` is initialized inside `my-monorepo` dir. and it is added as a member of workspace `my-monorepo` the following table is added to the `my-mono-project/pyproject.toml` file
```Bash
[tool.uv.workspace]
members = [
    "my-dev-project",
]
```  
```Bash
cd my-dev-project
uv add pandas
```
this updated the `my-dev-project/pyproject.toml` > `dependeccies = []` resulting the whole conent as the following
```Bash 
[project]
name = "my-dev-project"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "pandas>=3.0.1",
]
```
no changes to the root `pyproject.toml`, but `uv.lock` and `.venv` was materilized into the root `my-monorepo` dir.

Now if `my-dev-project/` if you run `uv add schwabdev`, uv will add schwabdev from the PyPi just as most of other libraries. But if you update the root `pyproject.toml` with the following new table (or add this new member `"github-lib/schwabdev"`)
```Bash
[tool.uv.workspace]
members = [
    "my-dev-project", "github-lib/schwabdev"
]
```
and in `my-dev-project/` run the same `uv add schwabdev` command, you will see ` schwabdev==3.0.3 (from file:///home/zhaohuiwang/dev/my-monorepo/github-lib/schwabdev)` and this can be confirmed by `uv pip list`, indicating that `schwabdev` is installed from the local github submodule dir. the  `my-dev-project/pyproject.toml` also has a new `[tool.uv.sources]` as the following
```Bash
[project]
name = "my-dev-project"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "pandas>=3.0.1",
    "schwabdev",
]

[tool.uv.sources]
schwabdev = { workspace = true }
```

Sync everything
```Bash
uv sync          # from root → syncs both workspaces
# or
uv sync --package my-dev-project
```
Daily workflow
```Bash
# Update the GitHub package (pull latest from remote)
git submodule update --remote github-lib
git add github-lib
git commit -m "chore: update github-lib"
uv sync

# Work on your dev project
cd my-dev-project
uv run python -m my_dev_project
# or uv run pytest, uv run my-cli, etc.

# Develop the GitHub lib locally (optional): you can edit files inside github-lib/ directly — changes are live because it’s editable.
```


###  B: When you really want separate venvs (most clean & common choice).
just don't use a workspace root at all. (no root `pyproject.toml`; inside project `pyproject.toml` file, `[tool.uv.sources]` table use `path` instead) 
```Bash
my-organization/
├── project-a/                # ← uv init here
│   ├── pyproject.toml
│   ├── .venv/               # ← its own
│   └── uv.lock
├── project-b/                # ← separate uv init
│   ├── pyproject.toml
│   ├── .venv/
│   └── uv.lock
├── shared-lib-from-github/   # ← still a git submodule or clone
│   └── ...
```
* Each project runs its own uv sync, uv add, uv run → gets its own isolated .venv
* To depend on shared-lib-from-github, use path dependency in each project that needs it

For example, in my `/finance-project/` git repo, I have `schwab-trader` and some other projects, I want them to have seperate `.venv`, and each might use a library from a local cloned dir `github-lib`. I have removed all the `.git`, `pyproject.toml`, `uv.lock` and `.venv` files or dirs.
 
```Bash
cd finance-project
git init
git submodule add git@github.com:tylerebowers/Schwabdev.git github-lib/schwabdev
git submodule add git@github.com:Lumiwealth/lumibot.git github-lib/lumibot
git submodule update --init
cd github-lib/schwabdev
git branch
git switch main  # when necessary
cd schwab-trader
uv init
vim pyproject.toml
```
add the following
```Bash
[tool.uv.sources]
schwabdev = { path = "../github-lib/schwabdev", editable = true }
```

```Bash
:~/dev/finance-project/schwab-trader$ uv add schwabdev
Using CPython 3.13.4
Creating virtual environment at: .venv
Resolved 20 packages in 267ms
      Built schwabdev @ file:///home/zhaohuiwang/dev/finance-project/github-lib/schwabdev
Prepared 1 package in 610ms
Installed 19 packages in 19ms
 + schwabdev==3.0.3 (from file:///home/zhaohuiwang/dev/finance-project/github-lib/schwabdev)
+ requests==2.32.5
# and some others 
```

setting up lumi-bot project
```Bash
cd lumi-bot
uv init
vim pyproject.toml
```
add this following to `pyproject.toml`
```Bash
[tool.uv.sources]
lumibot = { path = "../github-lib/lumibot", editable = true }
```

```Bash
uv add lumibot
```

```Bash
Using CPython 3.13.4
Creating virtual environment at: .venv
Resolved 146 packages in 1.52s
      Built lumibot @ file:///home/zhaohuiwang/dev/finance-project/github-lib/lumibot
      Built ibapi==9.81.1.post1
      Built free-proxy==1.1.3
Prepared 44 packages in 3.49s
Installed 142 packages in 139ms
 + aiodns==4.0.0
+ others
 + lumibot==4.4.54 (from file:///home/zhaohuiwang/dev/finance-project/github-lib/lumibot)
 + others
 ```


References:
1. [developer.schwab Accounts and Trading Production](https://developer.schwab.com/products/trader-api--individual/details/specifications/Retail%20Trader%20API%20Production)
2. [developer.schwab Market Data Production](https://developer.schwab.com/products/trader-api--individual/details/specifications/Market%20Data%20Production)
3. [Goldman Sachs](https://github.com/goldmansachs)
4. [freqtrade](https://github.com/freqtrade/freqtrade)
5. [Microsoft Qlib](https://github.com/microsoft/qlib)
6. [schwab-trader github](https://github.com/ibouazizi/schwab-trader/tree/main)
7. [schwab-trader](https://pypi.org/project/schwab-trader/#description)
8. [lumibot git](https://github.com/Lumiwealth/lumibot#)
9. [Lumibot: Backtesting and Algorithmic Trading Library](https://lumibot.lumiwealth.com/)
