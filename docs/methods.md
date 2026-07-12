# Methods

## Rodent A/B testing — differential expression

Counts arrive from NASA OSDR as RSEM *expected* counts, which are fractional: a
read mapping ambiguously across isoforms is split between them. The
negative-binomial model underneath DESeq2 is defined on integers, so counts are
rounded (half away from zero) before fitting. That step is mandatory in the code
path, not a caller option.

Differential expression is **DESeq2** (via pydeseq2): median-of-ratios size
factors, empirical-Bayes dispersion shrinkage toward a fitted mean-dispersion
trend, Wald test on the flight coefficient, Benjamini–Hochberg FDR. The contrast
is flight over ground, so positive log2FC means higher expression in spaceflight.

The repo also contains a hand-rolled negative-binomial GLM
(`src/abtest/rnaseq.py`). It does **not** serve the API. It is an independent
cross-check, and it earned its keep by exposing two dispersion bugs: estimating
dispersion from *total* variance folds the flight-vs-ground effect into the
dispersion, so a gene that genuinely responds to flight inflates its own
dispersion and suppresses its own significance; and estimating it from *raw*
counts double-counts library size, which the model's offset already handles.
Together those drove one dataset to zero significant genes where a plain t-test
on the same matrix found 667.

The two models agree on gene *ranking* and disagree on the extremity of very
small p-values — which is exactly what dispersion shrinkage is for, and why
DESeq2 is what the API serves.

### Limits

n = 6 per group. Fold changes for low-expression genes are unreliable regardless
of FDR. Genes with a null adjusted p-value were dropped by DESeq2's independent
filtering and are reported as null, never as zero or as a passing result.

---

## Inspiration4 forecasting — model comparison

### Sample size, stated plainly

The forecasting module runs on the Inspiration4 **complete blood count** panel:
**4 crew members, 7 timepoints, 20 analytes**. In the primary `crew=mean` mode
that is a series of **seven points**. Under leave-one-out, each model is fitted
on **six**.

This is far below the regime Prophet, ARIMA and LightGBM were designed for. The
model comparison in this project **demonstrates methodology; it is not a clinical
claim.** No conclusion about human physiology in spaceflight should be drawn from
which model wins a LOO contest on seven points, and nothing here is a basis for
any medical or operational decision. It is held to the same honesty standard as
the DESeq2 dispersion caveat above: the number is reported, and so is the reason
not to over-read it.

The CBC panel is used because it is the **only** Inspiration4 modality with
post-return recovery timepoints (R+45, R+82, R+194). The I4 transcriptomics stops
at R+1 — a single post-flight point, which cannot support a recovery trajectory
at all. See `docs/DATA_NOTES.md`.

### The time axis

Every model is fitted on **mission day**, produced by
`src.data.timepoints.to_mission_day`, never on the raw `L-92` / `R+1` labels.
`L-` is measured from launch and `R+` from *return*, so on a launch-anchored axis
(launch = day 0, splashdown = day 3) `R+1` is day **4**, not day 1. Fitting on
label order would silently collapse the flight out of the timeline and treat every
gap as equal. `check_training_frame` rejects raw labels with an error, and a test
pins this.

The real spacing is deeply irregular: days -92, -44, -3, 4, 48, 85, 197, so
consecutive gaps run 48, 41, 7, 44, 37, 112 — a 16x spread.

### Why leave-one-out instead of a train/test split

With 7 timepoints, a conventional split is not an evaluation. Holding out the last
two leaves 5 points to fit and 2 to score; a single noisy observation then swings
the MAE by a large fraction, and the "test set" would be entirely the recovery
tail, so the score would say nothing about how a model handles the pre-flight
baseline or the flight response.

Leave-one-out uses all 7 points as test points, one at a time, fitting on the
other 6. Every observation contributes to the score exactly once — the most
evaluation signal 7 points can support. Folds that fail to fit are recorded as
failures, not silently dropped, so a model that only converges on the easy folds
does not get to look good on them alone.

**What LOO here does not do.** Holding out an *interior* timepoint and fitting on
points that come after it lets the model see the future. That is legitimate for
asking "can this model describe the shape of this series?", which is the question
being asked. It is *not* the same as "could this model have predicted the next
draw?". So the LOO scores compare **interpolation of the observed trajectory**,
and they do **not** validate the what-if extrapolation, which is reported
separately.

### The three models, and what each one's numbers are worth

**Prophet.** Fitted on true calendar dates anchored at the real launch
(2021-09-16), so it respects the actual spacing. All seasonalities are off: with 7
points over ~10 months there is no weekly or yearly cycle to recover, and leaving
them on would fit seasonal wiggles to noise. Changepoints are disabled for the
same reason. Produces a genuine predictive interval.

**ARIMA.** The weakest-justified of the three here, and the reason is structural:
**ARIMA assumes equally-spaced observations, and these are not**. The wrapper is
explicit about what it actually fits — `SARIMAX(y, exog=mission_day,
order=(1,0,0), trend='c')`, a linear trend in real mission day (which respects
spacing) plus an AR(1) term on the residuals (which does not). Stationarity is
enforced: with it off and only 5–6 points, the optimiser fits an explosive AR
(phi = 1.42 was observed), which has no stationary level and produced a
prediction of −4.7 for a hemoglobin series that lives at 14.

**LightGBM.** No native time axis, so time is handed to it as features: mission
day, plus a one-hot mission phase (preflight / inflight / recovery). **No lag
features** — with six training rows a lag would cost another row, and a lag across
a 112-day gap does not mean what a lag across a 7-day gap means. At this n, lags
would encode irregular spacing as if it were autocorrelation. This is a deliberate
omission.

LightGBM has two hard limits that the API reports rather than hides:

1. **No uncertainty.** It is a point regressor. `yhat_lower` / `yhat_upper` are
   `null`, not a band manufactured from residual spread. A fabricated interval is
   worse than none — it looks like information and is not.
2. **It cannot extrapolate.** Gradient-boosted trees return a constant outside
   their training range — the boundary leaf. Asked for a day past R+194, LightGBM
   returns a flat line, not a trend. The what-if response flags this explicitly.

### Reading "best model" correctly

`best_by_mae` ranks models by lowest leave-one-out MAE. It means **best
interpolator of the seven observed points** — not best forecaster.

LightGBM frequently wins that score while being the only model that cannot
extrapolate at all. When the winner is a model with no predictive interval, the
response carries `best_by_mae_warning` saying so. Treating `best_by_mae` as
"the model to trust for the what-if" would be exactly backwards.
