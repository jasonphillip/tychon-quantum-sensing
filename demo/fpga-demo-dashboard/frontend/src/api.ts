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
  latency_ms?: number | null
  actuator_gated?: boolean
  source?: string
  rows?: number
  last_read?: number
  error?: string
}

export interface EvidenceItem { key: string; label: string; state: string }

export interface V250Result {
  ok: boolean
  result: string
  error_val: number | null
  out0: number | null
  model: string
  simulated: boolean
  raw: string[]
}

export interface CsrRow { name: string; addr: string; value: unknown; kind: string; error?: string }

export interface GainResult {
  name: string; addr: string; wrote: number; readback: number; bit_exact: boolean
  axi_write_count_before: number; axi_write_count_after: number; note: string
}

export interface Sample {
  t_host: number; sample_idx: number; error_in: number; nn_u_ai: number
  pid_only_out: number; pidnn_out: number; actuator_out: number; unclamped_calc: number
  clamp_active: number; watchdog_timeout: number; mode: string; vbx_error: number
  axi_write_count: number; csr_version: number
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
export const readCsr = () => fetch('/api/csr').then(J<CsrRow[]>)
export const writeGain = (name: string, value: number) => POST('/api/csr/write', { name, value }).then(J<GainResult>)
export const watchdogDemo = () => POST('/api/watchdog/demo').then(J<{ watchdog_timeout: number; induced: boolean; note: string }>)

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
