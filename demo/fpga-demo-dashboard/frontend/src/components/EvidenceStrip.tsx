import { EvidenceItem } from '../api'

export function EvidenceStrip({ items }: { items: EvidenceItem[] }) {
  if (!items.length) return null
  return (
    <div className="evidence">
      {items.map((it) => (
        <div key={it.key} className={'badge ' + it.state}>
          <span className="s" />
          {it.label}: <b>{it.state.toUpperCase()}</b>
        </div>
      ))}
    </div>
  )
}
