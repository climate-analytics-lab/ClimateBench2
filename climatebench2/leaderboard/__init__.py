"""ClimateBench2 leaderboard — turns ClimateEval result databases into scores.

Phase 0: a scores *table* built from the deterministic metrics ClimateEval
emits (``weighted_rmse``/``weighted_pearsonr``/``weighted_emd``), reusing
ClimateEval's own normalisation so numbers agree between the two tools.

Phase 6 (delineation plan §6) replaces this with the real thing: a standalone
static HTML page showing the Tier I pass/fail gate, Tier II/III probabilistic
scores, and every score relative to the three baselines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd


def build_scores_table(db_paths: list[Path]) -> pd.DataFrame:
    """Build a per-model scores table from ClimateEval ``.ddb`` databases.

    Returns a DataFrame with columns ``Rank``, ``data_id`` (model),
    ``Overall Score`` (0–1, higher is better), aggregated across every
    diagnostic/variable in the given databases.
    """
    import pandas as pd

    # Private-module reuse is deliberate and safe: climateeval is pinned by
    # commit in pyproject.toml (delineation plan §8.4).
    from climateeval.report._db import read_database
    from climateeval.report._leaderboard import build_leaderboard_data

    all_metrics: dict[str, dict[str, pd.DataFrame]] = {}
    for db_path in db_paths:
        tier_label = db_path.stem
        diags = read_database(db_path)
        all_metrics[tier_label] = {
            diag_name: tables["metrics"]
            for diag_name, tables in diags.items()
            if "metrics" in tables
        }

    summary, _detail = build_leaderboard_data(all_metrics)
    return summary
