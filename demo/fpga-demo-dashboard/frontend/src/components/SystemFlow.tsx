import { useEffect, useRef, useState } from 'react'

function box(x: number, y: number, w: number, h: number, label: string, sub: string, cls = '') {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="6" className={'flow-box ' + cls} />
      <text x={x + w / 2} y={y + (sub ? 19 : 27)} className="flow-label">{label}</text>
      {sub ? <text x={x + w / 2} y={y + 33} className="flow-sub">{sub}</text> : null}
    </g>
  )
}

export function SystemFlow({ mode, tripped }: { mode: string; tripped: boolean }) {
  const nn = tripped ? 'off' : 'on'
  const [hist, setHist] = useState<number[]>([])
  const last = useRef<number | null>(null)
  useEffect(() => {
    const v = tripped ? 1 : 0
    if (last.current !== v) { last.current = v; setHist((h) => [...h.slice(-59), v]) }
  }, [tripped])

  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <h2>System flow — what the FPGA is doing</h2>
      <svg viewBox="0 0 940 200" className="flow" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="ah" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" className="arrowhead" />
          </marker>
        </defs>
        <line className="arrow" x1="150" y1="46" x2="196" y2="46" markerEnd="url(#ah)" />
        <path className={'arrow nn ' + nn} d="M352,46 L408,82" markerEnd="url(#ah)" />
        <line className="arrow" x1="150" y1="150" x2="196" y2="150" markerEnd="url(#ah)" />
        <path className="arrow live" d="M352,150 L408,114" markerEnd="url(#ah)" />
        <line className="arrow live" x1="458" y1="98" x2="506" y2="98" markerEnd="url(#ah)" />
        <line className="arrow live" x1="632" y1="98" x2="686" y2="98" markerEnd="url(#ah)" />
        <path className={'arrow wdmon ' + (tripped ? 'tr' : 'ar')} d="M508,48 L362,68"
              strokeDasharray="4 3" markerEnd="url(#ah)" />
        {box(8, 24, 142, 44, 'ODMR spectrum', 'nv-sensor-sim')}
        {box(196, 24, 156, 44, 'V250 NN', tripped ? 'stalled' : 'inferring', 'nn ' + nn)}
        {box(8, 128, 142, 44, 'ODMR error', 'detuning')}
        {box(196, 128, 156, 44, 'PID', 'always on', 'live')}
        {box(408, 76, 50, 44, 'Σ', '')}
        {box(506, 76, 126, 44, 'clamp', '±4.5% sector')}
        {box(686, 76, 150, 44, 'actuator', tripped ? 'PID-only' : 'PID + NN', 'live')}
        <rect x="408" y="6" width="216" height="40" rx="6" className={'wd-box ' + (tripped ? 'tr' : 'ar')} />
        <text x="516" y="24" className="wd-t">watchdog</text>
        <text x="516" y="38" className="wd-s">{tripped ? 'TIMEOUT → fallback' : 'armed'}</text>
      </svg>
      <div className="flow-legend">
        mode: <b className={tripped ? 'bad' : 'ok'}>{mode}</b>
        <span className="wd-hist">{hist.map((v, i) => <span key={i} className={'tick ' + (v ? 'r' : 'g')} />)}</span>
      </div>
      <div className="footnote">
        {tripped
          ? 'V250 NN path gated out — the watchdog tripped and the controller fell back to pure PID (bumpless). This is the safety behavior.'
          : 'V250 NN feedforward is live and summed with the PID output; the watchdog is armed.'}
      </div>
    </div>
  )
}
