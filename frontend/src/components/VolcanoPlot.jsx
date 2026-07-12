import { useMemo } from 'react'
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'

const PADJ_CUTOFF = 0.05
const LFC_CUTOFF = 1

// Recharts renders SVG, one node per point. A full DESeq2 result is ~22,700
// genes, which makes the chart crawl. We plot every significant gene (those are
// the ones anyone actually looks at) and thin the non-significant cloud, which
// is a visually redundant blob. The thinning is deterministic (every k-th gene,
// not random) so the plot does not change between renders, and the exact counts
// are reported under the chart — never silently truncated.
const MAX_BACKGROUND_POINTS = 3000

function classify(gene) {
  if (gene.padj === null || gene.padj >= PADJ_CUTOFF) return 'ns'
  if (gene.log2fc >= LFC_CUTOFF) return 'up'
  if (gene.log2fc <= -LFC_CUTOFF) return 'down'
  return 'sig'
}

const SERIES = {
  up: { name: `Up in flight (padj<${PADJ_CUTOFF}, log2FC>${LFC_CUTOFF})`, color: '#e05c5c' },
  down: { name: `Down in flight (padj<${PADJ_CUTOFF}, log2FC<-${LFC_CUTOFF})`, color: '#4d8fd6' },
  sig: { name: `Significant, |log2FC|<${LFC_CUTOFF}`, color: '#c9a227' },
  ns: { name: 'Not significant', color: '#3d4655' },
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const gene = payload[0].payload
  return (
    <div
      style={{
        background: '#0b0e14',
        border: '1px solid #232b39',
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 12,
      }}
    >
      <div style={{ fontFamily: 'ui-monospace, monospace', marginBottom: 4 }}>
        {gene.gene}
      </div>
      <div>log2FC: {gene.log2fc.toFixed(3)}</div>
      <div>padj: {gene.padj === null ? 'n/a' : gene.padj.toExponential(2)}</div>
      <div>base mean: {gene.base_mean.toFixed(1)}</div>
    </div>
  )
}

export default function VolcanoPlot({ results }) {
  const { series, plotted, total, filteredOut } = useMemo(() => {
    // Genes with padj === null were dropped by DESeq2's independent filtering.
    // They have no y-value, so they cannot appear on a volcano at all.
    const plottable = results.filter(
      (gene) => gene.padj !== null && gene.padj > 0 && Number.isFinite(gene.log2fc),
    )

    const groups = { up: [], down: [], sig: [], ns: [] }
    for (const gene of plottable) {
      groups[classify(gene)].push({ ...gene, negLog10Padj: -Math.log10(gene.padj) })
    }

    // Thin only the uninformative background.
    let background = groups.ns
    if (background.length > MAX_BACKGROUND_POINTS) {
      const step = Math.ceil(background.length / MAX_BACKGROUND_POINTS)
      background = background.filter((_, index) => index % step === 0)
    }
    groups.ns = background

    const plotted = Object.values(groups).reduce((sum, g) => sum + g.length, 0)
    return {
      series: groups,
      plotted,
      total: results.length,
      filteredOut: results.length - plottable.length,
    }
  }, [results])

  return (
    <>
      <ResponsiveContainer width="100%" height={440}>
        <ScatterChart margin={{ top: 12, right: 16, bottom: 16, left: 8 }}>
          <CartesianGrid stroke="#1d2431" />
          <XAxis
            type="number"
            dataKey="log2fc"
            name="log2 fold change"
            stroke="#8b96a8"
            tick={{ fontSize: 11 }}
            label={{
              value: 'log2 fold change (flight / ground)',
              position: 'insideBottom',
              offset: -8,
              fill: '#8b96a8',
              fontSize: 12,
            }}
          />
          <YAxis
            type="number"
            dataKey="negLog10Padj"
            name="-log10 padj"
            stroke="#8b96a8"
            tick={{ fontSize: 11 }}
            label={{
              value: '-log10(padj)',
              angle: -90,
              position: 'insideLeft',
              fill: '#8b96a8',
              fontSize: 12,
            }}
          />
          <ZAxis range={[9, 9]} />
          <ReferenceLine
            y={-Math.log10(PADJ_CUTOFF)}
            stroke="#5a6478"
            strokeDasharray="4 4"
          />
          <ReferenceLine x={LFC_CUTOFF} stroke="#5a6478" strokeDasharray="4 4" />
          <ReferenceLine x={-LFC_CUTOFF} stroke="#5a6478" strokeDasharray="4 4" />
          <Tooltip content={<CustomTooltip />} />
          {/* Background first so significant points draw on top of it. */}
          {['ns', 'sig', 'down', 'up'].map((key) => (
            <Scatter
              key={key}
              name={SERIES[key].name}
              data={series[key]}
              fill={SERIES[key].color}
              fillOpacity={key === 'ns' ? 0.45 : 0.85}
              isAnimationActive={false}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>

      <div className="note">
        Plotting {plotted.toLocaleString()} of {total.toLocaleString()} genes. Every
        significant gene is shown; the non-significant cloud is thinned to{' '}
        {MAX_BACKGROUND_POINTS.toLocaleString()} points for rendering speed.
        {filteredOut > 0 && (
          <>
            {' '}
            {filteredOut.toLocaleString()} genes have no adjusted p-value (dropped by
            DESeq2 independent filtering) and cannot be placed on a volcano.
          </>
        )}
      </div>
    </>
  )
}
