import type { InversionesResumen, PerformanceRelativaOut } from '../../api'
import { formatPctRatio } from '../../utils'
import { formatMonedaCruda } from '../../utils/formatoMonto'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import AvisoCalculo from '../inversiones/AvisoCalculo'
import MetricTile from '../ui/MetricTile'

function tono(v: number | null | undefined): 'pos' | 'neg' | undefined {
  if (v == null) return undefined
  return v >= 0 ? 'pos' : 'neg'
}

/**
 * Lo primero que se ve: cuánto rindió la cartera, dicho en palabras. El número grande es el TWR
 * (el rendimiento de las decisiones, sin que el momento de los aportes lo distorsione); la TIR y la
 * ganancia total van debajo como lectura complementaria.
 */
export default function RendimientoHero({
  resumen,
  totalPnl,
  perfRelativa,
  esARS,
}: {
  resumen: InversionesResumen
  totalPnl: number | null
  perfRelativa: PerformanceRelativaOut | null
  esARS: boolean
}) {
  const { monto, moneda } = useFormatoMoneda()

  const twr = esARS ? resumen.twr_ars : resumen.twr_usd
  const twrReal = esARS ? resumen.twr_ars_real : null
  const anualizada = esARS ? resumen.xirr_ars : resumen.xirr_usd
  const extrapolada = resumen.dias_periodo > 0 && resumen.dias_periodo < 365
  const motivo = resumen.rendimiento_no_calculable?.[esARS ? 'ars' : 'usd']

  // Cien unidades de referencia, no un importe del usuario: no se tapa con el modo privacidad.
  const referencia = formatMonedaCruda(100, moneda)
  const ganado = twr != null ? formatMonedaCruda(Math.abs(twr) * 100, moneda) : null

  const hayBenchmark = perfRelativa?.estado === 'ok' && perfRelativa.delta_pp != null
  const delta = hayBenchmark ? perfRelativa!.delta_pp! : null

  return (
    <section aria-label="Resumen del rendimiento" className="bg-app-surface border border-app-border rounded-2xl p-5 mb-5 flex flex-col gap-3.5">
      <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">Tu cartera rindió</div>

      {twr == null ? (
        <p className="text-body text-app-text-dim">
          Todavía no se puede calcular el rendimiento de esta cartera en {esARS ? 'pesos' : 'dólares'}.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div className={`font-mono text-display leading-none font-bold tabular-nums ${twr >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
            {formatPctRatio(twr)}
          </div>
          <p className="text-strong text-app-text-dim">
            Por cada {referencia} que tuviste invertidos, {twr >= 0 ? 'ganaste' : 'perdiste'}{' '}
            <span className="font-semibold text-app-text">{ganado}</span>. Mide tus decisiones, no cuándo pusiste la plata.
          </p>
        </div>
      )}

      {twrReal != null && (
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-[10px] bg-app-pos-soft text-body text-app-text">
          <span>
            Descontando la inflación:{' '}
            <strong className={`font-mono tabular-nums ${twrReal >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>{formatPctRatio(twrReal)}</strong>
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <MetricTile label="Ganancia total" infoTerm="realizado" value={monto(totalPnl)} tone={tono(totalPnl)} />
        <MetricTile
          label={extrapolada ? 'A un año (estimado)' : 'Llevado a un año'}
          infoTerm="xirr"
          value={formatPctRatio(anualizada)}
          tone={tono(anualizada)}
        />
      </div>

      {delta != null && (
        <div className="flex items-center gap-2 pt-3 border-t border-app-border text-body text-app-text-dim">
          {/* Diferencia en puntos porcentuales, no un porcentaje. */}
          <span className={`font-mono font-bold text-caption px-1.5 py-0.5 rounded-md tabular-nums ${delta >= 0 ? 'bg-app-pos-soft text-app-pos' : 'bg-app-neg-soft text-app-neg'}`}>
            {delta >= 0 ? '+' : '−'}{Math.abs(delta).toFixed(1)} pp
          </span>
          <span>
            {delta >= 0 ? 'Superaste a' : 'Quedaste por debajo de'} {perfRelativa!.benchmark_usado}.
          </span>
        </div>
      )}

      {extrapolada && anualizada != null && (
        <div className="text-label text-app-text-faint">
          La cifra anual extrapola tus {resumen.dias_periodo} días de historial a 12 meses: con poco tiempo puede verse exagerada.
        </div>
      )}
      <AvisoCalculo className="" mensajes={[motivo]} />
    </section>
  )
}
