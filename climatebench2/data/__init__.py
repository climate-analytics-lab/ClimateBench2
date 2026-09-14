"""Packaged protocol data tables (not model or observational data).

Anything a CB2 *score* needs that is neither a threshold nor a computation:
today only the annual effective-radiative-forcing series that drives the
two-layer EBM behind the pattern-scaling baseline
(``erf_ar6_ssp245.csv``, read by :func:`climatebench2.baselines.load_erf_series`).

Model output and observations never live here — they come from ClimateEval
DataSources (docs/climateeval_delineation_plan.md, the ownership test).
"""
