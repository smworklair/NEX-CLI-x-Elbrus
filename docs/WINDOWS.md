# Windows

> Branch from stage 2 · [← CLI](CLI.md) · [Roadmap](README.md)

The tool works fully on Windows, including the fullscreen workspace.
This page lists only the differences from [`CLI.md`](CLI.md).

## Python

Python 3.10+ is required. Verify with:

```powershell
py --version
```

If unavailable, install from [python.org](https://www.python.org/downloads/) (check **Add python.exe to PATH**) or via `winget`:

```powershell
winget install Python.Python.3.12
```

On Windows the executable is usually `python` or `py`; `python3` typically does not exist. Substitute `python` wherever the rest of the docs say `python3`.

## Installation

```powershell
git clone <repository-url>
cd NEX-CLI-x-Elbrus
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[tui]"
```

If PowerShell blocks script activation (`running scripts is disabled`), allow it for the current session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

In `cmd.exe`, activation uses `.venv\Scripts\activate.bat`.

## Running

```powershell
python -m vliw run slotclash
python -m vliw                 # mode selector
python -m vliw --mode code     # straight into CODE
python -m vliw --plain         # line-by-line mode
```

After `pip install -e .`, the short `vliw` command is available.

If `textual` is not installed, `python -m vliw` opens the setup assistant screen: it explains why, shows the commands, and installs `textual`/`rich` once you confirm.

## Two Quirks

**Unicode / UTF-8.** The tool automatically switches the Windows console to UTF-8 and VT mode. If you see boxes or garbled text, update the repository.

**Command history.** Standard Python on Windows does not bundle `readline`. This only affects plain mode (`--plain`, pipes, scripts), where the up arrow does not cycle history. The fullscreen TUI handles its own input, so it is unaffected.

## Agent

Without an API key, the agent answers offline from computed numbers — this is expected, not a bug.
Paste a key in chat or configure via command:

```text
/ai deepseek key=sk-...
/ai gigachat key=<client_id>:<client_secret>
/ai yandex folder=... key=...
/ai local-server url=http://localhost:11434/v1 model=qwen2.5:3b
```

Keys live in session memory only. 17 providers are supported; full list in [`AGENT_PROMPTS.md`](AGENT_PROMPTS.md) and [`.env.example`](../.env.example).
For non-interactive scripts, use environment variables: `NEX_PROVIDER`, `NEX_API_KEY`, `NEX_MODEL`, `NEX_BASE_URL`.

## Troubleshooting

| symptom | fix |
|---|---|
| `No module named vliw` | run from the project root or `pip install -e .` |
| `.venv` activation blocked | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| boxes instead of text | update the repository |
| no history in `--plain` | Windows limitation, not a bug |
| `verify` cannot find assembler | set `E2K_AS` or add `lcc` to `PATH` |

General issues: [`CLI.md`](CLI.md#common-issues).
