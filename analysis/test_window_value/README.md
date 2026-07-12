# Test-window value under sensitivity + aerosol uncertainty (FaIR grid posterior)

The demonstration for ClimateBench v2's core claim, done the way it needs to be done:
with *climate sensitivity* uncertain. Bayesian grid-posterior version of the frequentist
subsampling in Watson-Parris (GRL 2025, doi:10.1029/2024GL111233 — check) / the
FaIR_simulations notebook; truth = NorESM2-LM (ClimateBench v1.0, historical + ssp245).

## Model
FaIR impulse-response GMST (NorESM2-tuned d, q from the FaIRGP repo), linear in forcing:
T(t; s, α) = s·[T_G(t) + α·T_A(t)], with s scaling the equilibrium response
(ECS = s·ECS₀, ECS₀ ≈ 2.45 K) and α scaling the aerosol forcing (time-shape from
FaIR/ClimateBench emissions; amplitude normalized so α = 1 gives −1.0 W/m² aerosol ERF
over 2005–2014, AR6-central). Uniform priors: ECS ∈ [1, 6.9] K, aerosol ERF ∈ [−2.5, 0].

## Constraints (Gaussian likelihoods, AR(1)-corrected IV sds from NorESM2 members)
- A ("trained to 2014"): 1995–2014 mean level + 1975–2014 trend.
- B ("+ test window"): A + 2015–2025 mean level + 2015–2025 trend.
Observations = a single NorESM2 realization (each of the 3 members in turn).

## Result
| obs member | D50 5–95% (A) | D50 5–95% (B) | var. reduction | window trend only | window level only |
|---|---|---|---|---|---|
| 1 | [0.89, 1.77] | [0.67, 1.27] | 54% | 13% | 49% |
| 2 | [0.40, 1.20] | [0.61, 1.23] | 42% | 12% | 38% |
| 3 | [0.43, 1.24] | [0.47, 1.06] | 47% | 4% | 47% |

Truth (NorESM2 forced 2050 change vs 1990–2020): **0.84 K** — inside every B interval.
ECS marginal narrows correspondingly (e.g. member 1: [2.7, 4.8] → [2.2, 3.5] K, around
NorESM2's 2.54 K).

**Mechanism.** To 2014 the record is degenerate: high-sensitivity/strong-aerosol and
low-sensitivity/weak-aerosol members fit equally well (panel a ridge), leaving the 2050
change spread over ~0.85 K. The 2015–2025 window breaks the degeneracy because (i) it
extends the record through a period of declining aerosol forcing, so the realized warming
is more purely sensitivity-driven, and (ii) it adds a decade of high-signal warming.

**On rate vs level.** Duncan's GRL constraint used the *rate* of recent warming (a ~20-yr
smoothed rate). Here, with an 11-yr window, the OLS trend within the window is
internal-variability-swamped (IV sd ≈ 0.3 K/decade; the 3 NorESM2 members give
−0.15/+0.14/+0.45!) and contributes only 4–13%. The window *mean level* — which,
referenced to the training-period level, is the *integrated* warming rate since 2014,
i.e. a far more IV-robust estimator of the same quantity — carries nearly all the
information (38–49%). So the GRL intuition survives intact; for short windows the level
is simply the better estimator of the recent rate.

**FaIRGP connection.** This does *not* fall out of FaIRGP as published: there the
response parameters (d, q) are fixed and only the forcing is stochastic, which is exactly
why the earlier FaIRGP experiment showed ~0% narrowing at 2050. Promoting q (sensitivity)
to a random variable inside FaIRGP — which the authors note is possible in their tuning
framework — would reproduce this behaviour natively; the grid posterior here is the
minimal Bayesian version of that extension.

## Caveats (state in any paper text)
GMST only; response timescales held fixed as sensitivity scales; statistics treated as
independent Gaussians; no volcanic forcing in the FaIR mean (present in NorESM2's
historical); single-realization observations (hence the member-to-member range above);
aerosol amplitude normalization is imposed, not emergent.

## Files
`sens_experiment.py` (self-contained; needs the FaIRGP repo + ClimateBench data),
`sens_testwindow.{png,pdf}`, `sens_results.npz`.
