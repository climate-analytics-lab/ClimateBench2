# Running the tests

The tests need ClimateEval importable. The simplest way is the ClimateEval
pixi environment with this repo on `PYTHONPATH`:

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

Pure-function tests (scoring, gate machinery) skip nothing; suite integration
tests `importorskip("climateeval")`.
