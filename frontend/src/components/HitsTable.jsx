import { useMemo, useState } from 'react'

const COLUMNS = [
  { key: 'gene', label: 'Gene', numeric: false },
  { key: 'base_mean', label: 'Base mean', numeric: true, format: (v) => v.toFixed(1) },
  { key: 'log2fc', label: 'log2FC', numeric: true, format: (v) => v.toFixed(3) },
  { key: 'pvalue', label: 'p-value', numeric: true, format: (v) => v.toExponential(2) },
  { key: 'padj', label: 'padj (FDR)', numeric: true, format: (v) => v.toExponential(2) },
]

const PAGE_SIZE = 100

export default function HitsTable({ results }) {
  const [sortKey, setSortKey] = useState('padj')
  const [ascending, setAscending] = useState(true)
  const [query, setQuery] = useState('')
  const [significantOnly, setSignificantOnly] = useState(true)

  const rows = useMemo(() => {
    let filtered = results
    if (significantOnly) {
      filtered = filtered.filter((g) => g.padj !== null && g.padj < 0.05)
    }
    if (query.trim()) {
      const needle = query.trim().toLowerCase()
      filtered = filtered.filter((g) => g.gene.toLowerCase().includes(needle))
    }

    const sorted = [...filtered].sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]

      // Nulls always sort last, whichever direction — a null padj is "no result",
      // not "the best result", and letting it float to the top would be a lie.
      if (left === null && right === null) return 0
      if (left === null) return 1
      if (right === null) return -1

      if (typeof left === 'string') {
        return ascending ? left.localeCompare(right) : right.localeCompare(left)
      }
      return ascending ? left - right : right - left
    })
    return sorted
  }, [results, sortKey, ascending, query, significantOnly])

  const shown = rows.slice(0, PAGE_SIZE)

  function toggleSort(key) {
    if (key === sortKey) {
      setAscending(!ascending)
    } else {
      setSortKey(key)
      setAscending(key === 'padj' || key === 'pvalue')
    }
  }

  return (
    <>
      <div className="controls" style={{ marginBottom: 14 }}>
        <input
          type="search"
          placeholder="Filter by gene ID…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={significantOnly}
            onChange={(event) => setSignificantOnly(event.target.checked)}
          />
          Significant only (FDR &lt; 0.05)
        </label>
      </div>

      <table>
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <th key={column.key} onClick={() => toggleSort(column.key)}>
                {column.label}
                {sortKey === column.key ? (ascending ? ' ↑' : ' ↓') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((gene) => (
            <tr key={gene.gene}>
              <td className="gene">{gene.gene}</td>
              <td>{gene.base_mean.toFixed(1)}</td>
              <td className={gene.log2fc > 0 ? 'up' : 'down'}>
                {gene.log2fc.toFixed(3)}
              </td>
              <td>{gene.pvalue === null ? '—' : gene.pvalue.toExponential(2)}</td>
              <td>{gene.padj === null ? '—' : gene.padj.toExponential(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {shown.length === 0 && <p className="note">No genes match.</p>}

      <div className="note">
        Showing {shown.length.toLocaleString()} of {rows.length.toLocaleString()} rows
        {rows.length > PAGE_SIZE && ` (first ${PAGE_SIZE} — narrow the filter to see more)`}.
        Positive log2FC means higher expression in flight.
      </div>
    </>
  )
}
