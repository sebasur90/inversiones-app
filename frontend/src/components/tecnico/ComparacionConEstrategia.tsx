import type { CicloVsEstrategiaOut } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import InfoTooltip from '../../help/components/InfoTooltip'
import { colorResultado } from './operacionesPropias'
import { fechaCorta, formatoPct } from './formatoEjes'

/**
 * "Vos vs. la estrategia vs. comprar y mantener": una fila por posición que tuviste de este ticker
 * dentro del período del backtest, con lo que te dio a vos, lo que habría dado la estrategia entre
 * las mismas dos fechas y lo que habría dado comprar y mantener. El resultado tuyo es el real (USD
 * MEP, con comisiones; el monto pasa por el modo privacidad, el porcentaje no); los otros dos salen
 * de las curvas del backtest sobre el precio de la serie.
 */
export default function ComparacionConEstrategia({ ciclos }: { ciclos: CicloVsEstrategiaOut[] }) {
  const fmt = useFormatoFijo('USD')

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase">
        Vos vs. la estrategia vs. comprar y mantener
        <InfoTooltip term="backtest_vos_vs_estrategia" />
      </div>

      {ciclos.length === 0 ? (
        <p className="text-label text-app-text-dim">
          Operaste este ticker, pero ninguna de tus posiciones cae dentro del período de este backtest.
        </p>
      ) : (
        <>
          <div className="flex flex-col divide-y divide-app-border rounded-xl bg-app-surface-2">
            {[...ciclos].reverse().map(c => (
              <div key={c.ciclo} className="px-3 py-2.5">
                <div className="flex items-baseline justify-between gap-2 mb-1.5">
                  <span className="text-caption text-app-text font-mono tabular-nums">
                    {fechaCorta(c.desde)} → {c.abierto ? 'abierta' : fechaCorta(c.hasta ?? undefined)}
                  </span>
                  {c.recortado && (
                    <span className="text-label text-app-text-faint" title="La posición empezó antes del período del backtest: tu resultado cuenta toda la posición; el de la estrategia, sólo desde que arranca el período.">
                      empezó antes del período
                    </span>
                  )}
                  {c.recortado_fin && (
                    <span className="text-label text-app-text-faint" title="La posición sigue (o terminó) después de la última fecha del backtest: tu resultado cuenta hasta hoy o hasta tu venta; el de la estrategia, sólo hasta el fin del período.">
                      sigue después del período
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2 font-mono tabular-nums">
                  <Celda
                    etiqueta="Vos" valor={c.tu_resultado_pct} color={colorResultado(c.tu_resultado_usd)}
                    sub={c.tu_resultado_usd != null ? fmt.montoConSigno(c.tu_resultado_usd) : undefined}
                  />
                  <Celda etiqueta="Estrategia" valor={c.estrategia_pct} color={colorResultado(c.estrategia_pct)} />
                  <Celda etiqueta="Comprar y mantener" valor={c.buy_hold_pct} color={colorResultado(c.buy_hold_pct)} />
                </div>
              </div>
            ))}
          </div>
          <p className="text-label text-app-text-dim">
            Lo tuyo es el resultado real en USD MEP, con comisiones; la estrategia y comprar y mantener
            se miden sobre el precio de la serie del backtest entre las mismas fechas. Una estrategia
            que no estaba comprada en ese tramo rinde 0 %.
          </p>
        </>
      )}
    </div>
  )
}

function Celda({ etiqueta, valor, color, sub }: { etiqueta: string; valor: number | null; color: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-label text-app-text-dim font-sans truncate">{etiqueta}</div>
      <div className="text-caption font-semibold" style={{ color }}>{valor != null ? formatoPct(valor) : '—'}</div>
      {sub && <div className="text-label" style={{ color }}>{sub}</div>}
    </div>
  )
}
