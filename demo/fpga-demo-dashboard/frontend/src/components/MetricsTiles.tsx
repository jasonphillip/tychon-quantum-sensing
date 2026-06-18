import { useEffect, useState } from 'react'

interface Metrics {
  scalar_residual?: {
    deployed_mae_uT: number; pid_baseline_mae_uT: number; reduction_pct: number
    coarse_stage_mae_uT: number; fine_stage_mae_uT: number
    bit_exact: boolean; rounding: string; epochs: number
  }
  figures?: { name: string; caption: string }[]
}

export function MetricsTiles() {
  const [m, setM] = useState<Metrics | null>(null)
  useEffect(() => { fetch('/api/metrics').then((r) => r.json()).then(setM).catch(() => {}) }, [])

  if (!m?.scalar_residual) return <div className="panel"><h2>Metrics</h2><div className="kv">loading…</div></div>
  const s = m.scalar_residual
  return (
    <div className="panel">
      <h2>Accuracy — scalar residual</h2>
      <div className="tiles">
        <div className="tile"><div className="big">{s.reduction_pct}%</div><div className="cap">better vs PID</div></div>
        <div className="tile"><div className="big">{s.deployed_mae_uT}</div><div className="cap">deployed MAE µT</div></div>
        <div className="tile"><div className="big">{s.pid_baseline_mae_uT}</div><div className="cap">PID-only MAE µT</div></div>
      </div>
      <div className="kv" style={{ marginTop: 8 }}>
        stage MAE: coarse {s.coarse_stage_mae_uT} / fine {s.fine_stage_mae_uT} µT · INT8{' '}
        <span className={s.bit_exact ? 'ok' : 'bad'}>{s.bit_exact ? '✓ bit-exact' : '✗'}</span> ({s.rounding})
      </div>
      {m.figures?.map((f) => (
        <figure key={f.name} style={{ margin: '12px 0 0' }}>
          <img src={'/api/figures/' + f.name} alt={f.caption}
               style={{ width: '100%', borderRadius: 6, border: '1px solid var(--border)' }} />
          <figcaption className="footnote">{f.caption}</figcaption>
        </figure>
      ))}
    </div>
  )
}
