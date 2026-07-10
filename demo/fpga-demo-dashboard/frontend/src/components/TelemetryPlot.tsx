import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { getV250Loop, openTelemetry, Sample, startV250Loop, stopV250Loop, V250LoopStatus } from '../api'

type Cols = number[][]
const COLS = 7 // x, error_in, pid_only, pidnn, nn_u_ai, clamp, watchdog
const LIVE_TRACE_LIMIT = 240

function fmt(v?: number | null, digits = 4) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

function makeOpts(width: number): uPlot.Options {
  const ax = { stroke: '#8595a6', grid: { stroke: '#1c2733', width: 1 }, ticks: { stroke: '#1c2733' } }
  return {
    width,
    height: 300,
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: false }, y: {}, u: { range: [-0.06, 0.06] }, f: { range: [-0.05, 1.15] } },
    axes: [
      { ...ax },
      { ...ax, scale: 'y' },
      { stroke: '#fbbf24', scale: 'u', side: 1, grid: { show: false } },
      { show: false, scale: 'f', side: 1 },
    ],
    series: [
      {},
      { label: 'error_in', show: false, stroke: '#94a3b8', width: 1, dash: [2, 4] },
      { label: 'PID estimate', show: false, stroke: '#38bdf8', width: 1.5, dash: [8, 4] },
      { label: 'final actuator', stroke: '#f87171', width: 2.4 },
      { label: 'AI correction', scale: 'u', stroke: '#fbbf24', width: 1.7, dash: [4, 3] },
      { label: 'clamp', show: false, scale: 'f', stroke: '#fb923c', width: 1, points: { show: false } },
      { label: 'watchdog', show: false, scale: 'f', stroke: '#34d399', width: 1, points: { show: false } },
    ],
    legend: { show: false },
  }
}

