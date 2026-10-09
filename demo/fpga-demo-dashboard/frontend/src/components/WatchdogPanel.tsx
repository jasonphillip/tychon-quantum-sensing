import { useState } from 'react'
import { Status, watchdogDemo } from '../api'

export function WatchdogPanel({ status }: { status: Status | null }) {
  const [info, setInfo] = useState<string | null>(null)
  const tripped = !!status?.watchdog_timeout
  const label = status?.watchdog_label ?? (tripped ? 'Safe fallback active' : 'AI assist active')

  const check = async () => {
    try {
      const r = await watchdogDemo()
      setInfo(`${r.note} · raw ${r.watchdog_raw ?? '—'} · timeout=${r.watchdog_timeout}`)
    } catch (e) {
      setInfo(String(e))
    }
  }

  return (
    <div className="panel">
      <h2>Safety watchdog</h2>
      <div className="kv">
        state: <b className={tripped ? 'warn' : 'ok'}>{label}</b>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="ghost" onClick={check}>Read advanced watchdog register</button>
      </div>
      {info && <div className="footnote">{info}</div>}
      <div className="footnote">
        When AI assist is stopped or stops producing fresh output, the controller reverts to the PID safety path.
        This image uses a 250,000-cycle fabric timeout at the 125 MHz PID clock.
      </div>
    </div>
  )
}
