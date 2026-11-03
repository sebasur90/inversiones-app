import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CicloDetalleOut, CicloPuntoRrg, CicloTramo } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import BadgeCuadrante from './BadgeCuadrante'
import { INFO_CUADRANTE, fmtNum } from './constantes'

type Transiciones = NonNullable<NonNullable<CicloDetalleOut['rotacion']>['transiciones']>

const VERBO: Record<string, string> = {
  leading: 'Ingresó a Leading',
  weakening: 'Pasó a Weakening',
  lagging: 'Ingresó a Lagging',
  improving: 'Empezó a mejorar (Improving)',
}

function Linea({ t, confirmada }: { t: CicloTramo; confirmada: boolean }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-caption">
      <span className="text-app-text-faint tabular-nums whitespace-nowrap">{fechaCorta(t.desde)}</span>
      <span className="text-app-text">{confirmada ? VERBO[t.cuadrante] : `Movimiento breve a ${INFO_CUADRANTE[t.cuadrante].nombre}`}</span>
      <span className="text-label text-app-text-faint">
        {confirmada ? `sostenido ${t.semanas} sem.` : `${t.semanas} sem. · transitorio`}
      </span>
    </li>
  )
}

/**
 * Cómo fue cambiando la posición del grupo: RS-Ratio y RS-Momentum en el tiempo y, debajo, cuándo ingresó a cada
 * cuadrante. Los cambios confirmados (sostenidos) se distinguen de los transitorios y de lo que todavía no se sabe.
 */
export default function HistorialRotacion({ puntos, transiciones }: { puntos: CicloPuntoRrg[]; transiciones: Transiciones | null }) {
  if (puntos.length === 0) return null
  const orden = [
    ...(transiciones?.cambios_confirmados ?? []).map(t => ({ t, confirmada: true })),
    ...(transiciones?.transitorios ?? []).map(t => ({ t, confirmada: false })),
  ].sort((a, b) => a.t.desde.localeCompare(b.t.desde))
  return (
    <div className="flex flex-col gap-3">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={puntos} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
          <XAxis
            dataKey="fecha"
            tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickFormatter={(f: string) => `${f.slice(5, 7)}/${f.slice(2, 4)}`}
            minTickGap={32}
          />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={36} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(0)} />
          <ReferenceLine y={100} stroke="#64748b" />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
            labelFormatter={(f: string) => fechaCorta(f)}
            formatter={(v: number, n: string) => [fmtNum(v, 1), n]}
          />
          <Line type="monotone" dataKey="rs_ratio" name="Fortaleza relativa" stroke="#60a5fa" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="rs_momentum" name="Momentum relativo" stroke="#fbbf24" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex gap-3 text-label text-app-text-dim">
        <span className="inline-flex items-center gap-1"><span aria-hidden="true" className="w-3 h-0.5 bg-[#60a5fa]" />Fortaleza relativa</span>
        <span className="inline-flex items-center gap-1"><span aria-hidden="true" className="w-3 h-0.5 bg-[#fbbf24]" />Momentum relativo</span>
        <span className="text-app-text-faint">100 = neutral</span>
      </div>

      <div>
        <div className="text-label font-bold uppercase text-app-text-faint mb-1.5">
          Cambios de cuadrante (<InfoTooltip term="ciclos_cambio_confirmado" label="confirmado = 3 semanas seguidas" />)
        </div>
        {orden.length === 0 && !transiciones?.pendiente ? (
          <p className="text-caption text-app-text-dim">En el historial disponible no hubo cambios de cuadrante.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {orden.map(({ t, confirmada }) => (
              <Linea key={`${t.desde}-${t.cuadrante}`} t={t} confirmada={confirmada} />
            ))}
          </ul>
        )}
        {transiciones?.pendiente && (
          <div className="mt-2 rounded-lg border border-app-warn/30 bg-app-warn/10 px-2.5 py-1.5 text-caption text-app-text-dim">
            Desde {fechaCorta(transiciones.pendiente.desde)} está en <BadgeCuadrante cuadrante={transiciones.pendiente.cuadrante} pendiente />{' '}
            ({transiciones.pendiente.semanas} sem.): todavía no se sabe si el cambio se sostiene.
          </div>
        )}
      </div>
    </div>
  )
}
