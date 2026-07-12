export default function Methods() {
  return (
    <>
      <div className="panel">
        <h2 style={{ fontSize: 15, marginTop: 0 }}>A/B testing — how the numbers are made</h2>
        <p style={{ fontSize: 14 }}>
          Counts come from NASA OSDR as RSEM <em>expected</em> counts, which are
          fractional: a read mapping ambiguously across isoforms is split between them.
          The negative-binomial model underneath DESeq2 is defined on integers, so counts
          are rounded (half away from zero) before the fit. That step is mandatory in the
          code path, not a caller option.
        </p>
        <p style={{ fontSize: 14 }}>
          Differential expression is <strong>DESeq2</strong> (via pydeseq2): median-of-ratios
          size factors, empirical-Bayes dispersion shrinkage toward a fitted
          mean-dispersion trend, Wald test on the flight coefficient, and
          Benjamini–Hochberg FDR. The contrast is flight over ground, so a positive
          log2FC means higher expression in spaceflight.
        </p>
      </div>

      <div className="panel">
        <h2 style={{ fontSize: 15, marginTop: 0 }}>Why there is a second, unused model</h2>
        <p style={{ fontSize: 14 }}>
          The repo also contains a hand-rolled negative-binomial GLM
          (<code>src/abtest/rnaseq.py</code>). It does <strong>not</strong> serve this
          site. It is kept as an independent cross-check, and it earned its place: it
          exposed two dispersion bugs during development. Estimating dispersion from
          total variance folds the flight-vs-ground effect itself into the dispersion, so
          a gene that genuinely responds to flight inflates its own dispersion and
          suppresses its own significance; and estimating it from raw counts
          double-counts library size, which the model's offset already handles.
        </p>
        <p style={{ fontSize: 14 }}>
          Together those two errors drove one dataset to <em>zero</em> significant genes
          where a plain t-test on the same matrix found 667. The two models now agree on
          gene <em>ranking</em>. They disagree on the extremity of very small p-values,
          which is exactly what dispersion shrinkage is for — and why DESeq2, not the
          hand-rolled model, is what you are looking at.
        </p>
      </div>

      <div className="panel">
        <h2 style={{ fontSize: 15, marginTop: 0 }}>Known limits</h2>
        <ul style={{ fontSize: 14, paddingLeft: 20 }}>
          <li>
            n = 6 per group. Fold changes for low-expression genes are unreliable
            regardless of FDR; sort by base mean before believing a large log2FC.
          </li>
          <li>
            Genes with a null adjusted p-value were dropped by DESeq2's independent
            filtering. They are shown as “—”, never as zero or as a passing result.
          </li>
          <li>
            Per-astronaut BMD and VO2max are not public at usable resolution. They are
            not stubbed, faked, or approximated anywhere in this project.
          </li>
        </ul>
      </div>
    </>
  )
}
