import { useMemo } from 'react'
import dayjs from 'dayjs'
import type { Evento } from '../../api'
import { Icon } from '../icons/Icons'
import { mesAnioLargo } from '../../utils/fechas'
import { agruparPorDia, COLOR_CATEGORIA, esEstimada, grillaMes, isoDia } from '../../utils/eventos'

const DIAS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const MAX_PUNTOS = 3

/**
 * Grilla mensual (lunes a domingo). Cada evento es un punto del color de su categoría; con más de
 * `MAX_PUNTOS` el día muestra "+N". Los días pasados quedan apagados y una fecha estimada se marca
 * con borde punteado: nunca se ve igual que una confirmada.
 */
export default function CalendarioMes({
  mes, eventos, diaElegido, onElegirDia, onCambiarMes,
}: {
  mes: string
  eventos: Evento[]
  diaElegido: string | null
  onElegirDia: (dia: string) => void
  onCambiarMes: (mes: string) => void
}) {
  const { dias } = useMemo(() => grillaMes(mes), [mes])
  const porDia = useMemo(() => agruparPorDia(eventos), [eventos])
  const hoy = isoDia(dayjs())
  const inicioMes = dayjs(`${mes}-01`)

  const mover = (delta: number) => onCambiarMes(inicioMes.add(delta, 'month').format('YYYY-MM'))

  return (
    <div className="bg-app-surface border border-app-border rounded-2xl p-3">
      <div className="flex items-center justify-between mb-2">
        <button onClick={() => mover(-1)} aria-label="Mes anterior" className="w-9 h-9 rounded-full flex items-center justify-center text-app-text-dim hover:bg-white/5 active:scale-90">
          <Icon name="back" className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-2">
          <span className="font-display text-strong font-semibold text-app-text">{mesAnioLargo(`${mes}-01`)}</span>
          {mes !== dayjs().format('YYYY-MM') && (
            <button onClick={() => onCambiarMes(dayjs().format('YYYY-MM'))} className="text-label font-bold text-app-accent px-2 py-1 rounded-lg hover:bg-app-accent-soft">
              Hoy
            </button>
          )}
        </div>
        <button onClick={() => mover(1)} aria-label="Mes siguiente" className="w-9 h-9 rounded-full flex items-center justify-center text-app-text-dim hover:bg-white/5 active:scale-90">
          <Icon name="back" className="w-4 h-4 rotate-180" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center">
        {DIAS.map((d, i) => (
          <div key={i} className="text-label font-bold text-app-text-faint py-1">{d}</div>
        ))}
        {dias.map(d => {
          const iso = isoDia(d)
          const lista = porDia.get(iso) ?? []
          const delMes = d.month() === inicioMes.month()
          const pasado = iso < hoy
          const elegido = iso === diaElegido
          const estimado = lista.length > 0 && lista.every(esEstimada)
          return (
            <button
              key={iso}
              onClick={() => onElegirDia(iso)}
              aria-label={`${d.format('D [de] MMMM')}: ${lista.length} eventos`}
              aria-pressed={elegido}
              className={`relative min-h-[44px] rounded-lg flex flex-col items-center justify-start pt-1 gap-1 transition-[background-color,transform] duration-150 active:scale-95 ${
                elegido ? 'bg-app-accent-soft ring-1 ring-app-accent' : 'hover:bg-white/5'
              } ${estimado ? 'border border-dashed border-app-warn/60' : ''} ${delMes ? '' : 'opacity-35'}`}
            >
              <span className={`font-mono tabular-nums text-caption ${
                iso === hoy ? 'w-6 h-6 rounded-full bg-app-accent text-white flex items-center justify-center' : pasado ? 'text-app-text-faint' : 'text-app-text'
              }`}>
                {d.date()}
              </span>
              {lista.length > 0 && (
                <span className={`flex items-center gap-0.5 ${pasado ? 'opacity-60' : ''}`}>
                  {lista.slice(0, lista.length > MAX_PUNTOS ? MAX_PUNTOS - 1 : MAX_PUNTOS).map(e => (
                    <span key={e.id} className="w-1.5 h-1.5 rounded-full" style={{ background: COLOR_CATEGORIA[e.categoria] }} />
                  ))}
                  {lista.length > MAX_PUNTOS && <span className="text-label leading-none font-bold text-app-text-dim">+{lista.length - (MAX_PUNTOS - 1)}</span>}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
