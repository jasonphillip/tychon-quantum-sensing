import { useEffect, useState } from 'react'
import { CsrRow, GainResult, readCsr, writeGain } from '../api'

const GAINS = ['kp', 'ki', 'kd', 'out_min', 'out_max', 'inner_clamp']

export function CsrPanel({ mode }: { mode: string }) {
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

  return (
    <div className="panel">
      <h2>PID control-plane · M1 CSR</h2>
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
        <button className="act" onClick={doWrite} disabled={!canWrite}>Write + read back</button>
      </div>
      {!canWrite && <div className="hint">writes disabled in REPLAY mode</div>}
      {wr && (
        <div className="kv" style={{ marginTop: 8 }}>
          wrote {wr.wrote} → readback <b className={wr.bit_exact ? 'ok' : 'bad'}>{wr.readback}</b>{' '}
          {wr.bit_exact ? '✓ bit-exact' : '✗ mismatch'}
          <div className="footnote">{wr.note}</div>
        </div>
      )}
      {err && <div className="kv bad" style={{ marginTop: 8 }}>error: {err}</div>}
    </div>
  )
}
