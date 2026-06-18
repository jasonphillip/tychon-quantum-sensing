import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { openTelemetry, Sample } from '../api'

type Cols = number[][]
const COLS = 7 // x, error_in, pid_only, pidnn, nn_u_ai, clamp, watchdog

function makeOpts(width: number): uPlot.Options {
  const ax = { stroke: '#8595a6', grid: { stroke: '#1c2733', width: 1 }, ticks: { stroke: '#1c2733' } }
  return {
    width,
    height: 300,
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: false }, y: {}, f: { range: [-0.05, 1.15] } },
    axes: [
      { ...ax },
      { ...ax, scale: 'y' },
      { stroke: '#8595a6', scale: 'f', side: 1, grid: { show: false } },
    ],
    series: [
      {},
      { label: 'error_in', stroke: '#d7e0ea', width: 1.5 },
      { label: 'PID-only', stroke: '#38bdf8', width: 1.5 },
      { label: 'PID+NN', stroke: '#f87171', width: 1.5 },
      { label: 'nn_u_ai', stroke: '#fbbf24', width: 1, dash: [4, 3] },
      { label: 'clamp', scale: 'f', stroke: '#fb923c', width: 1, points: { show: false } },
      { label: 'watchdog', scale: 'f', stroke: '#34d399', width: 1, points: { show: false } },
    ],
    legend: { live: false },
  }
}

export function TelemetryPlot({ mode, onSample, onEnd }: { mode: string; onSample?: (s: Sample) => void; onEnd?: () => void }) {
  const elRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const dataRef = useRef<Cols>(Array.from({ length: COLS }, () => []))
  const esRef = useRef<EventSource | null>(null)
  const [running, setRunning] = useState(false)
  const [count, setCount] = useState(0)
  const [nn, setNn] = useState('surrogate')
  const [stunt, setStunt] = useState('none')

  useEffect(() => {
    if (!elRef.current) return
    const u = new uPlot(makeOpts(elRef.current.clientWidth), dataRef.current as unknown as uPlot.AlignedData, elRef.current)
    plotRef.current = u
    const onResize = () => { if (elRef.current) u.setSize({ width: elRef.current.clientWidth, height: 300 }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); u.destroy(); plotRef.current = null }
  }, [])

  const stop = () => { esRef.current?.close(); esRef.current = null; setRunning(false); onEnd?.() }

  const start = () => {
    stop()
    const d: Cols = Array.from({ length: COLS }, () => [])
    dataRef.current = d
    setCount(0)
    setRunning(true)
    esRef.current = openTelemetry(
      { rows: 120, nn, stunt, period: 0.06 },
      (s: Sample) => {
        d[0].push(s.sample_idx); d[1].push(s.error_in); d[2].push(s.pid_only_out)
        d[3].push(s.pidnn_out); d[4].push(s.nn_u_ai); d[5].push(s.clamp_active); d[6].push(s.watchdog_timeout)
        plotRef.current?.setData(d as unknown as uPlot.AlignedData)
        setCount(d[0].length)
        onSample?.(s)
      },
      () => { setRunning(false); onEnd?.() },
      () => { setRunning(false); onEnd?.() },
    )
  }

  useEffect(() => () => stop(), [])

  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <h2>Closed-loop telemetry — Rung G replay</h2>
      <div className="row">
        <button className="act" onClick={running ? stop : start}>{running ? 'Stop' : 'Run replay'}</button>
        <select className="sel" value={nn} onChange={(e) => setNn(e.target.value)} disabled={running}>
          <option value="surrogate">NN: surrogate</option>
          <option value="constant">NN: constant (V250 out)</option>
        </select>
        <select className="sel" value={stunt} onChange={(e) => setStunt(e.target.value)} disabled={running}>
          <option value="none">stunt: none</option>
          <option value="clamp">stunt: clamp trip</option>
          <option value="watchdog">stunt: watchdog trip</option>
        </select>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12 }}>{count} samples</span>
      </div>
      <div ref={elRef} style={{ marginTop: 12 }} />
      <div className="footnote">
        {mode === 'LIVE'
          ? 'LIVE silicon: error_in + liveness are real; PID-only / PID+NN / actuator read 0 (M0-gated). Switch to DRY-RUN or REPLAY to see the full nonzero closed loop.'
          : 'error_in · hardware PID-only vs PID+NN overlay; clamp / watchdog flags on the right axis. NN feedforward is a host-side surrogate (per-row V250 inference is a follow-up).'}
      </div>
    </div>
  )
}
