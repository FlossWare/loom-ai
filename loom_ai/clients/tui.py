"""Optional live Loom operator TUI.

Presentation/control surface only. Loom core and its HTTP API remain headless.
"""

from __future__ import annotations

import asyncio
import curses
import os
import time
from typing import Any

from . import get_client

try:
    from curses_themes import Dropdown, Option, Table, Tabs, ThemeManager
except ImportError:  # optional UI dependency
    Dropdown = Option = Table = Tabs = ThemeManager = None

THEMES = ["dark", "default", "light", "dos", "borland-3d", "dbase-iii"]


def _theme(name: str):
    if ThemeManager is None:
        return None
    try:
        return ThemeManager.load(name)
    except Exception:
        return None


async def _snapshot() -> dict[str, Any]:
    client = await get_client()
    data: dict[str, Any] = {
        "url": getattr(
            client, "base_url", os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
        ),
        "at": time.strftime("%H:%M:%S"),
    }
    calls = {
        "health": client.health,
        "ready": client.ready,
        "models": client.list_models,
        "knowledge": client.knowledge_stats,
        "tools": client.list_tools,
        "resources": client.list_resources,
    }
    for name, call in calls.items():
        try:
            data[name] = await call()
        except Exception as exc:
            data[name] = {"error": str(exc)}
    return data


def _text(
    win: curses.window, y: int, x: int, value: object, width: int, attr: int = 0
) -> None:
    h, w = win.getmaxyx()
    if 0 <= y < h and x < w - 1:
        try:
            win.addnstr(y, x, str(value), max(1, min(width, w - x - 1)), attr)
        except curses.error:
            pass


def _status(data: dict[str, Any]) -> str:
    health = data.get("health", {})
    if isinstance(health, dict) and health.get("status") in ("ok", "healthy"):
        return "READY"
    if isinstance(health, dict) and health.get("error"):
        return "OFFLINE"
    return "DEGRADED"


def _count(value: object, keys: tuple[str, ...]) -> object:
    if not isinstance(value, dict):
        return value
    for key in keys:
        if key in value:
            return value[key]
    return "available"


def _header(win: curses.window, tabs: Any, theme_name: str, paused: bool) -> None:
    _, w = win.getmaxyx()
    _text(win, 0, 0, "=" * min(w - 1, 78), w, curses.A_BOLD)
    _text(
        win, 1, 2, "FlossWare Loom | Live Operator Control Panel", w - 4, curses.A_BOLD
    )
    _text(
        win, 2, 2, f"theme={theme_name}  refresh={'PAUSED' if paused else '2s'}", w - 4
    )
    if tabs:
        tabs.draw(win, 3, 2)
    else:
        _text(
            win,
            3,
            2,
            "1 Dashboard   2 Models   3 Health   4 Knowledge   5 Tools",
            w - 4,
        )
    _text(win, 4, 0, "-" * min(w - 1, 78), w)


def _table(
    win: curses.window,
    headers: list[str],
    rows: list[tuple[object, ...]],
    y: int,
    height: int,
) -> None:
    if Table:
        Table(headers, rows).draw(win, y, 2, height)
        return
    _text(
        win,
        y,
        2,
        "  ".join(headers),
        win.getmaxyx()[1] - 4,
        curses.A_BOLD | curses.A_UNDERLINE,
    )
    for i, row in enumerate(rows[: max(0, height - 1)], 1):
        _text(win, y + i, 2, "  ".join(map(str, row)), win.getmaxyx()[1] - 4)


def _dashboard(win: curses.window, data: dict[str, Any]) -> None:
    h, w = win.getmaxyx()
    models = data.get("models", [])
    tools = data.get("tools", [])
    resources = data.get("resources", [])
    rows = [
        ("Server", data.get("url", "")),
        ("Status", _status(data)),
        (
            "Ready",
            data.get("ready", {}).get("status", "unknown")
            if isinstance(data.get("ready"), dict)
            else data.get("ready"),
        ),
        ("Models", len(models) if isinstance(models, list) else "error"),
        ("Tools", len(tools) if isinstance(tools, list) else "error"),
        ("Resources", len(resources) if isinstance(resources, list) else "error"),
        (
            "Knowledge",
            _count(
                data.get("knowledge", {}),
                ("documents", "document_count", "total_documents", "count"),
            ),
        ),
        ("Last poll", data.get("at", "")),
    ]
    _text(win, 6, 2, "RUNTIME", w - 4, curses.A_BOLD | curses.A_UNDERLINE)
    _table(win, ["Metric", "Value"], rows, 7, min(12, h - 10))


