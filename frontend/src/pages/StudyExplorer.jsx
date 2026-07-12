import { useEffect, useState } from 'react'
import { getStudies } from '../api'

const MODULE_LABEL = {
  abtest: 'A/B testing',
  de: 'Differential expression',
  forecast: 'Forecasting',
}

export default function StudyExplorer() {
  const [studies, setStudies] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="panel error">
        <strong>Could not load studies.</strong> {error}
      </div>
    )
  }

  return (
    <>
      <div className="panel">
        <h2 style={{ fontSize: 15, margin: '0 0 6px' }}>Datasets in use</h2>
        <p className="note" style={{ marginTop: 0 }}>
          Pulled live from NASA OSDR. Several plausible-looking accessions do not
          contain what their titles suggest — see <code>docs/DATA_NOTES.md</code>.
        </p>
      </div>

      {studies.map((study) => (
        <div className="panel" key={study.accession}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 12,
            }}
          >
            <h3 style={{ fontSize: 15, margin: 0 }}>
              <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                {study.accession}
              </span>{' '}
              <span className="muted" style={{ fontWeight: 400 }}>
                {study.label}
              </span>
            </h3>
            <span className="muted" style={{ fontSize: 12 }}>
              {MODULE_LABEL[study.module] ?? study.module}
            </span>
          </div>
          <div className="note">
            {study.organism} · {study.tissue} · {study.assay} · {study.design}
          </div>
          <p style={{ fontSize: 13, marginBottom: 0 }}>{study.notes}</p>
        </div>
      ))}
    </>
  )
}
