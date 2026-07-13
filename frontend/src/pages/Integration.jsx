import { useEffect, useMemo, useState } from 'react'
import { getIntegrate, getStudies } from '../api'

// Three tiers of trust, and the colours encode them. This is the whole point of
// the page: a 1:1 ortholog and a many-to-many ortholog must not look alike.
const CARDINALITY = {
  one_to_one: {
    label: 'one-to-one',
    tier: 'clean',
    color: '#4ec9a0',
    blurb: 'Unambiguous. One mouse gene, one human gene.',
  },
  one_to_many: {
    label: 'one-to-many',
    tier: 'ambiguous',
    color: '#d8b968',
    blurb: 'One mouse gene splits across several human genes.',
  },
  many_to_one: {
    label: 'many-to-one',
    tier: 'ambiguous',
    color: '#d89a68',
    blurb: 'Several mouse genes collapse onto the same human gene.',
  },
  many_to_many: {
    label: 'many-to-many',
    tier: 'ambiguous',
    color: '#d87c8a',
    blurb: 'Ambiguous in both directions. Read the mapping before trusting it.',
  },
  no_ortholog: {
    label: 'no ortholog',
    tier: 'unmappable',
    color: '#6b7688',
    blurb: 'No human counterpart in MGI. Not mappable — not "not significant".',
  },
}

const TIER_NOTE = {
  clean: 'clean',
  ambiguous: 'ambiguous — read the mapping before trusting it',
  unmappable: 'not mappable',
}

const ORDER = ['one_to_one', 'one_to_many', 'many_to_one', 'many_to_many', 'no_ortholog']

const COLUMNS = [
  { key: 'mouse_symbol', label: 'Mouse gene', numeric: false },
  { key: 'ensembl_id', label: 'ENSMUSG', numeric: false },
  { key: 'log2fc', label: 'log2FC', numeric: true },
  { key: 'padj', label: 'padj', numeric: true },
  { key: 'cardinality', label: 'Ortholog mapping', numeric: false },
  { key: 'n_human', label: 'Human genes', numeric: true },
]

const PAGE_SIZE = 100

