import { Status } from '../api'

export function ConnectionStrip({ status }: { status: Status | null }) {
  const online = !!status?.online
  const t = status?.last_read ? new Date(status.last_read * 1000).toLocaleTimeString() : '—'
  return (
    <div className="connstrip">
      <div className="item">
        <span className="k">link</span>
        <span className="v">
          <span className={'dot ' + (online ? 'on' : 'off')} />
          {online ? (status?.mode ?? '') : 'OFFLINE'}
        </span>
      </div>
      <div className="item">
        <span className="k">kit</span>
        <span className="v">{status?.kit_host ?? status?.source ?? '—'}</span>
      </div>
      <div className="item">
        <span className="k">ssh latency</span>
        <span className="v">{status?.latency_ms != null ? status.latency_ms + ' ms' : '—'}</span>
      </div>
      <div className="item">
        <span className="k">heartbeat · axi_write_count</span>
        <span className="v">
          <span key={status?.axi_write_count} className="heart pulse">
            {status?.axi_write_count ?? '—'}
          </span>
        </span>
      </div>
      <div className="item">
        <span className="k">csr_version</span>
        <span className={'v ' + (status?.csr_version_ok ? 'ok' : 'bad')}>{status?.csr_version ?? '—'}</span>
      </div>
      <div className="item">
        <span className="k">watchdog</span>
        <span className={'v ' + (status?.watchdog_timeout ? 'bad' : 'ok')}>
          {status?.watchdog_timeout ? 'TIMEOUT' : 'ok'}
        </span>
      </div>
      <div className="item">
        <span className="k">last read</span>
        <span className="v">{t}</span>
      </div>
    </div>
  )
}
