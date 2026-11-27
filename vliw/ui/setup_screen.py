"""Interactive setup assistant screen shown when the full-screen TUI cannot start.

Displayed whenever the full-screen Textual UI is unavailable and `--plain`
was not explicitly requested. Acts as a lightweight assistant: the user can
type plain questions ("launch", "missing textual", "won't start") or pick an
item with arrow keys, inspect the exact shell commands, confirm, and run safe
setup steps (install missing packages, verify the environment, launch NEX CLI).

Pure standard library: ANSI colors from `vliw.ui.render`, header from
`vliw.ui.logo`, answers from `vliw.help_answers`. Requires neither textual,
rich, nor numpy.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

from .. import VERSION_LABEL, help_answers, help_nnl
from . import render
from .logo import render_title
from .render import Style, paint

# Purple theme active only for the lifetime of this boot/setup screen.
_BOOT_THEME = "nnl-purple"

MIN_TEXTUAL = "8.2"
MIN_RICH = "13"

_VT: bool | None = None


# --------------------------------------------------------------------------
# Environment detection and reasons the full-screen UI could not start
# --------------------------------------------------------------------------


def _has(module: str) -> bool:
    """Check whether a module is installed without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # pragma: no cover - broken environment
        return False


def missing() -> list[str]:
    """Missing UI packages as pip requirement specs."""
    out: list[str] = []
    if not _has("textual"):
        out.append(f"textual>={MIN_TEXTUAL}")
    if not _has("rich"):
        out.append(f"rich>={MIN_RICH}")
    return out


def reasons(extra: str | None = None) -> list[str]:
    """List concrete reasons why the full-screen UI did not start."""
    out: list[str] = []
    if sys.version_info < (3, 10):
        out.append(
            f"Python {platform.python_version()} is older than 3.10 — "
            "NEX CLI requires 3.10 or newer"
        )
    if not _has("textual"):
        out.append(
            f"package textual is not installed (requires >= {MIN_TEXTUAL}) — "
            "needed for the full-screen interface"
        )
    elif not _has("rich"):
        out.append(
            f"package rich is not installed (requires >= {MIN_RICH}) — "
            "needed for colored output"
        )
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        out.append(
            "stdin or stdout is not attached to a terminal "
            "(pipe, file redirection, or non-interactive console)"
        )
    if extra:
        out.append(extra)
    if not out:
        out.append("full-screen mode is disabled in this environment")
    return out


def _exe() -> str:
    """Current Python executable path, quoted if it contains spaces."""
    return f'"{sys.executable}"' if " " in sys.executable else sys.executable


