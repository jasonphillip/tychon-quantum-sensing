import { useState } from 'react'
import { runV250, V250Result } from '../api'

function fmtTime(ts?: number) {
  return ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—'
}

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
      <h2>AI chip test</h2>
      <div className="row">
        <button className="act" onClick={run} disabled={busy}>{busy ? 'testing...' : 'Test AI chip'}</button>
        {res?.simulated && <span className="sim-tag">SIMULATED · {mode}</span>}
      </div>
      {err && <div className="kv bad" style={{ marginTop: 10 }}>error: {err}</div>}
      {res && (
        <div style={{ marginTop: 12 }}>
          <div className={res.ok ? 'result-ok' : 'result-bad'}>
            {res.ok ? 'AI CHIP TEST PASSED' : 'AI CHIP TEST NEEDS ATTENTION'}
          </div>
          <div className="hint">checked {fmtTime(res.checked_at)}</div>
          <div className="kv">out[0] = <b>{res.out0 ?? '—'}</b> · error_val = {res.error_val ?? '—'}</div>
          <div className="kv" style={{ color: 'var(--muted)' }}>{res.model}</div>
          {res.raw?.length > 0 && (
            <details className="advanced">
              <summary>Advanced probe log</summary>
              <pre className="raw">{res.raw.join('\n')}</pre>
            </details>
          )}
        </div>
      )}
      <div className="hint">Runs the V250 probe and model smoke test on the kit.</div>
    </div>
  )
}
