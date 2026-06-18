import { useState } from 'react'
import { Status, watchdogDemo } from '../api'

export function WatchdogPanel({ status }: { status: Status | null }) {
  const [info, setInfo] = useState<string | null>(null)
  const tripped = !!status?.watchdog_timeout

  const check = async () => {
    try {
      const r = await watchdogDemo()
      setInfo(`${r.note} (timeout=${r.watchdog_timeout})`)
    } catch (e) {
      setInfo(String(e))
    }
  }

  return (
    <div className="panel">
      <h2>Safety watchdog</h2>
      <div className="kv">
        state: <b className={tripped ? 'bad' : 'ok'}>{tripped ? 'TIMEOUT → PID_ONLY_FALLBACK' : 'armed · PID_NN'}</b>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="ghost" onClick={check}>Read watchdog_csr</button>
      </div>
      {info && <div className="footnote">{info}</div>}
      <div className="footnote">
        When the V250 stops producing fresh output, the watchdog trips and the controller reverts to
        pure PID — the safety behavior to demonstrate. On-demand induction is a follow-up (open item #4).
      </div>
    </div>
  )
}
