// Typed client for the dashboard backend. All paths are relative ("/api/..."):
// dev -> Vite proxy to :8077; prod -> same-origin FastAPI. No absolute URLs, so
// the built app needs no network config at the offline demo.

export type Mode = 'LIVE' | 'DRY-RUN' | 'REPLAY'

export interface Status {
  mode: string
  kit_host?: string | null
  online: boolean
  csr_version?: string
  csr_version_ok?: boolean
  axi_write_count?: number
  watchdog_timeout?: number
  watchdog_raw?: string
  watchdog_note?: string
  watchdog_label?: string
  latency_ms?: number | null
  actuator_gated?: boolean
  actuator_source?: string
  kit_bitstream?: string | null
  m0_writes_enabled?: boolean
  m0_gate?: string
  idfix2_smoke_ok?: boolean
  idfix2_smoke_note?: string
  idfix2_smoke_checked_at?: number | null
  v250_ok?: boolean
  v250_note?: string
  v250_checked_at?: number | null
  reset_detected_at?: number | null
  kit_boot_marker?: string | null
  source?: string
  rows?: number
  last_read?: number
  error?: string
}

export interface EvidenceItem {
  key: string
  label: string
  state: string
  checked_at?: number | null
  note?: string
}

export interface V250Result {
  ok: boolean
  result: string
  error_val: number | null
  out0: number | null
  model: string
  simulated: boolean
  raw: string[]
  checked_at?: number
}

export interface CsrRow { name: string; addr: string; value: unknown; kind: string; error?: string }

export interface GainResult {
  name: string; addr: string; wrote: number; readback: number; bit_exact: boolean
  axi_write_count_before: number; axi_write_count_after: number; m0_written?: boolean; note: string
}

export interface Sample {
  t_host: number; sample_idx: number; error_in: number; nn_u_ai: number
  pid_only_out: number; pidnn_out: number; actuator_out: number; unclamped_calc: number
  clamp_active: number; watchdog_timeout: number; mode: string; vbx_error: number
  axi_write_count: number; csr_version: number
}

export interface V250LoopState {
  running: boolean
  pid: number
  row: number
  t_ns: number
  v250_ns: number
  polls: number
  input_row: number
  error_in: number
  nn_out0: number
  nn_q: number
  u_ai: number
  post_clamp: number
  watchdog_raw: string
  watchdog_timeout: number
  axi_write_count: string
  input_source: string
  updated_ns: number
}

export interface V250LoopStatus {
  running: boolean
  available?: boolean
  started?: boolean
  stopped?: boolean
  pid?: number | null
  state?: V250LoopState | null
  state_path?: string
  pid_path?: string
  log_path?: string
  note?: string
}

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return r.json() as Promise<T>
}

const POST = (path: string, body?: unknown) =>
  fetch(path, {
    method: 'POST',
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

export const getStatus = () => fetch('/api/status').then(J<Status>)
export const getEvidence = () => fetch('/api/evidence').then(J<EvidenceItem[]>)
export const setMode = (mode: string, file?: string) => POST('/api/mode', { mode, file }).then(J<Status>)
export const runV250 = () => POST('/api/v250/probe').then(J<V250Result>)
export const getV250Loop = () => fetch('/api/v250-loop/status').then(J<V250LoopStatus>)
export const startV250Loop = () => POST('/api/v250-loop/start').then(J<V250LoopStatus>)
export const stopV250Loop = () => POST('/api/v250-loop/stop').then(J<V250LoopStatus>)
export const readCsr = () => fetch('/api/csr').then(J<CsrRow[]>)
export const writeGain = (name: string, value: number) => POST('/api/csr/write', { name, value }).then(J<GainResult>)
export const watchdogDemo = () => POST('/api/watchdog/demo').then(J<{ watchdog_timeout: number; watchdog_raw?: string; induced: boolean; note: string }>)

export function openTelemetry(
  params: { rows?: number; nn?: string; stunt?: string; period?: number },
  onSample: (s: Sample) => void,
  onDone: () => void,
  onError: (msg: string) => void,
): EventSource {
  const q = new URLSearchParams()
  if (params.rows != null) q.set('rows', String(params.rows))
  if (params.nn) q.set('nn', params.nn)
  if (params.stunt) q.set('stunt', params.stunt)
  if (params.period != null) q.set('period', String(params.period))
  const es = new EventSource('/api/telemetry/stream?' + q.toString())
  es.onmessage = (e) => { try { onSample(JSON.parse(e.data)) } catch { /* ignore */ } }
  es.addEventListener('done', () => { es.close(); onDone() })
  es.addEventListener('error', () => { es.close(); onError('stream error / disconnected') })
  return es
}
