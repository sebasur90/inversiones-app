import type { EvolucionPunto, InversionesResumen } from '../../api'
import { formatPctRatio } from '../../utils'
import { avisoRendimiento } from '../../utils/avisosCalculo'
import AvisoCalculo from './AvisoCalculo'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { Icon } from '../icons/Icons'
import Sparkline from '../charts/Sparkline'
import InfoTooltip from '../../help/components/InfoTooltip'

export default function HeroValorCard({
  resumen,
  moneda,
  evolucion,
}: {
  resumen: InversionesResumen | null
  moneda: 'USD' | 'ARS'
  evolucion: EvolucionPunto[]
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

  return (
    <div className="bg-gradient-to-br from-app-surface to-app-surface-2 border border-app-border rounded-[18px] p-[18px] mb-3.5">
      <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-1.5">Valor actual</div>
      <div className="font-mono text-hero font-semibold tracking-tight tabular-nums text-app-text">
        {resumen ? fmt.monto(valorActual) : '—'}
      </div>
      {!esARS && resumen && <div className="font-mono text-caption text-app-text-dim mt-0.5 tabular-nums">≈ {fmtArs.monto(resumen.valor_actual_ars)}</div>}

      {resumen && (rendimiento != null || aviso) && (
        <div className="mt-2.5">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
            <InfoTooltip term="simple" label="Rendimiento total" />
          </div>
          <div className="flex items-center gap-2">
            {rendimiento != null ? (
              <span
                className={`inline-flex items-center gap-0.5 font-mono font-bold text-caption px-2 py-1 rounded-lg tabular-nums ${
                  positivo ? 'text-app-pos bg-app-pos-soft' : 'text-app-neg bg-app-neg-soft'
                }`}
              >
                <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
                {formatPctRatio(rendimiento)}
              </span>
            ) : (
              <span className="font-mono font-bold text-caption text-app-text-dim">—</span>
            )}
            {deltaAbs != null && (
              <span className="font-mono text-label text-app-text-dim tabular-nums">
                {fmt.montoConSigno(deltaAbs)} ganancia total
              </span>
            )}
          </div>
          <AvisoCalculo mensajes={[aviso]} />
        </div>
      )}

      <Sparkline data={serie} color={positivo ? '#10b981' : '#ef4444'} className="w-full h-13 mt-2.5" />
    </div>
  )
}
