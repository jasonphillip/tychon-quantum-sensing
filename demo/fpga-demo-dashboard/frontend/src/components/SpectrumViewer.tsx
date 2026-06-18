import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'

interface Spec {
  idx: number; b_uT: number; b_xyz_uT: number[]
  p1_ppm: number; temp_K: number; b1_grad: number; spectrum: number[]
}
interface SpecData { freq_ghz: number[]; samples: Spec[] }

export function SpectrumViewer() {
  const [data, setData] = useState<SpecData | null>(null)
  const [sel, setSel] = useState(0)
  const elRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => { fetch('/api/spectrum').then((r) => r.json()).then(setData).catch(() => {}) }, [])

  useEffect(() => {
    if (!data || !elRef.current) return
    const ax = { stroke: '#8595a6', grid: { stroke: '#1c2733', width: 1 }, ticks: { stroke: '#1c2733' } }
    const opts: uPlot.Options = {
      width: elRef.current.clientWidth, height: 260,
      scales: { x: { time: false }, y: {} },
      axes: [{ ...ax }, { ...ax }],
      series: [{}, { label: 'PL (norm)', stroke: '#38bdf8', width: 1.5, fill: 'rgba(56,189,248,0.08)' }],
      legend: { show: false },
      cursor: { drag: { x: false, y: false } },
    }
    const u = new uPlot(opts, [data.freq_ghz, data.samples[0].spectrum] as unknown as uPlot.AlignedData, elRef.current)
    plotRef.current = u
    const onResize = () => { if (elRef.current) u.setSize({ width: elRef.current.clientWidth, height: 260 }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); u.destroy(); plotRef.current = null }
  }, [data])

  useEffect(() => {
    if (data && plotRef.current) {
      plotRef.current.setData([data.freq_ghz, data.samples[sel].spectrum] as unknown as uPlot.AlignedData)
    }
  }, [sel, data])

  if (!data) return <div className="panel" style={{ marginTop: 14 }}><h2>ODMR spectrum</h2><div className="kv">loading…</div></div>
  const s = data.samples[sel]
  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <h2>ODMR spectrum — simulated input (nv-sensor-sim)</h2>
      <div className="row">
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>sample</span>
        <select className="sel" value={sel} onChange={(e) => setSel(parseInt(e.target.value))}>
          {data.samples.map((sm, i) => <option key={i} value={i}>#{sm.idx} · |B| {sm.b_uT} µT</option>)}
        </select>
        <span className="kv" style={{ marginLeft: 8 }}>
          ground-truth |B| <b>{s.b_uT} µT</b> · P1 {s.p1_ppm} ppm · T {s.temp_K} K · B1grad {s.b1_grad}
        </span>
      </div>
      <div ref={elRef} style={{ marginTop: 10 }} />
      <div className="footnote">
        Real physics-simulated CW-ODMR spectrum (800 pts, 2.83–2.91 GHz) with ground-truth |B|. The FCNN
        reads a 100-pt window of this; live inference is in the V250 panel, accuracy in Metrics.
      </div>
    </div>
  )
}
