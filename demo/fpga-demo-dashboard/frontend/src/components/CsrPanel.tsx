import { useEffect, useState } from 'react'
import { CsrRow, EvidenceItem, GainResult, readCsr, Status, writeGain } from '../api'

const GAINS = ['kp', 'ki', 'kd', 'out_min', 'out_max', 'inner_clamp']

function fmtTime(ts?: number | null) {
  return ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : 'needs recheck'
}

function CheckCard({ label, state, value, detail }: { label: string; state: string; value: string; detail: string }) {
  return (
    <div className={'check-card ' + state}>
      <div className="check-top">
        <span className="check-dot" />
        <span>{label}</span>
      </div>
      <div className="check-value">{value}</div>
      <div className="check-detail">{detail}</div>
    </div>
  )
}

export function CsrPanel({ mode, status, evidence }: { mode: string; status: Status | null; evidence: EvidenceItem[] }) {
  const [rows, setRows] = useState<CsrRow[]>([])
  const [name, setName] = useState('kp')
  const [val, setVal] = useState('1.5')
  const [wr, setWr] = useState<GainResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const refresh = async () => {
    try { setRows(await readCsr()) } catch (e) { setErr(String(e)) }
  }
  useEffect(() => { refresh() }, [mode])

  const doWrite = async () => {
    setErr(null)
    try { setWr(await writeGain(name, parseFloat(val))); await refresh() }
    catch (e) { setErr(String(e)) }
  }

  const canWrite = mode !== 'REPLAY'
  const pidEvidence = evidence.find((it) => it.key === 'pid')
  const online = !!status?.online
  const fpgaState = status?.csr_version_ok ? 'pass' : (online ? 'fail' : 'warn')
  const pidState = status?.idfix2_smoke_ok ? 'pass' : (status?.m0_writes_enabled ? 'warn' : (online ? 'fail' : 'warn'))
  const actuatorState = status?.idfix2_smoke_ok ? 'pass' : (status?.m0_writes_enabled ? 'warn' : (online ? 'fail' : 'warn'))

  return (
    <div className="panel">
      <h2>Hardware checks</h2>
      <div className="check-grid">
        <CheckCard
          label="FPGA alive"
          state={fpgaState}
          value={status?.csr_version_ok ? 'ready' : (status?.online ? 'check failed' : 'offline')}
          detail={status?.csr_version ? `version ${status.csr_version}` : 'waiting for kit'}
        />
        <CheckCard
          label="PID path alive"
          state={pidState}
          value={status?.idfix2_smoke_ok ? 'checked' : (status?.m0_writes_enabled ? 'needs recheck' : 'gated')}
          detail={pidEvidence?.checked_at ? `checked ${fmtTime(pidEvidence.checked_at)}` : (status?.idfix2_smoke_note ?? 'run AI assist or hardware replay')}
        />
        <CheckCard
          label="Actuator readback alive"
          state={actuatorState}
          value={status?.idfix2_smoke_ok ? 'real readback' : (status?.m0_writes_enabled ? 'needs recheck' : 'unavailable')}
          detail={status?.idfix2_smoke_ok ? 'hardware actuator value is being read back' : 'run AI assist or hardware replay to refresh this check'}
        />
      </div>

      <details className="advanced">
        <summary>Advanced hardware registers</summary>
        <table className="reg"><tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td className="name">{r.name}</td>
              <td className="addr">{r.addr}</td>
              <td className="val">{r.error ? '—' : String(r.value)}</td>
            </tr>
          ))}
        </tbody></table>
        <div className="row" style={{ marginTop: 10 }}>
          <select className="sel" value={name} onChange={(e) => setName(e.target.value)}>
            {GAINS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
          <input className="num" value={val} onChange={(e) => setVal(e.target.value)} />
          <button className="act" onClick={doWrite} disabled={!canWrite}>Write advanced gain</button>
        </div>
        {!canWrite && <div className="hint">writes disabled in REPLAY mode</div>}
        {wr && (
          <div className="kv" style={{ marginTop: 8 }}>
            wrote {wr.wrote} → readback <b className={wr.bit_exact ? 'ok' : 'bad'}>{wr.readback}</b>{' '}
            {wr.bit_exact ? 'M1 echo ok' : 'M1 mismatch'}{wr.m0_written ? ' · live gain updated' : ''}
            <div className="footnote">{wr.note}</div>
          </div>
        )}
        {err && <div className="kv bad" style={{ marginTop: 8 }}>error: {err}</div>}
      </details>
    </div>
  )
}
