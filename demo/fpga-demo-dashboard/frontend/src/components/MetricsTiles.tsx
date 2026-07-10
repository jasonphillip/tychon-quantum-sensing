import { useEffect, useState } from 'react'

interface Metrics {
  scalar_residual?: {
    reduction_pct: number
    val_mae_reduction_pct: number
    sweep_mae_reduction_pct: number
    adev_tau_2700_reduction_pct_direct: number
    int8_note: string
    source: string
    deployed_model: string
  }
  figures?: { name: string; caption: string }[]
}

export function MetricsTiles() {
  const [m, setM] = useState<Metrics | null>(null)
  useEffect(() => { fetch('/api/metrics').then((r) => r.json()).then(setM).catch(() => {}) }, [])

  if (!m?.scalar_residual) return <div className="panel"><h2>Metrics</h2><div className="kv">loading…</div></div>
  const s = m.scalar_residual
  const clampLimitedPotentialPct = 9.3
  const clampLimitedCapturedPct = Math.round((s.reduction_pct / clampLimitedPotentialPct) * 100)
  return (
    <div className="panel">
      <h2>Accuracy - safety-bounded AI assist</h2>
      <div className="metric-primary">
        <div className="metric-big">~{Math.round(s.reduction_pct)}%</div>
        <div>
          <div className="metric-title">simulated held-out improvement</div>
          <div className="metric-copy">
            Captures ~{clampLimitedCapturedPct}% of the improvement available under the current
            safety clamp. Conservative AI assist; deployment is safety-bounded and not real-NV
            validated yet.
          </div>
        </div>
      </div>
      <div className="footnote">
        Clamp-limited oracle ceiling: ~{clampLimitedPotentialPct}% MAE reduction at ±2.25 µT.
        Deployed model: {s.deployed_model}. Source: {s.source}
      </div>
      <details className="advanced">
        <summary>Detailed metrics and Allan plot</summary>
        <div className="tiles">
          <div className="tile"><div className="big">{s.reduction_pct}%</div><div className="cap">AIC-test MAE reduction</div></div>
          <div className="tile"><div className="big">{s.val_mae_reduction_pct}%</div><div className="cap">validation MAE reduction</div></div>
          <div className="tile"><div className="big">{s.adev_tau_2700_reduction_pct_direct}%</div><div className="cap">direct OADEV reduction</div></div>
        </div>
        <div className="kv" style={{ marginTop: 8 }}>
          heading sweep: {s.sweep_mae_reduction_pct}% · {s.int8_note}
        </div>
        {m.figures?.map((f) => (
          <figure key={f.name} style={{ margin: '12px 0 0' }}>
            <img src={'/api/figures/' + f.name} alt={f.caption}
                 style={{ width: '100%', borderRadius: 6, border: '1px solid var(--border)' }} />
            <figcaption className="footnote">{f.caption}</figcaption>
          </figure>
        ))}
      </details>
    </div>
  )
}
