import { useNavigate } from 'react-router-dom'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { Icon } from '../icons/Icons'
import Card from '../ui/Card'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'

interface Parte {
  label: string
  sub: string
  infoTerm: HelpKey
  valor: number | null
  color: string
}

/**
 * De dónde salió la ganancia: lo que está en cartera, lo que ya se vendió y lo cobrado. La barra
 * apilada sólo se dibuja cuando las tres partes suman y ninguna es negativa; con una pérdida en
 * el medio, los anchos proporcionales dejarían de significar algo, y queda la lista.
 */
export default function GananciaOrigen({
  realizado,
  noRealizado,
  ingresos,
  total,
}: {
  realizado: number | null
  noRealizado: number | null
  ingresos: number | null
  total: number | null
}) {
  const navigate = useNavigate()
  const { monto } = useFormatoMoneda()

  const partes: Parte[] = [
    { label: 'Lo que tenés en cartera', sub: 'Suba de precio, todavía sin vender', infoTerm: 'noRealizado', valor: noRealizado, color: 'var(--color-app-accent)' },
    { label: 'Lo que ya vendiste', sub: 'Ganancia realizada en ventas', infoTerm: 'realizado', valor: realizado, color: 'var(--color-app-cyan)' },
    { label: 'Dividendos y cupones', sub: 'Cobros mientras tenías el activo', infoTerm: 'ingresos', valor: ingresos, color: 'var(--color-app-violet)' },
  ]
  const suma = partes.reduce((acc, p) => acc + (p.valor ?? 0), 0)
  const dibujaBarra = suma > 0 && partes.every(p => (p.valor ?? 0) >= 0)

  return (
    <Card className="flex flex-col gap-3.5">
      {dibujaBarra && (
        <div aria-hidden="true" className="flex h-3 rounded-md overflow-hidden gap-0.5">
          {partes.filter(p => (p.valor ?? 0) > 0).map(p => (
            <div key={p.label} style={{ width: `${((p.valor ?? 0) / suma) * 100}%`, background: p.color }} />
          ))}
        </div>
      )}

      <div className="flex flex-col">
        {partes.map(p => (
          <div key={p.label} className="flex items-center gap-2.5 py-2.5 border-b border-app-border-soft">
            <span aria-hidden="true" className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: p.color }} />
            <div className="flex-1 min-w-0">
              <div className="text-body font-semibold text-app-text"><InfoTooltip term={p.infoTerm} label={p.label} /></div>
              <div className="text-caption text-app-text-dim">{p.sub}</div>
            </div>
            <div className={`font-mono text-body font-bold tabular-nums ${p.valor == null ? 'text-app-text' : p.valor >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
              {monto(p.valor)}
            </div>
          </div>
        ))}
        <div className="flex items-center justify-between pt-2.5">
          <div className="text-body font-bold text-app-text">Total</div>
          <div className={`font-mono text-strong font-bold tabular-nums ${total == null ? 'text-app-text' : total >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
            {monto(total)}
          </div>
        </div>
      </div>

      <button
        onClick={() => navigate('/explicacion-resultado')}
        className="group flex items-center justify-between min-h-11 px-3 rounded-xl bg-app-surface-2 text-body font-semibold text-app-text transition-[background-color,transform] duration-150 hover:bg-white/[0.08] active:scale-[0.98]"
      >
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true">🔎</span>
          Ver por qué ganaste o perdiste
        </span>
        <Icon name="chevron" className="w-4 h-4 -rotate-90 text-app-text-dim transition-transform duration-150 group-hover:translate-x-0.5" />
      </button>
    </Card>
  )
}