def _project_dir() -> Path | None:
    """Project root directory when running from source (contains pyproject.toml)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _store_stub() -> bool:
    """Whether running via the WindowsApps Microsoft Store Python stub."""
    return "WindowsApps" in sys.executable


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _version(module: str) -> str:
    try:
        return importlib.metadata.version(module)
    except Exception:
        return "installed" if _has(module) else "missing"


def _tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


# --------------------------------------------------------------------------
# Layout helpers: wrapping, boxes, arrow-key menu
# --------------------------------------------------------------------------


def _ширина() -> int:
    return max(48, min(92, render.term_cols() - 6))


def _обернуть(текст: str, ширина: int) -> list[str]:
    """Wrap prose; lines indented by 4 spaces are shell commands left intact."""
    if not текст:
        return [""]
    if текст.startswith("    "):
        return [текст]
    return render.wrap(текст, ширина)


def _рамка(строки: list[str], заголовок: str, ширина: int, роль: str = "border") -> list[str]:
    """Draw a box around plain text lines with given outer width."""
    внутренняя = ширина - 4
    тело: list[str] = []
    for строка in строки:
        тело += _обернуть(строка, внутренняя)
    заголовок = заголовок[: max(0, ширина - 6)]
    верх = ("  " + paint(роль, "┌─ ") + paint("accent", заголовок)
            + paint(роль, " " + "─" * max(0, ширина - 5 - len(заголовок)) + "┐"))
    низ = "  " + paint(роль, "└" + "─" * (ширина - 2) + "┘")
    out = [верх]
    for строка in тело:
        out.append("  " + paint(роль, "│ ") + render.pad(строка, внутренняя) + paint(роль, " │"))
    out.append(низ)
    return out


def _заголовок(раздел: str) -> list[str]:
    return ["", "  " + paint("accent", раздел), "  " + Style.dim("─" * min(64, render.term_cols() - 6))]


def _пункт(текст: str) -> str:
    return "    " + Style.dim("•") + " " + текст


def _статус() -> str:
    venv = "venv" if _in_venv() else "no venv"
    textual = _version("textual") if _has("textual") else "missing"
    rich = _version("rich") if _has("rich") else "missing"
    return (f"Python {platform.python_version()} · {platform.system()} "
            f"{platform.release()} · {venv} · textual: {textual} · rich: {rich}")


def _статус_кратко() -> str:
    venv = "venv" if _in_venv() else "no venv"
    textual = "ok" if _has("textual") else "missing"
    rich = "ok" if _has("rich") else "missing"
    tty = "TTY OK" if _tty() else "NOT A TTY"
    return (f"Python {platform.python_version()} · {venv} · textual: {textual} · "
            f"rich: {rich} · {tty}")


def _о_продукте() -> list[str]:
    return [
        "NEX CLI is a workspace for instruction scheduling on the Elbrus e2k "
        "VLIW architecture. It shows how instructions map onto channels and "
        "ports, where cycles are lost, and what can be sped up by reordering.",
        "",
        "Three modes inside: CODE — .s editor and schedule; LAB — full graph "
        "and diagnostics; AGENT — LLM Q&A about the current graph. The scheduler, "
        "oracle, and one-shot commands run on pure Python without full-screen panes.",
    ]


def _приветствие() -> list[str]:
    return [
        "Hello! I'm the NEX CLI NNL assistant.",
        "Tell me what you need — I can install missing packages, launch, or troubleshoot.",
    ]


def _шапка_кратко() -> list[str]:
    """Compact launch header: brick-style 'NNL' logo + title line."""
    out = render_title(indent="  ")
    out += [
        "",
        "  " + paint("title", "NEX CLI") + Style.dim("  ·  ")
        + paint("mountain", "NNL Assistant") + Style.dim("  ·  ")
        + paint("mountain", "Elbrus e2k") + Style.dim("  ·  ")
        + paint("warning", VERSION_LABEL),
    ]
    return out


def _печать_причины(extra: str | None) -> None:
    """Print failure reasons with aligned continuation lines."""
    ширина = max(24, render.term_cols() - 4)
    for i, причина in enumerate(reasons(extra)):
        подпись = "  Reason: " if i == 0 else "          "
        for j, часть in enumerate(render.wrap(причина, ширина - len(подпись))):
            префикс = подпись if (i == 0 and j == 0) else " " * len(подпись)
            print(префикс + часть)


# --------------------------------------------------------------------------
# Keyboard input: arrow keys and Enter using stdlib only
# --------------------------------------------------------------------------


def _vt_доступен() -> bool:
    """Whether ANSI VT escape sequences are supported."""
    global _VT
    if _VT is not None:
        return _VT
    if os.name != "nt":
        _VT = True
        return _VT
    try:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.GetStdHandle(-11)
        режим = ctypes.c_uint32()
        if not k.GetConsoleMode(handle, ctypes.byref(режим)):
            _VT = False
        else:
            _VT = bool(k.SetConsoleMode(handle, режим.value | 0x0004))
    except Exception:  # pragma: no cover - legacy Windows
        _VT = False
    return _VT


def _клавиша() -> str:
    """Read a single key: up / down / enter / esc or printable char."""
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "вверх", "P": "вниз", "K": "влево", "M": "вправо"}.get(
                msvcrt.getwch(), ""
            )
        if ch == "\r":
            return "ввод"
        if ch == "\x1b":
            return "esc"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    старые = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if not select.select([fd], [], [], 0.05)[0]:
                return "esc"
            if sys.stdin.read(1) != "[":
                return "esc"
            if not select.select([fd], [], [], 0.05)[0]:
                return "esc"
            return {"A": "вверх", "B": "вниз", "C": "вправо", "D": "влево"}.get(
                sys.stdin.read(1), ""
            )
        if ch in ("\r", "\n"):
            return "ввод"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, старые)


def _строка_пункта(метка: str, подсказка: str, выбран: bool) -> str:
    указатель = paint("accent", ">") if выбран else " "
    if подсказка:
        доступно = render.term_cols() - 5 - len(метка)
        if доступно <= 3:
            подсказка = ""
        elif len(подсказка) > доступно:
            подсказка = подсказка[: max(1, доступно - 1)] + "…"
    текст = paint("title", метка) if выбран else метка
    if подсказка:
        текст += "  " + Style.dim(подсказка)
    return "  " + указатель + " " + текст


def _меню_вводом(
    пункты: list[tuple[str, str]],
    заголовок: str,
    подсказка: str,
    приём_текста: bool,
) -> int | str | None:
    """Fallback numbered menu for terminals without ANSI VT support."""
    if заголовок:
        хвост = ("   " + подсказка) if подсказка else ""
        print("  " + paint("accent", заголовок) + Style.dim(хвост))
    for i, (метка, хвост) in enumerate(пункты, 1):
        строка = f"  {i}. {метка}"
        if хвост:
            строка += "  " + Style.dim(хвост)
        print(строка)
    try:
        ответ = input("  " + paint("prompt", "NNL") + Style.dim(" > ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not ответ:
        return 0
    if ответ.lower() in ("q", "quit", "exit", "выход", "0"):
        return None
    if ответ.isdigit():
        i = int(ответ) - 1
        if 0 <= i < len(пункты):
            return i
    if приём_текста:
        return ответ
    print("  " + Style.dim("Invalid choice."))
    return None


def _меню(
    пункты: list[tuple[str, str]],
    *,
    заголовок: str = "",
    подсказка: str = "↑/↓ — select · Enter — confirm",
    приём_текста: bool = False,
) -> int | str | None:
    """Arrow-key menu returning selected index, typed query, or None (exit/back)."""
    if not _tty() or not _vt_доступен():
        return _меню_вводом(пункты, заголовок, подсказка, приём_текста)

    индекс = 0
    высота = 0

    def строки() -> list[str]:
        out: list[str] = []
        if заголовок:
            хвост = ("   " + подсказка) if подсказка else ""
            out.append("  " + paint("accent", заголовок) + Style.dim(хвост))
        for i, (метка, хвост) in enumerate(пункты):
            out.append(_строка_пункта(метка, хвост, i == индекс))
        return out

    def нарисовать(первый: bool = False) -> None:
        nonlocal высота
        новые = строки()
        if not первый:
            sys.stdout.write(f"\033[{высота}A")
        for строка in новые:
            sys.stdout.write("\r\033[2K" + строка + "\n")
        sys.stdout.flush()
        высота = len(новые)

    нарисовать(первый=True)
    while True:
        try:
            k = _клавиша()
        except KeyboardInterrupt:
            print()
            return None
        if k == "вверх":
            индекс = (индекс - 1) % len(пункты)
            нарисовать()
        elif k == "вниз":
            индекс = (индекс + 1) % len(пункты)
            нарисовать()
        elif k in ("ввод", " "):
            print()
            return индекс
        elif k.lower() in ("q", "й") or k == "esc":
            print()
            return None
        elif len(k) == 1 and k.isdigit():
            i = int(k) - 1
            if 0 <= i < len(пункты):
                индекс = i
                нарисовать()
                print()
                return индекс
        elif приём_текста and len(k) == 1 and k.isprintable():
            print()
            try:
                хвост = input("  " + paint("prompt", "NNL") + Style.dim(" > ") + k)
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            return k + хвост


# --------------------------------------------------------------------------
# Action plans: commands the assistant proposes and executes on approval
# --------------------------------------------------------------------------


def _команда_текст(команда: list[str]) -> str:
    """Format a command list cleanly for copy-paste into a shell."""
    if os.name == "nt":
        части: list[str] = []
        for аргумент in команда:
            if not аргумент:
                части.append('""')
            elif any(c in аргумент for c in ' \t"<>|&^'):
                части.append('"' + аргумент.replace('"', '\\"') + '"')
            else:
                части.append(аргумент)
        return " ".join(части)
    return " ".join(shlex.quote(x) for x in команда)


def _пакеты_интерфейса() -> list[str]:
    return missing() or [f"textual>={MIN_TEXTUAL}", f"rich>={MIN_RICH}"]


def _команда_установки(пакеты: list[str] | None = None) -> list[str]:
    return [sys.executable, "-m", "pip", "install", "--upgrade",
            *(пакеты or _пакеты_интерфейса())]


def _шаг_установки(пакеты: list[str] | None = None) -> dict:
    пакеты = пакеты or _пакеты_интерфейса()
    return {
        "текст": "Install " + ", ".join(пакеты),
        "команда": _команда_установки(пакеты),
        "вид": "установка",
    }


def _шаг_запуска() -> dict:
    return {
        "текст": "Launch NEX CLI",
        "команда": [sys.executable, "-m", "vliw"],
        "вид": "запуск",
    }


def _план_запуска() -> dict:
    пакеты = missing()
    шаги: list[dict] = []
    резюме: list[str] = []
    if пакеты:
        резюме.append(
            "I will install " + " and ".join(пакеты) + " first, then open NEX CLI. "
            "This takes less than a minute."
        )
        шаги.append(_шаг_установки(пакеты))
    else:
        резюме.append("Everything is ready — opening NEX CLI.")

    if _tty():
        шаги.append(_шаг_запуска())
    else:
        резюме.append(
            "Terminal is non-interactive: the full-screen UI cannot open here. "
            "Run the same command from PowerShell, Windows Terminal, or a "
            "standard Linux/macOS terminal."
        )
    if _store_stub():
        резюме.append(
            "Warning: running via the Microsoft Store Python stub. "
            "Installing Python from python.org is recommended so packages "
            "land in the right interpreter."
        )

    if пакеты and _tty():
        название = "Install UI packages and open NEX CLI"
        кнопка = "Install and open"
    elif пакеты:
        название = "Install UI packages"
        кнопка = "Install"
    else:
        название = "Open NEX CLI"
        кнопка = "Open NEX CLI"
    return {
        "название": название,
        "тема": "запуск",
        "резюме": резюме,
        "шаги": шаги,
        "можно_выполнить": bool(шаги),
        "кнопка": кнопка,
    }


def _план_починки() -> dict:
    пакеты = missing()
    шаги: list[dict] = []
    резюме = ["I will check what is missing, install missing UI packages, and retry opening NEX CLI."]
    if пакеты:
        шаги.append(_шаг_установки(пакеты))
    if _tty():
        шаги.append(_шаг_запуска())
    else:
        резюме.append(
            "This terminal is non-interactive — open a real terminal window first "
            "so full-screen mode can start."
        )
    if not пакеты and _tty():
        резюме.append("Packages are installed. If the UI still won't open, I'll show how to get a traceback.")
    return {
        "название": "Fix launch",
        "тема": "проблема",
        "резюме": резюме,
        "шаги": шаги,
        "можно_выполнить": bool(шаги),
        "кнопка": "Fix and open",
    }


def _план_проверки() -> dict:
    return {
        "название": "Check environment",
        "тема": "проверка",
        "резюме": ["I will check Python, pip, textual, rich, and your terminal without changing anything."],
        "шаги": [{"текст": "Collect diagnostics", "вид": "проверка"}],
        "можно_выполнить": True,
        "кнопка": "Check now",
    }


def _план_обновления() -> dict:
    пакеты = _пакеты_интерфейса()
    return {
        "название": "Update UI packages",
        "тема": "обновление",
        "резюме": ["I will upgrade textual and rich to the latest versions. Scenarios and settings are untouched."],
        "шаги": [_шаг_установки(пакеты)],
        "можно_выполнить": True,
        "кнопка": "Update",
    }


def _план_venv() -> dict:
    проект = _project_dir()
    if проект is None:
        return {
            "название": "Isolated .venv environment",
            "тема": "venv",
            "резюме": [
                "Project directory not found, so I cannot fill in the exact path. "
                "Create the virtual environment inside your project folder using the commands below."
            ],
            "шаги": [
                {"текст": "Create virtual environment", "команда": [sys.executable, "-m", "venv", ".venv"]},
                {"текст": "Install NEX CLI with TUI",
                 "команда": ["python", "-m", "pip", "install", "-e", ".[tui]"]},
            ],
            "можно_выполнить": False,
            "кнопка": "Show commands",
        }
    cwd = str(проект)
    if os.name == "nt":
        python = str(проект / ".venv" / "Scripts" / "python.exe")
    else:
        python = str(проект / ".venv" / "bin" / "python")
    return {
        "название": "Isolated .venv environment",
        "тема": "venv",
        "резюме": [
            "I will create .venv in the project directory, install NEX CLI with the TUI, "
            "and launch it. System Python remains untouched."
        ],
        "шаги": [
            {"текст": "Create .venv environment",
             "команда": [sys.executable, "-m", "venv", ".venv"], "cwd": cwd},
            {"текст": "Install NEX CLI with TUI",
             "команда": [python, "-m", "pip", "install", "-e", ".[tui]"], "cwd": cwd},
            {"текст": "Launch NEX CLI from .venv",
             "команда": [python, "-m", "vliw"], "cwd": cwd, "вид": "запуск"},
        ],
        "можно_выполнить": True,
        "кнопка": "Create and open",
    }


def _план_удаления() -> dict:
    if os.name == "nt":
        удалить_venv = ["cmd", "/c", "rmdir", "/s", "/q", ".venv"]
    else:
        удалить_venv = ["rm", "-rf", ".venv"]
    return {
        "название": "Uninstall NEX CLI",
        "тема": "удаление",
        "резюме": [
            "I will show the safe uninstall steps. I won't delete anything automatically since it is irreversible."
        ],
        "шаги": [
            {"текст": "Uninstall NEX CLI package",
             "команда": [sys.executable, "-m", "pip", "uninstall", "vliw-ai-scheduler"]},
            {"текст": "Remove .venv environment (if created)", "команда": удалить_venv},
            {"текст": "Delete the project folder manually if no longer needed"},
        ],
        "можно_выполнить": False,
        "кнопка": "Show commands",
    }


def _план_для_темы(тема: str) -> dict | None:
    if тема in ("запуск", "установка", "textual", "проблема", "требования",
                "система", "зачем", "данные", "агент"):
        return _план_запуска()
    if тема == "проверка":
        return _план_проверки()
    if тема == "обновление":
        return _план_обновления()
    if тема == "venv":
        return _план_venv()
    if тема == "удаление":
        return _план_удаления()
    return None


def _напечатать_план(план: dict) -> None:
    print()
    print("  " + paint("accent", "NNL · " + план["название"]))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    ширина = render.term_cols() - 6
    for абзац in план.get("резюме", []):
        for часть in _обернуть(абзац, ширина):
            print("  " + часть if часть else "")
    print("  " + Style.dim("Current: " + _статус_кратко()))
    print()
    print("  " + Style.dim("Plan:"))
    for i, шаг in enumerate(план.get("шаги", []), 1):
        print("   " + paint("accent", str(i)) + ". " + шаг["текст"])
        if шаг.get("cwd"):
            print("      " + Style.dim("cd " + шаг["cwd"]))
        if шаг.get("команда"):
            print("      " + paint("success", _команда_текст(шаг["команда"])))
    print()


def _напечатать_команды(план: dict) -> None:
    print()
    print("  " + paint("accent", "NNL · commands"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    for i, шаг in enumerate(план.get("шаги", []), 1):
        print()
        print("  " + Style.dim(f"{i}. {шаг['текст']}"))
        if шаг.get("cwd"):
            print("    " + Style.dim("cd " + шаг["cwd"]))
        if шаг.get("команда"):
            print("    " + paint("success", _команда_текст(шаг["команда"])))
        elif not шаг.get("вид"):
            print("    " + Style.dim("manual step"))
    print()


def _выполнить(команда: list[str], cwd: str | None = None) -> int:
    print()
    print("  " + Style.dim("$ " + _команда_текст(команда)))
    try:
        return subprocess.call(команда, cwd=cwd)
    except OSError as e:
        print("  " + paint("error", f"failed to run: {e}"))
        return 1


def _выполнить_план(план: dict, только_установка: bool = False) -> int | None:
    """Execute plan steps after user confirmation. Returns 0 if TUI launched."""
    шаги = план.get("шаги", [])
    for i, шаг in enumerate(шаги, 1):
        if только_установка and шаг.get("вид") == "запуск":
            break
        print()
        print("  " + paint("accent", f"[{i}/{len(шаги)}] {шаг['текст']}"))
        if шаг.get("вид") == "проверка":
            _проверить(пауза=False)
            continue
        команда = шаг.get("команда")
        if not команда:
            print("  " + Style.dim("this step must be performed manually"))
            continue

        код = _выполнить(команда, шаг.get("cwd"))
        if шаг.get("вид") == "установка":
            if код != 0 and not _has("pip"):
                print()
                print("  " + paint("warning", "pip not found — installing via ensurepip"))
                _выполнить([sys.executable, "-m", "ensurepip", "--upgrade"])
                код = _выполнить(команда, шаг.get("cwd"))
            importlib.invalidate_caches()
            if код == 0 and missing():
                print()
                print("  " + paint("warning", "pip succeeded, but modules are still not visible."))
                print("  " + Style.dim("Packages may have been installed into a different Python. "
                                       "Run pip with the same interpreter as NEX CLI."))
                _пауза()
                return None
        if код != 0:
            print()
            print("  " + paint("error", f"step failed (exit code {код})."))
            print("  " + Style.dim("Check internet access and permissions. If pip is missing:"))
            print("    " + paint("success", f"{_exe()} -m ensurepip --upgrade"))
            _пауза()
            return None
        if шаг.get("вид") == "запуск":
            return 0 if код == 0 else None

    print()
    print("  " + paint("success", "done"))
    if план.get("тема") == "обновление":
        print("  " + Style.dim('If installed from source, also update the repo: git pull, '
                               'then pip install -e ".[tui]".'))
    _пауза()
    return None


def _показать_план(план: dict) -> int | None:
    """Plan card: show commands, ask confirmation, and execute."""
    _напечатать_план(план)
    кнопка = план.get("кнопка", "Run")
    можно = план.get("можно_выполнить", False)
    есть_запуск = any(ш.get("вид") == "запуск" for ш in план.get("шаги", []))
    есть_установка = any(ш.get("вид") == "установка" for ш in план.get("шаги", []))

    while True:
        пункты: list[tuple[str, str]] = []
        if можно:
            пункты.append((кнопка, "run these steps for me"))
            if есть_установка and есть_запуск:
                пункты.append(("Install only", "without launching the UI"))
        else:
            пункты.append(("Show commands", "copy and run manually"))
        if можно:
            пункты.append(("Show commands", "inspect exact commands"))
        if план.get("тема"):
            пункты.append(("More details", "full explanation"))
        пункты.append(("Back", "return to menu"))

        выбор = _меню(пункты, заголовок="What next?")
        if выбор is None:
            return None
        метка = пункты[выбор][0]
        if метка == кнопка and можно:
            return _выполнить_план(план)
        if метка == "Install only":
            return _выполнить_план(план, только_установка=True)
        if метка == "Show commands":
            _напечатать_команды(план)
            _пауза()
        elif метка == "More details":
            _печать_ответа(план["тема"], полный=True)
            _пауза()
        else:
            return None


# --------------------------------------------------------------------------
# Assistant responses
# --------------------------------------------------------------------------


def _печать_ответа(тема: str, полный: bool = False) -> None:
    текст = help_answers.ответ(тема) if полный else help_answers.кратко(тема)
    if not текст:
        return
    заголовок = help_answers.ЗАГОЛОВКИ.get(тема, тема)
    print()
    print("  " + paint("accent", f"NNL · {заголовок}"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    ширина = render.term_cols() - 6
    for строка in текст:
        for часть in _обернуть(строка, ширина):
            if not часть:
                print()
            elif часть.startswith("    "):
                print("  " + paint("success", часть))
            else:
                print("  " + часть)
    print()


def _показать_кратко(тема: str) -> int | None:
    """Short answer plus a single obvious action instead of a wall of text."""
    _печать_ответа(тема)
    план = _план_для_темы(тема)
    while True:
        пункты: list[tuple[str, str]] = []
        if план is not None:
            пункты.append((план.get("кнопка", "Prepare"), "show commands and ask before running"))
        пункты.append(("More details", "full explanation"))
        пункты.append(("Back", "return to menu"))
        выбор = _меню(пункты, заголовок="What next?")
        if выбор is None:
            return None
        метка = пункты[выбор][0]
        if план is not None and метка == план.get("кнопка", "Prepare"):
            return _показать_план(план)
        if метка == "More details":
            _печать_ответа(тема, полный=True)
            _пауза()
        else:
            return None


def _объяснить_установки() -> int | None:
    """Explain why extra packages are requested without starting installation."""
    пакеты = missing()
    ширина = render.term_cols() - 6
    print()
    print("  " + paint("accent", "NNL · why extra packages are needed"))
    print("  " + Style.dim("─" * min(64, ширина)))
    print("  The scheduler, oracle, and one-shot commands run on pure Python.")
    print("  Extra packages are needed only for the full-screen interface:")
    print("    " + paint("success", "textual") + " — panes, tabs, and CODE / LAB / AGENT screens;")
    print("    " + paint("success", "rich") + " — colors, tables, and borders inside them.")
    print()
    if пакеты:
        print("  Currently missing: " + paint("warning", ", ".join(пакеты)) + ".")
        print("  Without them this helper screen opens instead — data and commands are identical.")
    else:
        print("  Both packages are " + paint("success", "installed")
              + " — full-screen UI is available.")
    print()

    пункты: list[tuple[str, str]] = []
    if пакеты:
        пункты.append(("Install and open",
                       "show commands and ask before running"))
    пункты.append(("More details", "full requirements overview"))
    пункты.append(("Back", "return to menu"))
    выбор = _меню(пункты, заголовок="What next?")
    if выбор is None:
        return None
    метка = пункты[выбор][0]
    if пакеты and метка == "Install and open":
        return _показать_план(_план_запуска())
    if метка == "More details":
        _печать_ответа("требования", полный=True)
        _пауза()
    return None


def _беседа(вопрос: str) -> bool:
    """Handle greetings/thanks/farewells. Returns True when user says goodbye."""
    низ = " ".join(вопрос.lower().replace("ё", "е").strip("!?.,;: ").split())
    if низ.startswith(("спасибо", "благодар", "thank", "thx")):
        print()
        print("  " + paint("accent", "NNL · you're welcome"))
        print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
        print("  If you need help launching or setting up, I'm right here.")
        print()
        return False
    if низ in ("пока", "до свидания", "до встречи", "хорошего дня",
               "bye", "goodbye", "see you", "have a nice day"):
        print()
        print("  " + paint("accent", "NNL · see you later"))
        print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
        print("  Launch again: " + paint("success", f"{_exe()} -m vliw"))
        print()
        return True
    _печать_ответа("беседа")
    return False


def _не_понял() -> None:
    print()
    print("  " + paint("warning", "NNL · didn't understand that"))
    print("  " + Style.dim("I only help with NEX CLI: setup, launch, errors, and modes."))
    print("  " + Style.dim("Try rephrasing or pick an option from the menu below."))
    print()


def _проверка_строки() -> list[tuple[str, str, str]]:
    """Return (item, value, status) tuples for environment diagnostics."""
    py_ok = sys.version_info >= (3, 10)
    tty_ok = _tty()
    pip_ok = _has("pip")
    textual_ok = _has("textual")
    rich_ok = _has("rich")
    проект = _project_dir()
    строки = [
        ("Python", f"{platform.python_version()} · "
                   f"{'64-bit' if sys.maxsize > 2 ** 32 else '32-bit'}",
         "OK" if py_ok else "NEED 3.10+"),
        ("terminal", f"{sys.stdin.isatty()} {sys.stdout.isatty()}",
         "OK" if tty_ok else "NOT TTY"),
        ("pip", "available" if pip_ok else "missing — run ensurepip",
         "OK" if pip_ok else "MISSING"),
        ("venv", "active" if _in_venv() else "not active (optional)", "info"),
        ("textual", _version("textual") if textual_ok else "missing", "OK" if textual_ok else "MISSING"),
        ("rich", _version("rich") if rich_ok else "missing", "OK" if rich_ok else "MISSING"),
        ("project", str(проект) if проект else "no pyproject.toml found", "info"),
    ]
    if _store_stub():
        строки.append(("Python", "Microsoft Store stub (WindowsApps)", "WARNING"))
    return строки


def _проверить(пауза: bool = True) -> None:
    print()
    print("  " + paint("accent", "Environment check"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    for имя, значение, статус in _проверка_строки():
        if len(значение) > 46:
            значение = значение[:43] + "..."
        метка = {"OK": paint("success", "OK"), "MISSING": paint("error", "MISSING"),
                 "NOT TTY": paint("warning", "NOT TTY"),
                 "WARNING": paint("warning", "WARNING"),
                 "NEED 3.10+": paint("error", "NEED 3.10+"),
                 "info": Style.dim("—")}.get(статус, статус)
        print("  " + render.pad(имя, 10) + render.pad(значение, 46) + " " + метка)

    print()
    if not _has("textual"):
        print("  " + paint("warning", "Full-screen UI cannot start without textual."))
        print("  " + Style.dim("The assistant can install it and launch NEX CLI."))
    elif not _tty():
        print("  " + paint("warning", "Packages are installed, but the terminal is not interactive."))
        print("  " + Style.dim("Open PowerShell / Windows Terminal / a standard Linux/macOS "
                               "terminal and run again."))
    else:
        print("  " + paint("success", "Everything required is in place — ready to open NEX CLI."))
    if пауза:
        _пауза()


def _пауза() -> None:
    try:
        input("\n  " + Style.dim("Enter — back to menu "))
    except (EOFError, KeyboardInterrupt):
        print()


# --------------------------------------------------------------------------
# Intent detection and main loop
# --------------------------------------------------------------------------


_ПРИЗНАКИ_ПОЧИНКИ = (
    "не работает", "не запускается", "не открывается", "не установ",
    "сломал", "ошибк", "traceback", "падает", "черный экран", "чёрный экран",
    "зависа", "не отвечает", "закрывается сразу",
    "not working", "doesn't work", "won't start", "won't open", "broken",
    "error", "crash", "black screen", "freeze", "fix",
)
_ПРИЗНАКИ_УДАЛЕНИЯ = ("удал", "снести", "деинстал", "uninstall", "стереть установку", "remove")
_ПРИЗНАКИ_ОБНОВЛЕНИЯ = ("обнов", "upgrade", "update", "git pull", "новая версия", "свежую версию")
_ПРИЗНАКИ_VENV = ("venv", "виртуал", "virtualenv", "ensurepip", "pip не найден", "нет pip", "без pip", "no pip")
_ПРИЗНАКИ_ПРОВЕРКИ = ("проверь", "провер", "диагност", "doctor", "selfcheck", "тест", "check", "verify", "test")
_ПРИЗНАКИ_ЗАПУСКА = ("запуст", "открой", "открыть", "старт", "включи", "launch", " run ", "start", "open")
_ПРИЗНАКИ_УСТАНОВКИ = ("установ", "поставь", "поставить", "инсталл", "install",
                       "скачай", "подготовь", "настрой", "setup", "set up")


def _намерение(текст: str) -> str | None:
    """Detect user action intent before falling back to the NNL topic classifier."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    if any(с in низ for с in _ПРИЗНАКИ_ПОЧИНКИ):
        return "починка"
    if any(с in низ for с in _ПРИЗНАКИ_УДАЛЕНИЯ):
        return "удаление"
    if any(с in низ for с in _ПРИЗНАКИ_ОБНОВЛЕНИЯ):
        return "обновление"
    if any(с in низ for с in _ПРИЗНАКИ_VENV):
        return "venv"
    if any(с in низ for с in _ПРИЗНАКИ_ПРОВЕРКИ):
        return "проверка"
    if any(с in низ for с in _ПРИЗНАКИ_ЗАПУСКА):
        return "запуск"
    if any(с in низ for с in _ПРИЗНАКИ_УСТАНОВКИ):
        return "установка"
    return None