export function TelemetryPlot({ mode, onSample, onEnd }: { mode: string; onSample?: (s: Sample) => void; onEnd?: () => void }) {
  const elRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const dataRef = useRef<Cols>(Array.from({ length: COLS }, () => []))
  const esRef = useRef<EventSource | null>(null)
  const lastLoopKeyRef = useRef<string | null>(null)
  const [running, setRunning] = useState(false)
  const [count, setCount] = useState(0)
  const [nn, setNn] = useState('v250-loop')
  const [stunt, setStunt] = useState('none')
  const [loopStatus, setLoopStatus] = useState<V250LoopStatus | null>(null)
  const [loopBusy, setLoopBusy] = useState(false)
  const [loopError, setLoopError] = useState<string | null>(null)
  const [latestSample, setLatestSample] = useState<Sample | null>(null)

  useEffect(() => {
    if (nn === 'v250-loop' && stunt !== 'none') setStunt('none')
  }, [nn, stunt])

  useEffect(() => {
    if (!elRef.current) return
    const u = new uPlot(makeOpts(elRef.current.clientWidth), dataRef.current as unknown as uPlot.AlignedData, elRef.current)
    plotRef.current = u
    const onResize = () => { if (elRef.current) u.setSize({ width: elRef.current.clientWidth, height: 300 }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); u.destroy(); plotRef.current = null }
  }, [])

  const stop = () => { esRef.current?.close(); esRef.current = null; setRunning(false); onEnd?.() }

  const resetPlot = () => {
    const d: Cols = Array.from({ length: COLS }, () => [])
    dataRef.current = d
    plotRef.current?.setData(d as unknown as uPlot.AlignedData)
    lastLoopKeyRef.current = null
    setLatestSample(null)
    setCount(0)
    return d
  }

  const appendSample = (s: Sample) => {
    const d = dataRef.current
    const x = nn === 'v250-loop' ? (d[0].length ? d[0][d[0].length - 1] + 1 : 0) : s.sample_idx
    d[0].push(x); d[1].push(s.error_in); d[2].push(s.pid_only_out)
    d[3].push(s.pidnn_out); d[4].push(s.nn_u_ai); d[5].push(s.clamp_active); d[6].push(s.watchdog_timeout)
    if (d[0].length > LIVE_TRACE_LIMIT) {
      d.forEach((col) => col.splice(0, col.length - LIVE_TRACE_LIMIT))
    }
    plotRef.current?.setData(d as unknown as uPlot.AlignedData)
    setLatestSample(s)
    setCount(d[0].length)
  }

  const sampleFromLoop = (s: V250LoopStatus): Sample | null => {
    const st = s.state
    if (!st) return null
    const axi = typeof st.axi_write_count === 'string' ? Number.parseInt(st.axi_write_count, 16) : 0
    return {
      t_host: st.t_ns / 1_000_000_000,
      sample_idx: st.row,
      error_in: st.error_in,
      nn_u_ai: st.u_ai,
      pid_only_out: st.error_in * 0.8,
      pidnn_out: st.post_clamp,
      actuator_out: st.post_clamp,
      unclamped_calc: st.error_in * 0.8 + st.u_ai,
      clamp_active: Math.abs(st.u_ai) > 0.045 ? 1 : 0,
      watchdog_timeout: st.watchdog_timeout,
      mode: st.watchdog_timeout ? 'PID_ONLY_FALLBACK' : 'PID_NN',
      vbx_error: 0,
      axi_write_count: Number.isFinite(axi) ? axi : 0,
      csr_version: 0x00010000,
    }
  }

  const refreshLoop = async () => {
    try {
      setLoopError(null)
      const s = await getV250Loop()
      setLoopStatus(s)
      const latest = sampleFromLoop(s)
      const st = s.state
      const key = st ? `${s.pid ?? st.pid}:${st.row}:${st.updated_ns}` : null
      if (latest) {
        setLatestSample(latest)
        onSample?.(latest)
        if (s.running && key && key !== lastLoopKeyRef.current) {
          appendSample(latest)
          lastLoopKeyRef.current = key
        }
      }
    } catch (e) {
      setLoopError(String(e))
    }
  }

  useEffect(() => {
    if (nn !== 'v250-loop' || mode !== 'LIVE') return
    refreshLoop()
    const t = window.setInterval(refreshLoop, 1000)
    return () => window.clearInterval(t)
  }, [nn, mode])

  const startDaemon = async () => {
    setLoopBusy(true)
    try {
      setLoopError(null)
      resetPlot()
      const s = await startV250Loop()
      setLoopStatus(s)
      const latest = sampleFromLoop(s)
      const st = s.state
      if (latest) {
        onSample?.(latest)
        appendSample(latest)
        lastLoopKeyRef.current = st ? `${s.pid ?? st.pid}:${st.row}:${st.updated_ns}` : null
      }
    } catch (e) {
      setLoopError(String(e))
    } finally {
      setLoopBusy(false)
    }
  }

  const stopDaemon = async () => {
    setLoopBusy(true)
    try {
      setLoopError(null)
      const s = await stopV250Loop()
      setLoopStatus(s)
      onEnd?.()
    } catch (e) {
      setLoopError(String(e))
    } finally {
      setLoopBusy(false)
    }
  }

  const start = () => {
    stop()
    resetPlot()
    setRunning(true)
    esRef.current = openTelemetry(
      { rows: 120, nn, stunt, period: nn === 'v250-loop' ? 0 : 0.06 },
      (s: Sample) => {
        appendSample(s)
        onSample?.(s)
      },
      () => { setRunning(false); onEnd?.() },
      () => { setRunning(false); onEnd?.() },
    )
  }

  useEffect(() => () => stop(), [])

  const liveLoop = nn === 'v250-loop'
  const canCapture = !(liveLoop && mode !== 'LIVE')
  const safetyState = latestSample ? (latestSample.watchdog_timeout ? 'fallback active' : 'AI assist active') : 'waiting'
  const clampState = latestSample ? (latestSample.clamp_active ? 'limit reached' : 'within bound') : 'waiting'
  const safetyClass = latestSample ? (latestSample.watchdog_timeout ? 'warn' : 'pass') : 'idle'
  const clampClass = latestSample ? (latestSample.clamp_active ? 'warn' : 'pass') : 'idle'

  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <h2>{liveLoop ? 'Tychon AI Control Assist - live hardware' : 'Hardware replay - host-paced'}</h2>
      <div className="row">
        <button className="act" onClick={running ? stop : start} disabled={!running && !canCapture}>
          {running ? 'Stop capture' : (liveLoop ? 'Capture 120 live points' : 'Run hardware replay')}
        </button>
        <select className="sel" value={nn} onChange={(e) => setNn(e.target.value)} disabled={running}>
          <option value="v250-loop">AI source: Tychon chip loop</option>
          <option value="surrogate">AI source: software-estimated assist</option>
        </select>
        <select className="sel" value={stunt} onChange={(e) => setStunt(e.target.value)} disabled={running || liveLoop}>
          <option value="none">demo scenario: none</option>
          <option value="clamp">demo scenario: clamp trip</option>
          <option value="watchdog">demo scenario: watchdog fallback</option>
        </select>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12 }}>{count} samples</span>
      </div>
      {liveLoop && (
        <div className="row" style={{ marginTop: 10 }}>
          <button className="act" onClick={startDaemon} disabled={loopBusy || mode !== 'LIVE'}>
            Start Tychon AI Control Assist
          </button>
          <button className="ghost" onClick={stopDaemon} disabled={loopBusy || mode !== 'LIVE'}>
            Stop AI Assist
          </button>
          <button className="ghost" onClick={refreshLoop} disabled={loopBusy || mode !== 'LIVE'}>
            Read latest status
          </button>
          <span style={{ color: loopStatus?.running ? 'var(--green)' : 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12 }}>
            assist: {loopStatus?.running ? 'running + plotting' : 'stopped'} · row {loopStatus?.state?.row ?? '—'} · safety {loopStatus?.state ? (loopStatus.state.watchdog_timeout ? 'fallback' : 'AI active') : '—'} · AI correction {loopStatus?.state?.u_ai?.toFixed(5) ?? '—'} · actuator {loopStatus?.state?.post_clamp?.toFixed(5) ?? '—'}
          </span>
          {loopError && <span style={{ color: 'var(--red)', fontFamily: 'var(--mono)', fontSize: 12 }}>{loopError}</span>}
        </div>
      )}
      <div className="assist-grid">
        <div className="assist-card ai">
          <div className="assist-label">AI correction</div>
          <div className="assist-value">{fmt(latestSample?.nn_u_ai)}</div>
        </div>
        <div className="assist-card">
          <div className="assist-label">Final actuator</div>
          <div className="assist-value">{fmt(latestSample?.actuator_out)}</div>
        </div>
      </div>
      <div className="trace-status-row">
        <span className={`trace-pill ${safetyClass}`}>safety: {safetyState}</span>
        <span className={`trace-pill ${clampClass}`}>correction: {clampState}</span>
        <span className="trace-key final">final actuator</span>
        <span className="trace-key ai">AI correction</span>
      </div>
      <div className="section-kicker">Live trace - last {count || 0} samples</div>
      <div ref={elRef} style={{ marginTop: 12 }} />
      <div className="footnote">
        {mode === 'LIVE'
          ? (liveLoop
            ? 'LIVE silicon: the on-kit helper runs AI-chip inference, writes AI correction into the PID fabric, pulses compute, and reads the hardware actuator tap. The dashboard polls and plots it.'
            : 'LIVE silicon: hardware replay injects error, pulses the PID fabric, and reads the actuator. AI assist is software-estimated in this mode.')
          : 'Offline/replay mode: PID-only vs AI-assisted overlay with clamp and watchdog flags on the right axis.'}
      </div>
    </div>
  )
}
