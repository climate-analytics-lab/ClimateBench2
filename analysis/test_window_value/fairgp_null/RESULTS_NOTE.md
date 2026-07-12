# FaIRGP test-window experiment — results (honest summary)

**Question.** Does conditioning FaIRGP on the 2015–2025 test window narrow the posterior
of the 2050 GMST projection (SSP2-4.5, NorESM2 truth), relative to training on ≤2014 only?

**Setup.** FaIRGP built from the authors' code (their exact FaIR mean + physically-structured
covariance), fitted by marginal likelihood on NorESM2 historical residuals. Sanity: hist-only
SSP2-4.5 GMST posterior-mean RMSE = 0.124 K, internal-variability σ ≈ 0.10 K — i.e. a *good,
non-degenerate* fit, consistent with Bouabid et al. (2024).

**Result.** The 2015–2025 window strongly narrows *near-term* projections but its information
**decays to ~0 by 2050**:

| horizon | variance reduction from test window (FaIRGP) | (plain GP) | FaIRGP σ trained-to-2014 → +window |
|---|---|---|---|
| 2026 | 80% | 91% | 0.20 → 0.09 K |
| 2030 | 49% | 50% | 0.21 → 0.15 K |
| 2035 | 16% | 15% | 0.21 → 0.19 K |
| 2040 | 3% | 3% | 0.21 → 0.20 K |
| **2050** | **0.1%** | **0.1%** | **0.20 → 0.20 K** |

**The 2050 posterior is essentially unchanged by the test window**, and FaIRGP tracks the
physics-free plain GP almost exactly — the physical prior does **not** carry the test-window
information out to 2050.

**Why (the modelling insight).** Two structural reasons, both real:
1. FaIRGP's uncertainty is *forcing-trajectory* uncertainty. The EBM response parameters
   (d, q — i.e. the sensitivity/timescales) are **fixed**; only the forcing is stochastic, with a
   covariance that is a Matérn kernel over *cumulative-emission distance*. So 2050 (SSP2-4.5,
   far in emission-space from 2015–2025) is nearly decorrelated from the recent window — the
   forcing GP "reverts to the FaIR prior" out there. FaIRGP therefore cannot express the
   mechanism the intuition needs: *recent warming pinning the climate sensitivity, which then
   sets 2050*. Sensitivity isn't uncertain in the model, so recent data can't constrain 2050
   through it.
2. Near-term GMST is internal-variability-dominated (Hawkins–Sutton; the authors' Fig 15), so
   the 11 window points are mostly noise about the forced response — low signal to propagate.

**Bottom line.** For GMST via FaIRGP, the test window discriminates *near-term* projections
(≤~2035), not the 2050 target. This is the third consistent signal (with the CMIP6 trend
result, r=0.48 / CV R²=0.11) that global-mean temperature alone is a weak vehicle for the
"test period discriminates 2050" claim. The right instrument for that claim is a setting with
*sensitivity* uncertainty (the CMIP6 inter-model spread), where recent warming does constrain
2050 — but only moderately.
