"""Access to the ClimateBench v2 protocol thresholds.

``thresholds.yml`` is the single source of truth for every pass/fail bound in
the protocol (see ``docs/metrics_reference.md``). Diagnostics must read their
bounds through :func:`get_threshold` and never hard-code them.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import Any

import yaml


@cache
def load_thresholds() -> dict[str, Any]:
    """Load and cache the packaged ``thresholds.yml``."""
    text = resources.files("climatebench2").joinpath("thresholds.yml").read_text()
    return yaml.safe_load(text)


def get_threshold(path: str) -> Any:
    """Return a threshold by dotted path, e.g. ``"tier1.ecs.range"``.

    Raises
    ------
    KeyError
        If the path does not exist in ``thresholds.yml`` — a protocol bug, so
        it fails loudly rather than defaulting.
    """
    node: Any = load_thresholds()
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            msg = f"Threshold '{path}' not found in thresholds.yml (missing '{key}')"
            raise KeyError(msg)
        node = node[key]
    return node
