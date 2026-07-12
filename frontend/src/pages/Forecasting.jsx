export default function Forecasting() {
  return (
    <div className="panel">
      <h2 style={{ fontSize: 15, marginTop: 0 }}>Forecasting — not built yet</h2>
      <p style={{ fontSize: 14 }}>
        This page will forecast Inspiration4 molecular trajectories across the mission
        timeline. The backend endpoint does not exist yet, so there is nothing real to
        show here — and a mocked chart would be worse than an empty page.
      </p>
      <p className="note">
        Planned target: the <strong>CBC clinical panel</strong> (4 crew × 7 timepoints ×
        20 analytes), not the RNA-seq. The I4 transcriptomics has exactly one post-return
        timepoint (R+1), so it cannot support a recovery trajectory — Prophet, ARIMA and
        LightGBM all need a post-flight curve that isn't in that data. The CBC panel is
        the only I4 modality carrying R+45, R+82 and R+194.
      </p>
    </div>
  )
}
