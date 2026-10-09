import { EvidenceItem } from '../api'

function fmtTime(ts?: number | null) {
  return ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : 'needs recheck'
}

function stateText(state: string, checkedAt?: number | null) {
  if (state === 'warn' && !checkedAt) return 'NEEDS RECHECK'
  if (state === 'pass') return 'PASS'
  if (state === 'live') return 'LIVE'
  return state.toUpperCase()
}

export function EvidenceStrip({ items }: { items: EvidenceItem[] }) {
  if (!items.length) return null
  return (
    <div className="evidence">
      {items.map((it) => (
        <div key={it.key} className={'badge ' + it.state} title={it.note ?? undefined}>
          <span className="s" />
          <span>{it.label}: <b>{stateText(it.state, it.checked_at)}</b></span>
          <span className="badge-time">checked {fmtTime(it.checked_at)}</span>
        </div>
      ))}
    </div>
  )
}
