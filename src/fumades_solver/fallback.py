"""Compatibility entry point for the deterministic fallback engine.

V1.1.1 keeps the CLI option but routes it through the same five-minute CP-SAT
model with a single worker, which is deterministic and preserves all hard
constraints.
"""

from __future__ import annotations

from .model import solve


def solve_fallback(*args, **kwargs):
    kwargs["engine"] = "fallback"
    kwargs["num_workers"] = 1
    return solve(*args, **kwargs)
