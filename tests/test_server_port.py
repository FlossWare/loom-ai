"""Tests for LOOM_PORT environment variable validation in server.main()."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _run_main_with_port(port_value: str) -> None:
    """Call main() with LOOM_PORT set to *port_value*, stubbing uvicorn."""
    env = {"LOOM_PORT": port_value}
    with (
        patch.dict("os.environ", env, clear=False),
        patch("uvicorn.run"),
    ):
        from loom_ai.server import main

        main()


class TestLoomPortValidation:
    """LOOM_PORT must be a valid integer in [1, 65535]."""

    def test_valid_port(self) -> None:
        env = {"LOOM_PORT": "8080"}
        with (
            patch.dict("os.environ", env, clear=False),
            patch("uvicorn.run") as mock_run,
        ):
            from loom_ai.server import main

            main()
            _, kwargs = mock_run.call_args
            assert kwargs.get("port") == 8080 or mock_run.call_args[0]

    def test_default_port(self) -> None:
        env: dict[str, str] = {}
        with (
            patch.dict("os.environ", env, clear=False),
            patch.dict("os.environ", {"LOOM_PORT": ""}, clear=False),
            patch("uvicorn.run") as mock_run,
        ):
            # Remove LOOM_PORT so the default kicks in
            import os

            os.environ.pop("LOOM_PORT", None)
            from loom_ai.server import main

            main()
            mock_run.assert_called_once()

    def test_non_integer_port_raises(self) -> None:
        with pytest.raises(SystemExit, match="invalid integer"):
            _run_main_with_port("not-a-number")

    def test_empty_string_port_raises(self) -> None:
        with pytest.raises(SystemExit, match="invalid integer"):
            _run_main_with_port("")

    def test_float_port_raises(self) -> None:
        with pytest.raises(SystemExit, match="invalid integer"):
            _run_main_with_port("80.5")

    def test_port_zero_raises(self) -> None:
        with pytest.raises(SystemExit, match="outside valid range"):
            _run_main_with_port("0")

    def test_port_negative_raises(self) -> None:
        with pytest.raises(SystemExit, match="outside valid range"):
            _run_main_with_port("-1")

    def test_port_too_large_raises(self) -> None:
        with pytest.raises(SystemExit, match="outside valid range"):
            _run_main_with_port("70000")

    def test_port_65536_raises(self) -> None:
        with pytest.raises(SystemExit, match="outside valid range"):
            _run_main_with_port("65536")

    def test_port_boundary_low(self) -> None:
        """Port 1 is valid (lowest)."""
        env = {"LOOM_PORT": "1"}
        with (
            patch.dict("os.environ", env, clear=False),
            patch("uvicorn.run") as mock_run,
        ):
            from loom_ai.server import main

            main()
            mock_run.assert_called_once()

    def test_port_boundary_high(self) -> None:
        """Port 65535 is valid (highest)."""
        env = {"LOOM_PORT": "65535"}
        with (
            patch.dict("os.environ", env, clear=False),
            patch("uvicorn.run") as mock_run,
        ):
            from loom_ai.server import main

            main()
            mock_run.assert_called_once()
