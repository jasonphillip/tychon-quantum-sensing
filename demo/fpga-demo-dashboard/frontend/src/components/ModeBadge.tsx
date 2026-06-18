export function ModeBadge({ mode, onChange }: { mode: string; onChange: (m: string) => void }) {
  const modes = ['LIVE', 'DRY-RUN', 'REPLAY']
  const cls = (m: string) => 'm-' + m.replace('-', '')
  return (
    <div className="modebadge" title="LIVE = real kit · REPLAY = saved capture · DRY-RUN = software">
      {modes.map((m) => (
        <button
          key={m}
          className={'mode-btn ' + (m === mode ? 'active ' + cls(m) : '')}
          onClick={() => onChange(m)}
        >
          {m}
        </button>
      ))}
    </div>
  )
}
