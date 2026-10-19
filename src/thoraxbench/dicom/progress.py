# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Optional bounded work counters shared by CLI and server-side study loading."""

from collections.abc import Callable

Progress = Callable[[str, int, int | None], None]


def emit_progress(
    progress: Progress | None, operation: str, completed: int, total: int | None
) -> None:
    """Report phase boundaries and every 25 completed units, without paths or estimates."""
    if progress is not None and (completed == 0 or completed % 25 == 0 or completed == total):
        progress(operation, completed, total)
