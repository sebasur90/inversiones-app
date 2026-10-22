import { Link } from 'react-router-dom'
import type { EvolucionPunto, InversionesResumen } from '../../api'
import { formatPctRatio, type PeriodoEvolucion } from '../../utils'
import { avisoRendimiento } from '../../utils/avisosCalculo'
import { mayoresMovimientos, resultadoDelPeriodo, type VariacionDiaCartera } from '../../utils/resumenCartera'
import AvisoCalculo from './AvisoCalculo'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { Icon } from '../icons/Icons'
import Sparkline from '../charts/Sparkline'
import InfoTooltip from '../../help/components/InfoTooltip'

export type PeriodoHero = Extract<PeriodoEvolucion, '1M' | '3M' | '1Y' | 'ALL'>

const PERIODOS: { value: PeriodoHero; label: string; texto: string }[] = [
  { value: '1M', label: '1M', texto: 'en 1 mes' },
  { value: '3M', label: '3M', texto: 'en 3 meses' },
  { value: '1Y', label: '1A', texto: 'en 1 año' },
  { value: 'ALL', label: 'Todo', texto: 'desde el inicio' },
]

const tonoDe = (v: number) => (v > 0 ? 'text-app-pos' : v < 0 ? 'text-app-neg' : 'text-app-text-dim')

