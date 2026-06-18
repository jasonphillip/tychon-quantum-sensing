import { useState } from 'react'
import { runV250, V250Result } from '../api'

export function V250Panel({ mode }: { mode: string }) {
  const [res, setRes] = useState<V250Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await runV250()) } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="panel">
      <h2>V250 NPU inference</h2>
      <div className="row">
        <button className="act" onClick={run} disabled={busy}>{busy ? 'running…' : 'Run V250 check'}</button>
        {res?.simulated && <span className="sim-tag">SIMULATED · {mode}</span>}
      </div>
      {err && <div className="kv bad" style={{ marginTop: 10 }}>error: {err}</div>}
      {res && (
        <div style={{ marginTop: 12 }}>
          <div className={res.ok ? 'result-ok' : 'result-bad'}>{res.result}</div>
          <div className="kv">out[0] = <b>{res.out0 ?? '—'}</b> · error_val = {res.error_val ?? '—'}</div>
          <div className="kv" style={{ color: 'var(--muted)' }}>{res.model}</div>
          {res.raw?.length > 0 && <pre className="raw">{res.raw.join('\n')}</pre>}
        </div>
      )}
      <div className="hint">Runs <code>vbx_probe</code> + <code>vnnx_smoke</code> on the kit (cold-boot required for the V250).</div>
    </div>
  )
}