# Questions should be answered, not immediately executed as action commands.
_ВОПРОСНЫЕ = (
    "зачем", "почему", "отчего", "для чего", "что такое", "что это",
    "что значит", "что за ", "чем полез", "в чем смысл", "в чём смысл",
    "как работает", "как устроен", "как устроена", "как устроено",
    "как запустить", "как запускается", "как установить", "как ставится",
    "как настроить", "как пользоваться", "как обновить", "как удалить",
    "как проверить", "как создать", "как включить",
    "нужно ли", "надо ли", "обязательно ли", "можно ли", "стоит ли",
    "есть ли", "какие", "какой", "какая", "каких", "каким", "какую",
    "где ", "когда", "сколько",
    "why ", "what is", "what are", "what does", "how to ", "how do ",
    "how does", "do i need", "is it required", "can i ", "where ", "which ",
)


def _это_вопрос(текст: str) -> bool:
    """Return True if the input is an explanatory question rather than an imperative."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    return any(слово in низ for слово in _ВОПРОСНЫЕ)


def _спросили_зачем_установки(текст: str) -> bool:
    """Detect questions asking why extra packages/installations are needed."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    зачем = ("зачем", "почему", "для чего", "нужно ли", "надо ли",
             "обязательно ли", "стоит ли", "why ", "do i need", "is it required")
    про_пакеты = ("установ", "постав", "пакет", "textual", "rich", "доп",
                  "install", "package", "extra", "depend")
    return any(м in низ for м in зачем) and any(м in низ for м in про_пакеты)


