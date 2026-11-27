# -*- coding: utf-8 -*-
"""Topic-based answers for the NNL assistant — pure stdlib.

The setup screen runs in environments where textual, rich, or numpy may not
be installed. Therefore this module only produces text and substitutes paths;
formatting (colors, wrapping, borders) is handled by `vliw.ui.setup_screen`.

An answer is a list of paragraphs. A line indented by four spaces is treated
as a shell command: the screen highlights it separately from explanatory text.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import VERSION_LABEL

МИН_PYTHON = "3.10"


def _py() -> str:
    """Current Python interpreter, quoted for shell copy-paste if needed."""
    return f'"{sys.executable}"' if " " in sys.executable else sys.executable


def _project() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _project_text() -> str:
    p = _project()
    if p is not None:
        return str(p)
    return r"path\to\project\dir" if os.name == "nt" else "path/to/project/dir"


def _activate() -> str:
    if os.name == "nt":
        return r".venv\Scripts\activate"
    return "source .venv/bin/activate"


def _venv_python() -> str:
    if os.name == "nt":
        return r".venv\Scripts\python.exe"
    return ".venv/bin/python"


def _pip_install() -> str:
    """Install the project with the TUI interface — from the project directory."""
    if _project() is not None:
        return f'{_py()} -m pip install -e ".[tui]"'
    return f'{_py()} -m pip install "textual>=8.2" "rich>=13"'


def _tui_only() -> str:
    return f'{_py()} -m pip install "textual>=8.2" "rich>=13"'


ЗАГОЛОВКИ: dict[str, str] = {
    "зачем": "what NEX CLI is for",
    "требования": "system requirements",
    "установка": "how to install",
    "textual": "textual and rich — full-screen interface",
    "система": "Windows / Linux / macOS",
    "проверка": "how to verify installation and run tests",
    "запуск": "how to launch",
    "проблема": "won't start — troubleshooting",
    "venv": "virtual environment",
    "обновление": "how to update",
    "удаление": "how to uninstall",
    "данные": "scenarios and data",
    "агент": "agent and API keys",
    "nnl": "how NNL understands your question",
    "беседа": "greeting",
}


def _зачем() -> list[str]:
    return [
        f"NEX CLI {VERSION_LABEL} is a workspace for instruction scheduling "
        "on the Elbrus e2k VLIW architecture.",
        "",
        "It takes a program dependency graph and shows how instructions map onto "
        "machine channels and ports: where port conflicts occur, how many cycles "
        "are lost to stalls, and what can be sped up by reordering. Three modes inside:",
        "  CODE — .s editor, schedule, analysis, and linter diagnostics in one window;",
        "  LAB — full dependency graph, diagnostics, and built-in scenarios;",
        "  AGENT — LLM Q&A grounded in the current graph and schedule.",
        "",
        "The scheduler, oracle, and one-shot commands run on pure Python. "
        "Full-screen panes are built on Textual — if it is missing or the terminal "
        "is non-interactive, this setup screen opens instead.",
        "",
        "Quick check without installing:",
        f"    {_py()} -m vliw run slotclash",
        f"    {_py()} -m vliw compare",
        f"    {_py()} -m vliw --help",
    ]


def _требования() -> list[str]:
    return [
        f"Minimum — Python {МИН_PYTHON} or newer (3.12 recommended), 64-bit.",
        "",
        "What you need:",
        "  • about 100 MB of disk space including textual and rich;",
        "  • a standard UTF-8 terminal (PowerShell, Windows Terminal, bash, zsh);",
        "  • internet access — only to download packages; not needed at runtime.",
        "",
        "What you do NOT need:",
        "  • a GPU or CUDA;",
        "  • real Elbrus hardware — the e2k machine model is built into the project;",
        "  • numpy, torch, or other heavy packages for the scheduler and this screen.",
        "",
        "Check your Python version:",
        f"    {_py()} --version",
        "",
        "Supported on Windows 10/11, Linux (Ubuntu, Debian, Fedora, Arch), "
        "and macOS.",
    ]


def _установка() -> list[str]:
    проект = _project() is not None
    шаги = [
        "Recommended installation order — step by step, without skipping:",
        "",
        "1. Check Python (3.10+ required):",
        f"    {_py()} --version",
        "",
        "2. Change to the project directory (where pyproject.toml lives):",
        f"    cd {_project_text()}",
        "",
        "3. Create an isolated environment so system Python stays clean:",
        f"    {_py()} -m venv .venv",
        "",
        "4. Activate it:",
        f"    {_activate()}",
        "",
        "5. Upgrade pip and install the project with the TUI interface:",
        "    python -m pip install --upgrade pip",
    ]
    if проект:
        шаги.append('    python -m pip install -e ".[tui]"')
    else:
        шаги.append('    python -m pip install "textual>=8.2" "rich>=13"')
    шаги += [
        "",
        "6. Launch:",
        "    python -m vliw",
        "",
        "If environment activation fails, use the full interpreter path:",
        f"    {_venv_python()} -m pip install --upgrade pip",
        f'    {_venv_python()} -m pip install -e ".[tui]"',
        f"    {_venv_python()} -m vliw",
        "",
        "Interface packages only, without installing the project itself:",
        f"    {_tui_only()}",
    ]
    return шаги


def _textual() -> list[str]:
    return [
        "Textual is the full-screen UI library: panes, tabs, keybindings, and "
        "the CODE / LAB / AGENT switcher. Rich handles colored output and "
        "tables; Textual uses it under the hood.",
        "",
        "Without these two packages NEX CLI does not crash: the scheduler and "
        "CLI commands still work, but this helper screen opens instead of the "
        "full-screen interface.",
        "",
        "Install both packages:",
        f"    {_tui_only()}",
        "",
        "Install the full project along with them (from the project directory):",
        f"    {_pip_install()}",
        "",
        "Verify both modules are importable:",
        f'    {_py()} -c "import textual, rich; '
        'print(textual.__version__, rich.__version__)"',
        "",
        "If you see 'No module named textual', the package was installed into "
        "a different Python. Install and run with the exact same interpreter:",
        f'    {_py()} -m pip install "textual>=8.2" "rich>=13"',
        f"    {_py()} -m vliw",
        "",
        "After installing, restart the command: Textual is loaded at process startup.",
        "",
        "If you don't need full-screen panes, you can skip Textual — "
        "line-by-line plain mode works on pure Python:",
        f"    {_py()} -m vliw --plain",
    ]


def _система() -> list[str]:
    return [
        "Windows (PowerShell or cmd):",
        "  • check Python:  py -3 --version",
        "  • create venv:  py -3 -m venv .venv",
        r"  • activate:  .venv\Scripts\activate",
        '  • install:  python -m pip install -e ".[tui]"',
        "  • launch:  python -m vliw",
        "",
        "If PowerShell blocks activate, relax the execution policy once:",
        "    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned",
        "or skip activation and call the venv interpreter directly:",
        r"    .venv\Scripts\python.exe -m vliw",
        "",
        "If legacy cmd garbles Unicode characters, enable UTF-8:",
        "    chcp 65001",
        "",
        "Linux / macOS:",
        "  • check Python:  python3 --version",
        "  • install venv if missing:  sudo apt install python3-venv",
        "  • create venv:  python3 -m venv .venv",
        "  • activate:  source .venv/bin/activate",
        '  • install:  python -m pip install -e ".[tui]"',
        "  • launch:  python -m vliw",
        "",
        "If python3 is not found, try python. On Windows, watch out for the "
        "Microsoft Store stub in WindowsApps — it's better to install Python "
        "from python.org and call it by full path.",
    ]


def _проверка() -> list[str]:
    return [
        "Step-by-step verification — from Python to the TUI:",
        "",
        "1. Python version:",
        f"    {_py()} --version",
        "",
        "2. Check if UI packages are visible:",
        f'    {_py()} -c "import textual, rich; '
        'print(textual.__version__, rich.__version__)"',
        "",
        "3. Check that NEX CLI responds:",
        f"    {_py()} -m vliw --version",
        f"    {_py()} -m vliw --help",
        "",
        "4. Model and scenario diagnostics:",
        f"    {_py()} -m vliw doctor",
        f"    {_py()} -m vliw selfcheck --seeds 20",
        "",
        "5. Full project test suite (takes a few minutes):",
        f"    {_py()} -m unittest discover -s tests",
        "",
        "If the first three commands work but the full-screen UI won't open, "
        "the issue is the terminal: run from a real interactive terminal, "
        "not a redirected pipe or non-TTY IDE console.",
        "",
        "Verify you are in a real TTY:",
        f'    {_py()} -c "import sys; '
        'print(sys.stdin.isatty(), sys.stdout.isatty())"',
        "Expected output: True True",
    ]


def _запуск() -> list[str]:
    return [
        "Standard launch — from the project directory with venv activated:",
        "    python -m vliw",
        "",
        "Opens the mode picker: CODE, LAB, AGENT, CORE. Arrow keys and Enter "
        "to navigate, Esc to go back, Ctrl+C to exit.",
        "",
        "Jump straight into a mode:",
        "    python -m vliw code",
        "    python -m vliw lab",
        "    python -m vliw mind",
        "",
        "Single command without the full-screen UI:",
        "    python -m vliw run slotclash",
        "    python -m vliw compare",
        "    python -m vliw scenarios",
        "",
        "Line-by-line plain mode if panes aren't needed or the terminal can't render them:",
        "    python -m vliw --plain",
        "",
        "After installing the package, the short command is available:",
        "    vliw",
        "",
        "Full list of commands:  python -m vliw --help",
    ]


def _проблема() -> list[str]:
    return [
        "Diagnostic checklist — covers almost every failure mode:",
        "",
        "1. Make sure you're in a real terminal, not a pipe or IDE console:",
        f'    {_py()} -c "import sys; '
        'print(sys.stdin.isatty(), sys.stdout.isatty())"',
        "Must print True True. If False, open PowerShell, Windows Terminal, "
        "or a standard Linux/macOS terminal.",
        "",
        "2. Inspect the raw error message in plain mode:",
        "    python -m vliw --plain",
        "This shows the real traceback instead of falling back to the setup screen.",
        "",
        "3. Check UI packages:",
        f'    {_py()} -c "import textual, rich; '
        'print(textual.__version__, rich.__version__)"',
        "If a module is missing:",
        f"    {_tui_only()}",
        "",
        "4. Check that Python is 3.10 or newer:",
        f"    {_py()} --version",
        "",
        "5. Run built-in diagnostics:",
        f"    {_py()} -m vliw doctor",
        "",
        "Common causes: textual installed into a different Python; launching via "
        "the Microsoft Store stub; terminal lacks full-screen support; legacy cmd "
        "without UTF-8 (fix with chcp 65001).",
        "",
        "If nothing helped, share the last lines of the traceback from "
        "--plain: they pinpoint which module or file failed.",
    ]


def _venv() -> list[str]:
    return [
        "A virtual environment (venv) is an isolated folder with its own Python "
        "and packages. It keeps NEX CLI dependencies separate from system Python.",
        "",
        "Create in the project directory:",
        f"    cd {_project_text()}",
        f"    {_py()} -m venv .venv",
        "",
        "Activate:",
        f"    {_activate()}",
        "Your prompt will show (.venv). From then on, python and pip use the venv.",
        "",
        "Install packages and launch:",
        "    python -m pip install --upgrade pip",
        '    python -m pip install -e ".[tui]"',
        "    python -m vliw",
        "",
        "Leave the environment:  deactivate",
        "",
        "If pip is missing or ensurepip fails:",
        f"    {_py()} -m ensurepip --upgrade",
        f"    {_py()} -m pip install --upgrade pip",
        "",
        "Delete the environment by removing its folder:",
        r"    rmdir /s /q .venv        (Windows)",
        "    rm -rf .venv             (Linux / macOS)",
    ]


def _обновление() -> list[str]:
    return [
        "If the project is installed from source:",
        f"    cd {_project_text()}",
        "    git pull",
        '    python -m pip install --upgrade -e ".[tui]"',
        "",
        "Update only the UI packages:",
        '    python -m pip install --upgrade "textual>=8.2" "rich>=13"',
        "",
        "Verify versions after updating:",
        f"    {_py()} -m vliw --version",
        f'    {_py()} -c "import textual, rich; '
        'print(textual.__version__, rich.__version__)"',
        "",
        "If the update broke the environment, recreate .venv from scratch:",
        r"    rmdir /s /q .venv        (Windows)",
        "    rm -rf .venv             (Linux / macOS)",
        f"    {_py()} -m venv .venv",
        f"    {_activate()}",
        '    python -m pip install -e ".[tui]"',
        "",
        "Settings and scenarios live outside site-packages, so recreating "
        "the venv won't touch them.",
    ]


def _удаление() -> list[str]:
    return [
        "Uninstall in three steps — from package to folders:",
        "",
        "1. Remove NEX CLI from the current environment:",
        f"    {_py()} -m pip uninstall vliw-ai-scheduler",
        "",
        "2. Remove the virtual environment (if installed in .venv):",
        r"    rmdir /s /q .venv        (Windows)",
        "    rm -rf .venv             (Linux / macOS)",
        "",
        "3. Delete the project directory if you no longer need it.",
        "",
        "Only uninstall UI packages if no other tools depend on them:",
        f"    {_py()} -m pip uninstall textual rich",
        "",
        "Optionally clear the pip cache:",
        f"    {_py()} -m pip cache purge",
        "",
        "API keys entered via /key or /ai are kept in memory only — "
        "nothing is written to disk.",
    ]


def _данные() -> list[str]:
    return [
        "Built-in scenarios are compact dependency graphs illustrating specific "
        "e2k VLIW hazards. List them:",
        "    python -m vliw scenarios",
        "",
        "The flagship scenario is slotclash: an instruction sequence where division "
        "monopolizes a port and stalls other ops, showing why reordering matters.",
        "",
        "Run a scenario and compare against the oracle:",
        "    python -m vliw run slotclash",
        "    python -m vliw compare",
        "",
        "Load a real .s file from the lcc compiler:",
        "    python -m vliw load examples/probe.s",
        "",
        "Summary across all scenarios and random graphs:",
        "    python -m vliw all",
        "    python -m vliw sweep --seeds 20",
        "",
        "The real_candidates_100_400 folder contains real candidate measurements; "
        "eval_real is the evaluation suite for schedule quality.",
    ]


def _агент() -> list[str]:
    return [
        "The agent is optional: it answers questions about the current graph "
        "using an LLM. Without an API key, the UI and scheduler work normally.",
        "",
        "Set a key for the current session (not saved to disk):",
        "    python -m vliw",
        "    /key YOUR_KEY",
        "    /ai openai key=YOUR_KEY model=gpt-4o-mini",
        "",
        "Or via environment variables:",
        "    OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,",
        "    MISTRAL_API_KEY, YANDEX_API_KEY, NEX_API_KEY",
        "",
        "Local model (Ollama, vLLM) via local-server with any non-empty key:",
        "    /ai local-server key=local model=your-model",
        "",
        "Check status:  /ai",
        'Ask in one shot:  python -m vliw ask "why is the schedule shaped like this?"',
        "",
        "If the agent is silent, check your key and internet connection; on "
        "network errors it responds honestly offline rather than fabricating answers.",
    ]


def _беседа() -> list[str]:
    return [
        "Hello! I'm the NEX CLI NNL assistant.",
        "",
        "I can help you understand what the scheduler does, what to install on "
        "a new machine, why the full-screen interface isn't opening, and how to "
        "verify everything works.",
        "",
        "Ask in plain words — for example:",
        '  "how to install", "system requirements", "missing textual",',
        '  "interface won\'t start", "how on Windows", "how to uninstall".',
        "",
        'You can pick a menu item by number or ask a question with "?".',
    ]


def _nnl() -> list[str]:
    return [
        "NNL is not a large language model — it is a collection of small trained "
        "blocks. Each block solves one narrow task: suggest a schedule, estimate "
        "a gain, or route a question to a topic.",
        "",
        "How the help block works:",
        "  1. splits the question into words and 3-4 character n-grams;",
        "  2. hashes each token via crc32 into a row of embedding table E;",
        "  3. averages the rows into a single vector h;",
        "  4. linear layer h·U + b scores topics; softmax converts to probabilities.",
        "",
        "Weights were trained on real question phrasings rather than hand-coded. "
        "However, it is a topic classifier, not a conversational model: it does "
        "not remember dialogue context.",
        "",
        "That's why keyword matching runs before the block: it catches exact "
        "names (textual, venv, slotclash) and distinguishes questions about "
        "installation from launch commands. Full LLM conversation lives in "
        "AGENT mode, which requires an API key and sees the full dialogue.",
        "",
        "To be transparent: the agent in AGENT mode is not fine-tuned on your "
        "chats. The CLI relies on keyword routing and the trained NNL classifier.",
    ]


_ОТВЕТЫ = {
    "зачем": _зачем,
    "требования": _требования,
    "установка": _установка,
    "textual": _textual,
    "система": _система,
    "проверка": _проверка,
    "запуск": _запуск,
    "проблема": _проблема,
    "venv": _venv,
    "обновление": _обновление,
    "удаление": _удаление,
    "данные": _данные,
    "агент": _агент,
    "nnl": _nnl,
    "беседа": _беседа,
}


# Short answer — what the assistant says immediately. Not a full manual: 3-5
# lines followed by a suggested action. The full text (`ответ`) is tucked behind
# "More details" so a simple question doesn't turn into a wall of commands.
_КРАТКО: dict[str, list[str]] = {
    "зачем": [
        "NEX CLI is an instruction scheduler for the Elbrus e2k VLIW architecture. "
        "It shows where instructions contend for ports and how many cycles "
        "can be recovered by reordering.",
        "The CODE / LAB / AGENT panes use Textual. The scheduler and one-shot "
        "commands work without it.",
    ],
    "требования": [
        "Requires Python 3.10+ (3.12 recommended) and ~100 MB of disk space. "
        "No GPU, numpy, or real Elbrus hardware needed.",
        "Internet is only needed to install textual and rich.",
    ],
    "установка": [
        "I can install textual and rich into the current Python environment and "
        "launch NEX CLI right away — no manual commands required.",
    ],
    "textual": [
        "Textual powers the full-screen panes and tabs; rich handles colors and "
        "tables. Without them NEX CLI still runs, but opens this helper screen "
        "instead of the full-screen UI.",
    ],
    "система": [
        "Windows: use py -3 or python. Linux and macOS: python3. "
        "In PowerShell, activate venv via .venv\\Scripts\\activate.",
        "If legacy cmd garbles Unicode, enable UTF-8 with chcp 65001.",
    ],
    "проверка": [
        "I will check Python, pip, textual, rich, and your terminal without "
        "modifying anything.",
    ],
    "запуск": [
        "I will launch NEX CLI. If textual is missing, I'll install it first so "
        "the full-screen panes can start.",
    ],
    "проблема": [
        "I will check your environment, install anything missing, and retry "
        "launching NEX CLI. If it still fails, I'll show how to get a traceback.",
    ],
    "venv": [
        "An isolated .venv protects your system Python. I'll show the exact "
        "commands to run inside the project directory.",
    ],
    "обновление": [
        "I will update textual and rich. If the project is installed from source, "
        "I'll also show the git pull and reinstall commands.",
    ],
    "удаление": [
        "I will show the safe uninstall steps. I won't delete anything "
        "automatically since that is irreversible.",
    ],
    "данные": [
        "Built-in scenarios are included; the flagship is slotclash, where "
        "division monopolizes a port and blocks other instructions.",
        "I'll open NEX CLI — you can run the scenario from there with one command.",
    ],
    "агент": [
        "The agent is optional: the scheduler and UI work without a key. "
        "Keys are kept in memory for the session only and never written to disk.",
    ],
    "беседа": [
        "Hello! Tell me what you need: launch NEX CLI, install the UI, "
        "check your environment, or troubleshoot an error.",
    ],
    "nnl": [
        "NNL is a set of small trained blocks, not a large language model. "
        "The help block computes a bag of words and linearly classifies the topic.",
        "It does not remember conversation context. Full LLM chat is in AGENT "
        "mode, which requires an API key.",
    ],
}


def кратко(тема: str) -> list[str]:
    """Opening lines of the answer — for the assistant before offering an action."""
    if тема in _КРАТКО:
        return list(_КРАТКО[тема])
    полный = ответ(тема) or []
    return [s for s in полный if s.strip()][:2]


def ответ(тема: str) -> list[str] | None:
    """Paragraphs of the answer for a topic; None if unknown."""
    fn = _ОТВЕТЫ.get(тема)
    return fn() if fn else None


def темы() -> list[str]:
    return list(_ОТВЕТЫ)


def не_понял(вопрос_ли: bool = True) -> list[str]:
    """Polite fallback when the block did not recognize the topic."""
    if not вопрос_ли:
        return _беседа()
    return [
        "I'm not sure I understood that — it doesn't look like a question about "
        "installing or using NEX CLI.",
        "",
        "I can answer questions about:",
        "  • what NEX CLI is for and what it does;",
        "  • system requirements and installation (Python, venv, textual, rich);",
        "  • launching, errors, and why the UI won't open;",
        "  • Windows / Linux / macOS specifics;",
        "  • verification, tests, updating, and uninstalling;",
        "  • scenarios, data, and the LLM agent.",
        "",
        'Try rephrasing or pick a menu item — e.g. "how to install" '
        'or "interface won\'t start".',
    ]


def подсказки() -> list[str]:
    return [f'"{q}"' for q in (
        "how to install", "system requirements", "why won't it open",
        "missing textual", "how on Windows", "how to verify", "how to uninstall",
    )]