export default function HeroValorCard({
  resumen,
  moneda,
  evolucion,
  periodo,
  onPeriodo,
  cargandoSerie = false,
  variacionDia,
}: {
  resumen: InversionesResumen | null
  moneda: 'USD' | 'ARS'
  /** La serie del período elegido, no la histórica entera. */
  evolucion: EvolucionPunto[]
  periodo: PeriodoHero
  onPeriodo: (p: PeriodoHero) => void
  cargandoSerie?: boolean
  variacionDia: VariacionDiaCartera | null
}) {
  const esARS = moneda === 'ARS'
  const valorActual = esARS ? resumen?.valor_actual_ars : resumen?.valor_actual_usd
  const totalInvertido = esARS ? resumen?.total_invertido_ars : resumen?.total_invertido_usd
  const rendimiento = esARS ? resumen?.rendimiento_simple_ars : resumen?.rendimiento_simple_usd
  const fmt = useFormatoFijo(moneda)
  // El equivalente en pesos de la línea secundaria: va siempre en ARS, pase lo que pase arriba.
  const fmtArs = useFormatoFijo('ARS')
  const ingresos = esARS ? resumen?.ingresos_recibidos_ars : resumen?.ingresos_recibidos_usd
  // Misma cuenta que el numerador del %: valor + lo cobrado (dividendos/cupones) − lo invertido.
  // Sin sumar los ingresos, el monto y el % de al lado contaban historias distintas.
  const deltaAbs =
    valorActual != null && totalInvertido != null ? valorActual + (ingresos ?? 0) - totalInvertido : null
  const aviso = avisoRendimiento(resumen?.rendimiento_no_calculable, esARS ? 'ars' : 'usd')
  const positivo = (rendimiento ?? deltaAbs ?? 0) >= 0

  const serie = evolucion.map(p => (esARS ? p.valor_ars : p.valor_usd))
  const textoPeriodo = PERIODOS.find(p => p.value === periodo)?.texto ?? ''
  // "Desde el inicio" ya tiene su cuenta arriba (con lo cobrado); el resto sale de la serie y
  // descuenta los aportes del tramo, para que meter plata no se lea como ganarla.
  const resultado = periodo === 'ALL' ? deltaAbs : resultadoDelPeriodo(evolucion, moneda)
  const colorSerie = (resultado ?? (serie.length > 1 ? serie[serie.length - 1] - serie[0] : 0)) >= 0 ? '#10b981' : '#ef4444'

  // La frase: la respuesta a "¿cómo voy?" sin tener que leer los números.
  const { suben, bajan } = variacionDia ? mayoresMovimientos(variacionDia.movimientos) : { suben: [], bajan: [] }
  const lideres = variacionDia && variacionDia.monto >= 0 ? suben : bajan
  const nombresLideres = lideres.map(l => l.ticker)
  const cualitativo = variacionDia ? Math.abs(variacionDia.pct) < 0.0005 : false

  return (
    <section
      aria-label="Valor de la cartera"
      className="bg-gradient-to-br from-app-surface to-app-surface-2 border border-app-border rounded-[18px] p-[18px] mb-3.5"
    >
      <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-1.5">Valor actual</div>
      <div className="font-mono text-hero font-semibold tracking-tight tabular-nums text-app-text">
        {resumen ? fmt.monto(valorActual) : '—'}
      </div>
      {!esARS && resumen && <div className="font-mono text-caption text-app-text-dim mt-0.5 tabular-nums">≈ {fmtArs.monto(resumen.valor_actual_ars)}</div>}

      {resumen && (
        <div className="grid grid-cols-2 gap-2 mt-3.5">
          <div className="bg-app-surface-2 rounded-xl px-3 py-2.5">
            <div className="text-caption text-app-text-dim mb-0.5">Último día</div>
            {variacionDia ? (
              <div className="flex items-baseline gap-1.5 flex-wrap">
                <span className={`inline-flex items-center gap-0.5 font-mono text-strong font-bold tabular-nums ${tonoDe(variacionDia.pct)}`}>
                  {Math.abs(variacionDia.pct) >= 0.0005 && (
                    <Icon name={variacionDia.pct > 0 ? 'up' : 'down'} className="w-3 h-3" />
                  )}
                  {formatPctRatio(variacionDia.pct)}
                </span>
                <span className="font-mono text-label text-app-text-dim tabular-nums">{fmt.montoConSigno(variacionDia.monto)}</span>
              </div>
            ) : (
              <span
                className="font-mono text-strong font-bold text-app-text-dim"
                title="Ninguna posición tiene todavía un precio del día anterior para comparar"
              >
                —
              </span>
            )}
          </div>

          <div className="bg-app-surface-2 rounded-xl px-3 py-2.5">
            <div className="text-caption text-app-text-dim mb-0.5">
              <InfoTooltip term="simple" label="Desde el inicio" />
            </div>
            {rendimiento != null ? (
              <div className="flex items-baseline gap-1.5 flex-wrap">
                <span
                  className={`inline-flex items-center gap-0.5 font-mono text-strong font-bold tabular-nums ${
                    positivo ? 'text-app-pos' : 'text-app-neg'
                  }`}
                >
                  <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
                  {formatPctRatio(rendimiento)}
                </span>
                {deltaAbs != null && (
                  <span className="font-mono text-label text-app-text-dim tabular-nums">{fmt.montoConSigno(deltaAbs)}</span>
                )}
              </div>
            ) : (
              <span className="font-mono text-strong font-bold text-app-text-dim">—</span>
            )}
          </div>
        </div>
      )}
      {resumen && variacionDia && variacionDia.conDato < variacionDia.total && (
        <div className="text-label text-app-text-faint mt-1.5">
          El último día se calcula con {variacionDia.conDato} de {variacionDia.total} posiciones: el resto no tiene precio del día anterior.
        </div>
      )}
      <AvisoCalculo mensajes={[aviso]} />

      <div className="mt-3">
        <div role="img" aria-label={`Evolución del valor de la cartera ${textoPeriodo}`} className={cargandoSerie ? 'opacity-50 transition-opacity duration-200' : 'transition-opacity duration-200'}>
          <Sparkline data={serie} color={colorSerie} className="w-full h-13" />
        </div>
        <div className="flex items-center justify-between gap-2 mt-2">
          <div role="group" aria-label="Período del gráfico" className="flex gap-1">
            {PERIODOS.map(p => (
              <button
                key={p.value}
                onClick={() => onPeriodo(p.value)}
                aria-pressed={periodo === p.value}
                className={`min-w-11 min-h-9 px-2 rounded-lg font-mono text-caption font-semibold text-center transition-[background-color,color,transform] duration-150 active:scale-95 ${
                  periodo === p.value ? 'bg-app-accent-soft text-app-accent' : 'text-app-text-dim hover:text-app-text hover:bg-white/5'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {resultado != null && (
            <span className={`font-mono text-caption font-semibold tabular-nums ${tonoDe(resultado)}`}>
              {fmt.montoConSigno(resultado)}
            </span>
          )}
        </div>
        {resultado != null && (
          <div className="text-label text-app-text-faint mt-1">
            Ganancia {textoPeriodo}{periodo === 'ALL' ? '' : ', sin contar tus aportes'}
          </div>
        )}
      </div>

      {resumen && (rendimiento != null || (variacionDia && !cualitativo)) && (
        <div className="border-t border-app-border mt-3.5 pt-3.5">
          <p className="text-strong leading-relaxed text-app-text">
            {rendimiento != null && (
              <>
                Vas {rendimiento >= 0 ? 'ganando' : 'perdiendo'}{' '}
                <strong className={`font-semibold ${rendimiento >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                  {fmt.ocultos || deltaAbs == null
                    ? `un ${formatPctRatio(Math.abs(rendimiento)).replace('+', '')}`
                    : `${fmt.monto(Math.abs(deltaAbs))} (${formatPctRatio(Math.abs(rendimiento)).replace('+', '')})`}
                </strong>{' '}
                sobre lo que pusiste.{' '}
              </>
            )}
            {variacionDia && (
              cualitativo ? (
                <>El último día casi no se movió.</>
              ) : (
                <>
                  El último día {variacionDia.pct > 0 ? 'sube' : 'baja'} {formatPctRatio(Math.abs(variacionDia.pct)).replace('+', '')}
                  {nombresLideres.length > 0 && (
                    <>
                      , {variacionDia.pct > 0 ? 'empujada' : 'arrastrada'} por{' '}
                      <strong className="font-semibold">{nombresLideres.join(' y ')}</strong>
                    </>
                  )}
                  .
                </>
              )
            )}
          </p>
          <Link
            to="/explicacion-resultado"
            className="inline-flex items-center gap-1 min-h-9 mt-1 text-body font-semibold text-app-accent"
          >
            ¿Por qué ganó o perdió?
            <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90" />
          </Link>
        </div>
      )}
    </section>
  )
}