def _models(win: curses.window, data: dict[str, Any]) -> None:
    h, w = win.getmaxyx()
    models = data.get("models", [])
    if not isinstance(models, list):
        _text(win, 6, 2, f"Model discovery failed: {models}", w - 4)
        return
    _text(
        win, 6, 2, f"MODELS ({len(models)})", w - 4, curses.A_BOLD | curses.A_UNDERLINE
    )
    for i, model in enumerate(models[: max(1, h - 10)]):
        _text(win, 8 + i, 2, f"{i + 1:>3}. {model}", w - 4)
    _text(
        win,
        h - 4,
        2,
        "T changes theme. Model selector is available from the dropdown when the shared widgets package is installed.",
        w - 4,
    )


def _health(win: curses.window, data: dict[str, Any]) -> None:
    rows: list[tuple[object, ...]] = []
    for group in ("health", "ready"):
        value = data.get(group, {})
        if isinstance(value, dict):
            rows.extend((f"{group}.{k}", str(v)[:120]) for k, v in value.items())
        else:
            rows.append((group, value))
    _table(win, ["Field", "Value"], rows, 6, win.getmaxyx()[0] - 8)


def _knowledge(win: curses.window, data: dict[str, Any]) -> None:
    value = data.get("knowledge", {})
    rows = (
        list((str(k), str(v)[:100]) for k, v in value.items())
        if isinstance(value, dict)
        else [("status", value)]
    )
    _table(win, ["Metric", "Value"], rows, 6, win.getmaxyx()[0] - 8)


def _tools(win: curses.window, data: dict[str, Any]) -> None:
    tools = data.get("tools", [])
    rows = []
    for item in tools if isinstance(tools, list) else []:
        if isinstance(item, dict):
            rows.append((item.get("name", ""), item.get("description", "")[:80]))
        else:
            rows.append((str(item), ""))
    _table(win, ["Tool", "Description"], rows, 6, max(2, win.getmaxyx()[0] - 10))
    _text(
        win,
        win.getmaxyx()[0] - 3,
        2,
        f"Resources exposed: {len(data.get('resources', [])) if isinstance(data.get('resources'), list) else 'error'}",
        win.getmaxyx()[1] - 4,
    )


def _run(stdscr: curses.window) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(250)
    theme_name = os.environ.get("FLOSSWARE_TUI_THEME", "dark")
    tabs = (
        Tabs(["Dashboard", "Models", "Health", "Knowledge", "Tools"]) if Tabs else None
    )
    paused = False
    last_poll = 0.0
    data: dict[str, Any] = {"url": os.environ.get("LOOM_URL", "http://127.0.0.1:5000")}
    while True:
        if not paused and time.monotonic() - last_poll >= 2:
            try:
                data = asyncio.run(_snapshot())
            except Exception as exc:
                data = {
                    "url": os.environ.get("LOOM_URL", ""),
                    "health": {"error": str(exc)},
                    "at": time.strftime("%H:%M:%S"),
                }
            last_poll = time.monotonic()
        theme = _theme(theme_name)
        if theme:
            try:
                theme.apply(stdscr)
            except Exception:
                pass
        stdscr.erase()
        _header(stdscr, tabs, theme_name, paused)
        page = tabs.selected if tabs else 0
        if page == 0:
            _dashboard(stdscr, data)
        elif page == 1:
            _models(stdscr, data)
        elif page == 2:
            _health(stdscr, data)
        elif page == 3:
            _knowledge(stdscr, data)
        else:
            _tools(stdscr, data)
        h, w = stdscr.getmaxyx()
        _text(
            stdscr,
            h - 2,
            2,
            "1-5 tabs  ←/→ tabs  R refresh  P pause  T theme  Q quit",
            w - 4,
        )
        _text(
            stdscr,
            h - 1,
            2,
            f"Loom: {_status(data)}   poll={data.get('at', '--:--:--')}",
            w - 4,
            curses.A_BOLD,
        )
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        if key in (ord("p"), ord("P")):
            paused = not paused
        elif key in (ord("r"), ord("R")):
            last_poll = 0
        elif key in (ord("t"), ord("T")) and Dropdown and Option:
            selected = Dropdown(
                [Option(x, x) for x in THEMES],
                THEMES.index(theme_name) if theme_name in THEMES else 0,
            )
            choice = selected.choose(stdscr, 6, 2, min(60, w - 4), "Theme")
            if choice:
                theme_name = choice
        elif tabs:
            tabs.handle(key)


def main() -> None:
    curses.wrapper(_run)


if __name__ == "__main__":
    main()
