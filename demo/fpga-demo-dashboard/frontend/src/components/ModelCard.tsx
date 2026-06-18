import { useEffect, useState } from 'react'

interface Card {
  name: string; arch: string; params: number; quant: string
  tflite_kb: number; vnnx_kb: number; input: string; output: string
  target: string; deployed_out0: number
}

export function ModelCard() {
  const [c, setC] = useState<Card | null>(null)
  useEffect(() => { fetch('/api/model-card').then((r) => r.json()).then(setC).catch(() => {}) }, [])

  if (!c) return <div className="panel"><h2>Model</h2><div className="kv">loading…</div></div>

  const rows: [string, string][] = [
    ['architecture', c.arch],
    ['parameters', c.params.toLocaleString()],
    ['quantization', c.quant],
    ['size', `${c.tflite_kb} KB TFLite → ${c.vnnx_kb} KB .vnnx`],
    ['input', c.input],
    ['output', c.output],
    ['target', c.target],
    ['live out[0]', String(c.deployed_out0)],
  ]
  return (
    <div className="panel">
      <h2>Model — {c.name}</h2>
      <table className="reg"><tbody>
        {rows.map(([k, v]) => (
          <tr key={k}><td className="name">{k}</td><td style={{ textAlign: 'left' }}>{v}</td></tr>
        ))}
      </tbody></table>
      <div className="hint">ODMR spectrum → magnetic-field residual correction, deployed on the V250 NPU.</div>
    </div>
  )
}
