export default function Integration() {
  return (
    <div className="panel">
      <h2 style={{ fontSize: 15, marginTop: 0 }}>Integration — not built yet</h2>
      <p style={{ fontSize: 14 }}>
        This page will cross-reference the rodent flight-vs-ground DE hits (OSD-104,
        OSD-105) against shifts in the human Inspiration4 data. It depends on the
        forecasting module, which does not exist yet.
      </p>
      <p className="note">
        Note the cross-species join is not trivial: the rodent hits are mouse ENSMUSG
        IDs and the human data is ENSG. Mapping requires orthologs, and that mapping is
        many-to-many — it will need to be an explicit, inspectable step rather than a
        silent merge.
      </p>
    </div>
  )
}
