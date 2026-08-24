from loom_ai.clients import tui


def test_tui_is_headless_importable():
    assert callable(tui.main)
    assert tui._status({"health": {"status": "ok"}}) == "READY"
    assert tui._status({"health": {"error": "down"}}) == "OFFLINE"


def test_knowledge_count():
    assert tui._count({"documents": 12}, ("documents", "count")) == 12
    assert tui._count({}, ("documents", "count")) == "available"