def _задать_вопрос(extra: str | None = None) -> int | None:
    try:
        текст = input("  " + paint("prompt", "NNL") + Style.dim(" > ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not текст:
        return None
    return _обработать_запрос(текст, extra)


def _обработать_запрос(текст: str, extra: str | None = None) -> int | None:
    """Route natural-language input to an action plan or short answer. 0 = TUI opened."""
    текст = текст.strip()
    if not текст:
        return None
    if текст in ("?", "？"):
        return _задать_вопрос(extra)

    if _спросили_зачем_установки(текст):
        return _объяснить_установки()

    вид = None if _это_вопрос(текст) else _намерение(текст)
    if вид == "починка":
        return _показать_план(_план_починки())
    if вид == "удаление":
        return _показать_план(_план_удаления())
    if вид == "обновление":
        return _показать_план(_план_обновления())
    if вид == "venv":
        return _показать_план(_план_venv())
    if вид == "проверка":
        return _показать_план(_план_проверки())
    if вид in ("запуск", "установка"):
        return _показать_план(_план_запуска())

    if not help_nnl.доступно():
        print()
        print("  " + paint("warning", "NNL help block not found."))
        print("  " + Style.dim("It looks like nnl_vliw or vliw/help_weights.json "
                               "is missing from this installation."))
        print("  " + Style.dim("Showing manual installation steps instead."))
        _печать_ответа("установка", полный=True)
        return None

    результат = help_nnl.спросить(текст)
    if результат is None:
        _не_понял()
        return None
    тема, _ = результат
    if тема == help_nnl.БЕСЕДА:
        return 1 if _беседа(текст) else None
    return _показать_кратко(тема)


def _главное_меню() -> int | str | None:
    пакеты = missing()
    первый = "Install and launch" if пакеты else "Launch NEX CLI"
    return _меню(
        [
            (первый, "install missing packages and open"),
            ("Check environment", "Python, packages, terminal"),
            ("What is NEX CLI", "brief overview of the scheduler"),
            ("Ask a question", "type in plain English"),
            ("Exit", ""),
        ],
        заголовок="How can I help?",
        подсказка="↑/↓ — select · Enter — confirm",
        приём_текста=True,
    )


def welcome(extra: str | None = None) -> int:
    """Interactive setup assistant: prompt -> plan -> confirmation -> run.

    Returns 0 if the full-screen UI opened; 1 if the user exited.
    """
    render.apply_theme(_BOOT_THEME)
    render.utf8_console()
    if render.Style.enabled:
        render.enable_vt()
    ширина = _ширина()
    for строка in _шапка_кратко():
        print(строка)
    print()
    for строка in _рамка(_приветствие(), "NNL Assistant", ширина):
        print(строка)
    print()
    _печать_причины(extra)
    print("  " + Style.dim(_статус()))
    print()
    print("  " + Style.dim('You can type directly: "launch", "missing textual", "not working".'))
    print()

    while True:
        выбор = _главное_меню()
        if выбор is None:
            print("  " + Style.dim("Goodbye. Launch again: "
                                   + f"{_exe()} -m vliw"))
            return 1
        if isinstance(выбор, str):
            код = _обработать_запрос(выбор, extra)
        elif выбор == 0:
            код = _показать_план(_план_запуска())
        elif выбор == 1:
            код = _показать_план(_план_проверки())
        elif выбор == 2:
            код = _показать_кратко("зачем")
        elif выбор == 3:
            код = _задать_вопрос(extra)
        else:
            print("  " + Style.dim("Goodbye. Launch again: "
                                   + f"{_exe()} -m vliw"))
            return 1
        if код == 0:
            return 0
        if код == 1:
            return 1
        print()


# --------------------------------------------------------------------------
# Static output for pipes, CI, and tests
# --------------------------------------------------------------------------


def lines(extra: str | None = None) -> list[str]:
    """Build static setup-screen lines without printing (useful for tests/pipes)."""
    exe = _exe()
    out: list[str] = [""]
    out += render_title(indent="  ")
    out += [
        "",
        "  " + paint("warning", "full-screen interface did not start")
        + Style.dim("  ·  welcome and setup screen"),
    ]

    out += _заголовок("Why this screen opened")
    for r in reasons(extra):
        out.append(_пункт(r))
    out.append("    " + Style.dim(_статус()))

    out += [""]
    out += _рамка(_приветствие(), "NNL Assistant", _ширина())

    out += _заголовок("About NEX CLI")
    for строка in _о_продукте():
        out.append("  " + строка)

    missing_pkgs = missing()
    if missing_pkgs:
        out += _заголовок("Install (Windows / macOS / Linux)")
        out.append("    " + paint("success", f"{exe} -m pip install "
                                            + " ".join(f'"{p}"' for p in missing_pkgs)))
        project = _project_dir()
        if project is not None:
            out += [
                "",
                "  " + paint("accent", "Or from the project directory (installs NEX CLI too):"),
                "    " + Style.dim(f"cd {project}"),
                "    " + paint("success", f'{exe} -m pip install -e ".[tui]"'),
            ]
        out += [
            "",
            "  " + paint("accent", "Step by step with a virtual environment:"),
            "    " + Style.dim(f"cd {project if project else 'path/to/project/dir'}"),
            "    " + paint("success", f"{exe} -m venv .venv"),
            "    " + Style.dim(".venv\\Scripts\\activate        (Windows)"
                                   "   /   source .venv/bin/activate   (Linux, macOS)"),
            "    " + paint("success", "python -m pip install --upgrade pip"),
            "    " + paint("success", 'python -m pip install "textual>=8.2" "rich>=13"'),
            "",
            "  " + paint("accent", "Verify installation:"),
            "    " + paint("success",
                          f'{exe} -c "import textual, rich; '
                          f'print(textual.__version__, rich.__version__)"'),
        ]

    out += [
        "",
        "  " + paint("accent", "Launch:"),
        "    " + paint("success", f"{exe} -m vliw"),
        "",
        "  " + Style.dim("In an interactive terminal this screen can install missing packages "
                          "and open NEX CLI automatically."),
        "",
        "  " + Style.dim("Works without installing UI packages:"),
        "    " + Style.dim(f"{exe} -m vliw run slotclash"),
        "    " + Style.dim(f"{exe} -m vliw compare"),
        "    " + Style.dim(f"{exe} -m vliw --help"),
        "",
        "  " + Style.dim("Plain line-by-line mode (no panes):"),
        "    " + Style.dim(f"{exe} -m vliw --plain"),
    ]

    out += _заголовок("If the window still won't open")
    out += [
        "    " + Style.dim("Run from a real terminal: PowerShell, cmd,"),
        "    " + Style.dim("Windows Terminal, or a standard Linux/macOS terminal — not a pipe,"),
        "    " + Style.dim("redirected output, or non-TTY IDE console."),
        "    " + Style.dim(f'{exe} -c "import sys; '
                          'print(sys.stdin.isatty(), sys.stdout.isatty())"'),
        "    " + Style.dim("expected output: True True"),
    ]

    if missing_pkgs:
        out += [
            "",
            "  " + Style.dim("No pip?"),
            "    " + Style.dim(f"{exe} -m ensurepip --upgrade"),
        ]

    out += [
        "",
        "  " + Style.dim("Environment:"),
        "    " + Style.dim(_статус()),
        "    " + Style.dim(sys.executable),
    ]
    if _store_stub():
        out += [
            "",
            "  " + paint("error", "warning: running via the Microsoft Store stub (WindowsApps)."),
            "  " + Style.dim("install Python from python.org or call python.exe by full path"),
        ]
    out.append("")
    return out


def explain(extra: str | None = None) -> int:
    """Show the setup screen: interactive in a TTY, static in a pipe."""
    if _tty():
        return welcome(extra)
    render.apply_theme(_BOOT_THEME)
    for line in lines(extra):
        print(line)
    return 1
