# Running the tests

**333 tests, all passing (2026-09-20).** They need ClimateEval
importable. The simplest way is the ClimateEval pixi environment with this repo
on `PYTHONPATH`:

```bash
cd /path/to/ClimateEval
PYTHONPATH=/path/to/ClimateBench2 pixi run --frozen \
    python -m pytest /path/to/ClimateBench2/tests -q
```

Or any environment where both `climateeval` and `climatebench2` are installed
(`pip install -e .` in each repo):

```bash
pytest tests/
```

Pure-function tests (scoring, physics, gate machinery, the leaderboard) skip
nothing; suite integration tests `importorskip("climateeval")`. No test touches
the network or reads real model output — every fixture is a synthetic cube, a
synthetic DuckDB or a numpy array, which is also the honest limit of what the
suite proves. Several of the newer tests are **regressions from the first real
runs** (a masked pressure level read as its 1e20 fill value, daily and monthly
fields paired by position rather than by date, a per-member duplicate row, an
EOF basis built on a masked reference): the bug is reproduced on synthetic
cubes, but it was found on CMIP6 output. See "What has run on real data" in
[`../docs/metrics_reference.md`](../docs/metrics_reference.md) for what the
real runs cover and what they do not.

`tests/test_suites.py` is the one that guards packaging: it builds every
diagnostic of **every** suite in `_cli.SUITE_REGISTRY` (not just the CLI
defaults) and checks that `thresholds.yml`, `suites/*.yml` and `data/*.csv` all
resolve through `importlib.resources`, so a missing `package-data` entry in
`pyproject.toml` fails here rather than after an install.

## Linting

```bash
cd /path/to/ClimateEval
pixi run --frozen ruff check /path/to/ClimateBench2/climatebench2 \
                             /path/to/ClimateBench2/tests
```

Note that this borrows **ClimateEval's** `ruff` configuration (CB2's
`pyproject.toml` declares none), and its `select = ["ALL"]` comes with
`per-file-ignores` keyed to paths under the ClimateEval root — which CB2's
paths do not match. The result is a large number of findings that would be
ignored under that config in its own repo (`S101` for `assert` in tests,
`D103` for undocumented test functions, and the `ANN*`/`E402` directives the
CB2 files carry `# noqa` for). Judge the run by the real-defect subset:

```bash
pixi run --frozen ruff check --select F,E9 <same paths>   # clean at d21be52
```
