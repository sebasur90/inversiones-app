import { useState } from 'react'
import type { InversionesResumen } from '../../api'
import { formatPctRatio } from '../../utils'
import { Icon } from '../icons/Icons'
import Modal from '../ui/Modal'
import Segmented from '../ui/Segmented'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'

type Medida = 'usd' | 'ars' | 'real'

const OPCIONES: { value: Medida; label: string }[] = [
  { value: 'usd', label: 'Dólares' },
  { value: 'ars', label: 'Pesos' },
  { value: 'real', label: 'Pesos reales' },
]

type Trio = [number | null | undefined, number | null | undefined, number | null | undefined]

interface Fila {
  label: string
  desc: string
  infoTerm: HelpKey
  /** Valor en [dólares, pesos, pesos reales]. */
  valores: Trio
  /** Diferencia entre dos rendimientos: se escribe en puntos porcentuales, no en %. */
  enPp?: boolean
}

function diff(a: number | null | undefined, b: number | null | undefined): number | null {
  return a != null && b != null ? a - b : null
}

function formatPp(v: number | null | undefined): string {
  if (v == null) return '—'
  const redondeado = Number((v * 100).toFixed(2)) + 0
  return `${redondeado >= 0 ? '+' : ''}${redondeado.toFixed(2)} pp`
}

function tono(v: number | null | undefined): string {
  if (v == null) return 'text-app-text-faint'
  return v >= 0 ? 'text-app-pos' : 'text-app-neg'
}

/**
 * Las siete formas de medir el rendimiento, que antes eran una tabla de cuatro columnas que no
 * entraba en el teléfono. Acá se elige la moneda y se lee una sola columna, agrupadas por para qué
 * sirve cada una: compararte con un índice (TWR) o ver lo que ganó tu plata (TIR).
 */
export default function MetricasDetalladas({ resumen, medidaInicial }: { resumen: InversionesResumen; medidaInicial: Medida }) {
  const [abierto, setAbierto] = useState(false)
  const [medida, setMedida] = useState<Medida>(medidaInicial)
  const i = { usd: 0, ars: 1, real: 2 }[medida]

  const grupos: { titulo: string; para: string; filas: Fila[] }[] = [
    {
      titulo: 'Para compararte',
      para: 'con un índice',
      filas: [
        {
          label: 'TWR del período', infoTerm: 'twr', desc: 'Cómo rindieron tus decisiones, sin importar cuándo aportaste.',
          valores: [resumen.twr_usd, resumen.twr_ars, resumen.twr_ars_real],
        },
        {
          label: 'TWR sin comisiones', infoTerm: 'twrBruto', desc: 'Lo mismo, como si operar fuera gratis.',
          valores: [resumen.twr_usd_bruto, resumen.twr_ars_bruto, null],
        },
        {
          label: 'Costo de operar', infoTerm: 'costoOperar', desc: 'Lo que te restaron las comisiones y derechos de mercado.', enPp: true,
          valores: [diff(resumen.twr_usd, resumen.twr_usd_bruto), diff(resumen.twr_ars, resumen.twr_ars_bruto), null],
        },
      ],
    },
    {
      titulo: 'Para tu bolsillo',
      para: 'lo que ganó tu plata',
      filas: [
        {
          label: 'TIR del período', infoTerm: 'xirrPeriodo', desc: 'Pesa cuánta plata tenías invertida en cada momento.',
          valores: [resumen.xirr_usd_periodo, resumen.xirr_ars_periodo, resumen.xirr_ars_real_periodo],
        },
        {
          label: 'TIR anualizada', infoTerm: 'xirr', desc: 'La misma TIR llevada a 12 meses.',
          valores: [resumen.xirr_usd, resumen.xirr_ars, resumen.xirr_ars_real],
        },
        {
          label: 'Rendimiento simple', infoTerm: 'simple', desc: 'Ganancia sobre lo que pusiste, sin mirar cuándo.',
          valores: [resumen.rendimiento_simple_usd, resumen.rendimiento_simple_ars, resumen.rendimiento_simple_ars_real],
        },
        {
          label: 'Efecto de tus aportes', infoTerm: 'efectoAportes', desc: 'TIR menos TWR. Positivo: aportaste en buenos momentos.', enPp: true,
          valores: [
            diff(resumen.xirr_usd_periodo, resumen.twr_usd),
            diff(resumen.xirr_ars_periodo, resumen.twr_ars),
            diff(resumen.xirr_ars_real_periodo, resumen.twr_ars_real),
          ],
        },
      ],
    },
  ]

  return (
    <>
      <button
        onClick={() => setAbierto(true)}
        className="w-full flex items-center gap-3 min-h-[60px] px-3.5 py-3 rounded-[13px] bg-app-accent-soft border border-app-accent/30 text-left"
      >
        <Icon name="grid" className="w-5 h-5 text-app-accent shrink-0" />
        <span className="flex-1">
          <span className="block text-body font-bold text-app-text">Métricas detalladas</span>
          <span className="block text-caption text-app-text-dim">TWR, TIR, costo de operar y efecto de tus aportes</span>
        </span>
        <Icon name="chevron" className="w-4 h-4 text-app-accent shrink-0" />
      </button>

      <Modal open={abierto} onClose={() => setAbierto(false)} title="Métricas detalladas">
        <div className="flex flex-col gap-3">
          <Segmented options={OPCIONES} value={medida} onChange={setMedida} />

          {grupos.map(grupo => (
            <div key={grupo.titulo} className="flex flex-col">
              <div className="flex items-baseline justify-between pt-1.5 pb-1">
                <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">{grupo.titulo}</span>
                <span className="text-label text-app-text-faint">{grupo.para}</span>
              </div>
              {grupo.filas.map(fila => {
                const v = fila.valores[i]
                return (
                  <div key={fila.label} className="flex items-start gap-3 py-2.5 border-t border-app-border-soft">
                    <div className="flex-1 min-w-0">
                      <div className="text-body font-semibold text-app-text"><InfoTooltip term={fila.infoTerm} label={fila.label} /></div>
                      <div className="text-caption text-app-text-dim">{fila.desc}</div>
                    </div>
                    <div className={`font-mono text-strong font-bold tabular-nums shrink-0 ${tono(v)}`}>
                      {fila.enPp ? formatPp(v) : formatPctRatio(v)}
                    </div>
                  </div>
                )
              })}
            </div>
          ))}

          {resumen.dias_periodo > 0 && (
            <p className="px-3 py-2.5 rounded-[10px] bg-app-surface-2 text-caption text-app-text-dim">
              «Del período» son los {resumen.dias_periodo} días desde tu primer movimiento. La TIR anualizada lleva ese tramo a 12
              meses, por eso es mucho más grande cuando el historial es corto.
            </p>
          )}
        </div>
      </Modal>
    </>
  )
}
