"""Optional Loom operator TUI.

The TUI is presentation only. Loom core and the HTTP API remain headless.
"""
from __future__ import annotations
import asyncio, curses, os
from . import get_client

def _theme():
    try:
        from curses_themes import ThemeManager
        return ThemeManager.load(os.environ.get("FLOSSWARE_TUI_THEME", "dark"))
    except Exception:
        return None

async def _snapshot():
    client = await get_client()
    result = {"url": getattr(client, "base_url", os.environ.get("LOOM_URL", "http://127.0.0.1:5000"))}
    try: result["health"] = await client.health()
    except Exception as exc: result["health_error"] = str(exc)
    try: result["models"] = await client.list_models()
    except Exception: result["models"] = []
    return result

def main() -> None:
    def app(stdscr):
        curses.curs_set(0); stdscr.keypad(True); _theme()
        while True:
            data = asyncio.run(_snapshot()); stdscr.erase(); h,w=stdscr.getmaxyx()
            lines=["="*64," FlossWare Loom | Operator TUI","="*64,
                   f" Server: {data['url']}",f" Models: {len(data.get('models', []))} discovered", "",
                   "  [1] Dashboard", "  [2] Models", "  [3] Health", "  [R] Refresh", "  [Q] Quit"]
            for i,line in enumerate(lines[:h-1]): stdscr.addnstr(i+1,2,line,max(1,w-4))
            stdscr.refresh(); key=stdscr.getch()
            if key in (ord('q'),ord('Q'),27): return
            if key in (ord('r'),ord('R')): continue
    curses.wrapper(app)

if __name__ == "__main__": main()