export default function Integration() {
  const [studies, setStudies] = useState([])
  const [accession, setAccession] = useState('OSD-104')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [sortKey, setSortKey] = useState('padj')
  const [ascending, setAscending] = useState(true)
  const [query, setQuery] = useState('')
  const [tierFilter, setTierFilter] = useState('all')

  useEffect(() => {
    getStudies()
      .then((all) => setStudies(all.filter((s) => s.module === 'abtest')))
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getIntegrate(accession)
      .then((result) => !cancelled && setData(result))
      .catch((e) => !cancelled && setError(e.response?.data?.detail ?? e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [accession])

  const rows = useMemo(() => {
    if (!data) return []
    let filtered = data.genes

    if (tierFilter !== 'all') {
      filtered = filtered.filter(
        (g) => CARDINALITY[g.cardinality]?.tier === tierFilter,
      )
    }
    if (query.trim()) {
      const needle = query.trim().toLowerCase()
      filtered = filtered.filter(
        (g) =>
          (g.mouse_symbol ?? '').toLowerCase().includes(needle) ||
          g.ensembl_id.toLowerCase().includes(needle) ||
          (g.human_symbols ?? []).some((h) => h.toLowerCase().includes(needle)),
      )
    }

    return [...filtered].sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]
      // Nulls last in both directions — a null is "no result", not "best result".
      if (left === null && right === null) return 0
      if (left === null || left === undefined) return 1
      if (right === null || right === undefined) return -1
      if (typeof left === 'string') {
        return ascending ? left.localeCompare(right) : right.localeCompare(left)
      }
      return ascending ? left - right : right - left
    })
  }, [data, sortKey, ascending, query, tierFilter])

  const shown = rows.slice(0, PAGE_SIZE)

  function toggleSort(key) {
    if (key === sortKey) setAscending(!ascending)
    else {
      setSortKey(key)
      setAscending(key === 'padj')
    }
  }

  return (
    <>
      {/* Non-dismissible, first thing in the DOM, before the controls and the
          table. The framing has to land before any number does. */}
      <div
        data-testid="not-statistical-banner"
        style={{
          background: '#2a2113',
          border: '1px solid #6b5424',
          borderLeft: '4px solid #d8b968',
          borderRadius: 8,
          padding: '16px 18px',
          marginBottom: 20,
          color: '#f0d9a0',
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 8 }}>
          This is an evidence table, not a statistical integration.
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>
          Nothing on this page computes a correlation, enrichment, or hypothesis test
          linking rodent genes to human trajectories — and none could be computed
          honestly. The rodent data is mouse <strong>skeletal muscle</strong> (soleus,
          tibialis anterior); the Inspiration4 CBC panel is human{' '}
          <strong>whole blood</strong>. Those are not measurements of the same system.
          Add to that different species, different missions (RR-1 flew ~30+ days;
          Inspiration4 flew 3), and different measurement types — a DE gene is not a CBC
          analyte, and there is no row on which to join them.
          <div style={{ marginTop: 8 }}>
            What follows is the ortholog status of the rodent hits, shown{' '}
            <em>beside</em> what each blood analyte tracks, for a human to reason about.
            No number here asserts that a rodent gene explains a human trajectory.
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="controls">
          <div>
            <label htmlFor="accession">Rodent dataset</label>
            <select
              id="accession"
              value={accession}
              onChange={(e) => setAccession(e.target.value)}
            >
              {(studies.length ? studies : [{ accession: 'OSD-104', tissue: '' }]).map(
                (s) => (
                  <option key={s.accession} value={s.accession}>
                    {s.accession} {s.tissue ? `— ${s.tissue}` : ''}
                  </option>
                ),
              )}
            </select>
          </div>
          {loading && <span className="muted">Loading…</span>}
          {data && !loading && (
            <span className="muted" style={{ fontSize: 13 }}>
              {data.n_genes.toLocaleString()} significant genes (FDR &lt;{' '}
              {data.fdr_cutoff}) · orthology from MGI
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="panel error">
          <strong>Request failed.</strong> {error}
        </div>
      )}

      {data && !loading && (
        <>
          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 4px' }}>Ortholog mapping</h2>
            <p className="note" style={{ marginTop: 0, marginBottom: 16 }}>
              Mouse–human orthology is a many-to-many graph, not a lookup table. Every
              gene is tagged; none is silently joined and{' '}
              <strong>none is dropped</strong> — a gene that vanished from this table
              would read as “not significant” rather than “not mappable”, which is a
              different and much worse claim.
            </p>

            <div
              data-testid="cardinality-cards"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 12,
              }}
            >
              {ORDER.map((key) => {
                const meta = CARDINALITY[key]
                const count = data.orthology.cardinality[key] ?? 0
                return (
                  <div
                    key={key}
                    data-testid={`card-${key}`}
                    style={{
                      border: '1px solid var(--border)',
                      borderTop: `3px solid ${meta.color}`,
                      borderRadius: 8,
                      padding: 14,
                    }}
                  >
                    <div
                      style={{ fontSize: 24, fontWeight: 700, color: meta.color }}
                      data-testid={`count-${key}`}
                    >
                      {count.toLocaleString()}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>
                      {meta.label}
                    </div>
                    <div className="note" style={{ marginTop: 6 }}>
                      {meta.blurb}
                    </div>
                  </div>
                )
              })}
            </div>

            <div className="note" style={{ marginTop: 14 }}>
              <strong>{data.orthology.n_unambiguous.toLocaleString()}</strong> gene(s)
              have an unambiguous human counterpart.{' '}
              <strong>{data.orthology.n_ambiguous.toLocaleString()}</strong> map
              ambiguously and{' '}
              <strong>{data.orthology.n_no_ortholog.toLocaleString()}</strong> have no
              human ortholog at all. Source: {data.orthology.source}
            </div>
          </div>

          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 14px' }}>
              Rodent DE genes and their human orthologs
            </h2>

            <div className="controls" style={{ marginBottom: 14 }}>
              <input
                type="search"
                placeholder="Filter by mouse gene, ENSMUSG, or human symbol…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ minWidth: 300 }}
              />
              <div>
                <label htmlFor="tier">Show</label>
                <select
                  id="tier"
                  value={tierFilter}
                  onChange={(e) => setTierFilter(e.target.value)}
                >
                  <option value="all">all genes</option>
                  <option value="clean">clean (1:1 only)</option>
                  <option value="ambiguous">ambiguous mappings</option>
                  <option value="unmappable">not mappable</option>
                </select>
              </div>
            </div>

            <table>
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} onClick={() => toggleSort(c.key)}>
                      {c.label}
                      {sortKey === c.key ? (ascending ? ' ↑' : ' ↓') : ''}
                    </th>
                  ))}
                  <th style={{ cursor: 'default' }}>Human ortholog(s)</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((gene) => {
                  const meta = CARDINALITY[gene.cardinality] ?? CARDINALITY.no_ortholog
                  return (
                    <tr
                      key={`${gene.ensembl_id}:${gene.mgi_id ?? 'none'}`}
                      data-testid={`row-${gene.cardinality}`}
                      data-tier={meta.tier}
                    >
                      <td
                        className="gene"
                        style={{
                          // The visual marker: a coloured bar per row, so tier is
                          // readable at a glance without parsing the badge text.
                          borderLeft: `3px solid ${meta.color}`,
                          paddingLeft: 8,
                          color: gene.mouse_symbol ? 'var(--text)' : 'var(--muted)',
                        }}
                      >
                        {gene.mouse_symbol ?? '—'}
                      </td>
                      <td className="gene">{gene.ensembl_id}</td>
                      <td className={gene.log2fc > 0 ? 'up' : 'down'}>
                        {gene.log2fc.toFixed(3)}
                      </td>
                      <td>{gene.padj === null ? '—' : gene.padj.toExponential(2)}</td>
                      <td>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: 999,
                            fontSize: 11,
                            fontWeight: 600,
                            color: meta.color,
                            border: `1px solid ${meta.color}55`,
                            background: `${meta.color}14`,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {meta.label}
                        </span>
                        <div
                          className="note"
                          style={{ marginTop: 3, fontSize: 11 }}
                          data-testid={`tier-note-${gene.cardinality}`}
                        >
                          {TIER_NOTE[meta.tier]}
                        </div>
                      </td>
                      <td>{gene.n_human}</td>
                      <td className="gene">
                        {gene.human_symbols.length ? (
                          gene.human_symbols.join(', ')
                        ) : (
                          <span className="muted">
                            none — {gene.reason ?? 'no human counterpart'}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {shown.length === 0 && <p className="note">No genes match.</p>}

            <div className="note">
              Showing {shown.length.toLocaleString()} of {rows.length.toLocaleString()}{' '}
              rows
              {rows.length > PAGE_SIZE &&
                ` (first ${PAGE_SIZE} — narrow the filter to see more)`}
              . {data.truncated ? data.truncation_note : ''}
            </div>
          </div>

          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 4px' }}>
              What the blood panel actually tracks
            </h2>
            <p className="note" style={{ marginTop: 0, marginBottom: 14 }}>
              {data.cbc_context.note}
            </p>
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'default' }}>Analyte</th>
                  <th style={{ cursor: 'default' }}>Physiological system</th>
                  <th style={{ cursor: 'default' }}>Timepoints</th>
                </tr>
              </thead>
              <tbody>
                {data.cbc_context.analytes.map((a) => (
                  <tr key={a.analyte}>
                    <td>{a.analyte.replace(/_/g, ' ')}</td>
                    <td className="muted">{a.system}</td>
                    <td>{a.n_timepoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h2 style={{ fontSize: 15, margin: '0 0 10px' }}>Caveats</h2>
            <ul style={{ fontSize: 13, paddingLeft: 20, margin: 0, lineHeight: 1.7 }}>
              {data.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </>
      )}
    </>
  )
}
