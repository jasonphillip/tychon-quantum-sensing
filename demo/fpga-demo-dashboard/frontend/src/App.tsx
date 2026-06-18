import { useCallback, useEffect, useState } from 'react'
import * as api from './api'
import { ModeBadge } from './components/ModeBadge'
import { ConnectionStrip } from './components/ConnectionStrip'
import { EvidenceStrip } from './components/EvidenceStrip'
import { V250Panel } from './components/V250Panel'
import { CsrPanel } from './components/CsrPanel'
import { WatchdogPanel } from './components/WatchdogPanel'
import { TelemetryPlot } from './components/TelemetryPlot'
import { SystemFlow } from './components/SystemFlow'
import { ModelCard } from './components/ModelCard'
import { MetricsTiles } from './components/MetricsTiles'
import { SpectrumViewer } from './components/SpectrumViewer'

export default function App() {
  const [status, setStatus] = useState<api.Status | null>(null)
  const [evidence, setEvidence] = useState<api.EvidenceItem[]>([])
  const [streamSample, setStreamSample] = useState<api.Sample | null>(null)

  const refresh = useCallback(async () => {
    try { setStatus(await api.getStatus()) }
    catch (e) { setStatus({ mode: '?', online: false, error: String(e), csr_version_ok: false }) }
    try { setEvidence(await api.getEvidence()) } catch { /* keep last */ }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 1000)
    return () => clearInterval(t)
  }, [refresh])

  const changeMode = async (m: string) => {
    try { setStatus(await api.setMode(m)) } catch { /* keep current */ }
    refresh()
  }

  const mode = status?.mode ?? '…'
  const flowTripped = streamSample ? streamSample.watchdog_timeout === 1 : !!status?.watchdog_timeout
  const flowMode = streamSample ? streamSample.mode
    : (status?.online ? (status?.watchdog_timeout ? 'PID_ONLY_FALLBACK' : 'PID_NN') : '—')

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>PolarFire SoC Icicle — Live Demo</h1>
          <div className="sub">
            V250 NPU inference · PID control-plane · hardware watchdog · MPFS250T production silicon
          </div>
        </div>
        <ModeBadge mode={mode} onChange={changeMode} />
      </header>

      <ConnectionStrip status={status} />
      <EvidenceStrip items={evidence} />

      <div className="grid">
        <V250Panel mode={mode} />
        <div className="col">
          <CsrPanel mode={mode} />
          <WatchdogPanel status={status} />
        </div>
      </div>

      <SystemFlow mode={flowMode} tripped={flowTripped} />
      <TelemetryPlot mode={mode} onSample={setStreamSample} onEnd={() => setStreamSample(null)} />
      <div className="grid" style={{ marginTop: 14 }}>
        <ModelCard />
        <MetricsTiles />
      </div>
      <SpectrumViewer />

      <div className="footnote">
        Modes: <b>LIVE</b> reads the kit over ssh (M1-only; the actuator value is M0-gated → 0 on
        silicon). <b>REPLAY</b> plays a saved capture. <b>DRY-RUN</b> is the software model — no board
        needed. The dashboard never touches the M0 gains slave (it would wedge a hart).
      </div>
    </div>
  )
}
