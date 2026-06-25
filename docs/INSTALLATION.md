# Installation

How to get `aa_auto_sdr` installed and verified across platforms, including install methods, optional extras, and the dependency surface. This guide stops at the point where the tool runs — **credentials are covered separately** in [`CONFIGURATION.md`](CONFIGURATION.md), and the guided zero-to-first-SDR walkthrough is in [`QUICKSTART.md`](QUICKSTART.md).

## System requirements

| Requirement | Detail |
|-------------|--------|
| **Python** | 3.14 or higher |
| **Package manager** | [`uv`](https://docs.astral.sh/uv/) (recommended); `pip` also works |
| **Operating system** | macOS, Linux, or Windows |
| **Network** | Connectivity to Adobe Analytics 2.0 APIs |
| **Access** | An Adobe Developer Console project with Adobe Analytics API access (OAuth Server-to-Server), and that integration added to an Adobe Analytics Product Profile |

The tool is **read-only against Adobe Analytics** and uses the **2.0 API only**. It never creates, updates, or deletes anything in your Adobe environment.

## Install uv

`uv` is a fast Python package manager. It resolves and installs dependencies, creates the virtual environment, and runs the console scripts.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip on any platform
pip install uv
```

Verify:

```bash
uv --version
```

## Install the tool

### Option 1 — Clone + uv sync (recommended)

```bash
git clone https://github.com/brian-a-au/aa_auto_sdr
cd aa_auto_sdr
uv sync --all-extras
```

`uv sync` creates `.venv/`, installs all dependencies from `pyproject.toml`, generates a reproducible `uv.lock`, and installs the `aa_auto_sdr` / `aa-auto-sdr` console scripts. `--all-extras` also pulls in the optional features (`env`, `completion`, `notion`); drop it for a core-only install.

Verify:

```bash
# With uv (no venv activation needed)
uv run aa_auto_sdr --version

# Or activate the venv, then run directly
source .venv/bin/activate     # macOS/Linux
# .venv\Scripts\activate      # Windows PowerShell
aa_auto_sdr --version
```

> All subsequent commands assume you are in the `aa_auto_sdr` directory.

### Option 2 — Download ZIP

If you don't have git:

1. Download the repository as a ZIP from GitHub and extract it.
2. Open a terminal in the extracted folder.
3. `uv sync --all-extras`

### Option 3 — pip + virtual environment

```bash
git clone https://github.com/brian-a-au/aa_auto_sdr
cd aa_auto_sdr

python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows PowerShell

pip install .                  # or: pip install -e . for an editable install
aa_auto_sdr --version
```

### Windows notes

On Windows the smoothest path is to install with `uv` and run via the activated venv:

```powershell
uv sync --all-extras
.venv\Scripts\activate
aa_auto_sdr --version
```

If you hit problems, the usual causes are:

| Issue | Fix |
|-------|-----|
| Wrong Python | Install Python 3.14+ from [python.org](https://www.python.org/downloads/), not the Microsoft Store. Check "Add Python to PATH". |
| `python` resolves to the Store stub | `python -c "import sys; print(sys.executable)"` should point under `...\Programs\Python\...`, not `...\Microsoft\WindowsApps\...`. |
| Execution policy blocks activation | Run PowerShell as Administrator, then `Set-ExecutionPolicy RemoteSigned`. |
| Module not found after install | Confirm the venv is active: `.venv\Scripts\activate`. |

## Optional extras

Three optional extras enable extra features. They are not required for core SDR generation.

| Extra | Package | Enables |
|-------|---------|---------|
| `env` | `python-dotenv` | Reading credentials from a `.env` file in the working directory |
| `completion` | `argcomplete` | Dynamic shell tab-completion (a static script is always available via `--completion`) |
| `notion` | `notion-client` | Publishing SDRs to Notion (`--format notion`, `--push-to-notion`, the SDR Registry) |

Install everything at once, or one extra at a time:

```bash
# Everything (during a clone install)
uv sync --all-extras

# A single extra into an existing environment
# macOS/Linux (single quotes)
uv pip install 'aa-auto-sdr[notion]'
# Windows PowerShell (double quotes)
uv pip install "aa-auto-sdr[notion]"
```

## Dependencies

Core dependencies, installed automatically:

| Package | Purpose |
|---------|---------|
| `aanalytics2` | Adobe Analytics 2.0 API wrapper (isolated behind `api/client.py`) |
| `pandas` | Tabular data handling for output writers |
| `openpyxl` | Reading/filling Excel templates |
| `xlsxwriter` | Writing Excel workbooks from scratch |
| `requests` | Transient-failure classification in the resilience layer |

Optional dependencies map to the extras above (`python-dotenv`, `argcomplete`, `notion-client`).

## Verify the installation

```bash
# Tool runs and reports its version (fast-path, no heavy imports)
aa_auto_sdr --version

# Credential shape is valid locally (does not contact Adobe)
aa_auto_sdr --validate-config

# Which credential source resolved
aa_auto_sdr --show-config

# End-to-end: confirms auth, scopes, and report-suite visibility
aa_auto_sdr --list-reportsuites
```

If `--validate-config` passes but `--list-reportsuites` is empty or returns a 403, the cause is almost always credential or Product Profile setup — see [`CONFIGURATION.md`](CONFIGURATION.md) and run `aa_auto_sdr --explain-exit-code <CODE>`.

## Update or reinstall

```bash
# Update all dependencies to the latest allowed versions
uv sync --upgrade

# Reinstall everything from the lock file
uv sync --reinstall
```

## Security

`config.json` and `.env` are already in `.gitignore` — never commit credentials. Use a dedicated service-account integration for automated runs and rotate the client secret periodically. Locally written artifacts (snapshots, output files, `~/.aa/orgs/` profiles) are unrelated to Adobe and safe to keep on disk.

## Project layout

The on-disk module map is in the README's [Project Structure](../README.md#project-structure) section. It is descriptive — you don't need to know it to install or run the tool.

## Next steps

- [Configuration](CONFIGURATION.md) — set up credentials, OAuth scopes, and profiles
- [Quickstart](QUICKSTART.md) — guided walkthrough from clone to first SDR
- [Quick Reference](QUICK_REFERENCE.md) — single-page command cheat sheet
- [CLI Reference](CLI_REFERENCE.md) — every flag with examples
