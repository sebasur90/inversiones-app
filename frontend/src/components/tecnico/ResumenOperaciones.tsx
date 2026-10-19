import type { OperacionesGraficoOut } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { colorResultado } from './operacionesPropias'
import { fechaCorta, formatoPct } from './formatoEjes'

/**
 * Las posiciones que tuviste en este ticker, una fila por ciclo (de 0 a volver a 0), con lo que
 * ganaste o perdiste. Es el mismo resultado que el P&L de la app: en USD MEP, con comisiones y
 * costo promedio. Debajo del gráfico, junto a las zonas.
 */
export default function ResumenOperaciones({ datos }: { datos: OperacionesGraficoOut }) {
  const fmt = useFormatoFijo('USD')

  if (datos.ciclos.length === 0) {
    return (
      <p className="text-label text-app-text-dim">
        No tenés compras ni ventas registradas de este ticker.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-label font-bold text-app-text-dim uppercase">Mis posiciones</span>

      <div className="flex flex-col divide-y divide-app-border rounded-xl bg-app-surface-2">
        {[...datos.ciclos].reverse().map(c => {
          const color = colorResultado(c.resultado_usd)
          return (
            <div key={c.ciclo} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="text-caption text-app-text font-mono tabular-nums">
                  {fechaCorta(c.desde)} → {c.abierto ? 'abierta' : fechaCorta(c.hasta ?? undefined)}
                </div>
                <div className="text-label text-app-text-dim font-mono tabular-nums">
                  Comprado {fmt.monto(c.comprado_usd)}
                  {c.abierto && ` · hoy ${c.cantidad_abierta} u.`}
                </div>
              </div>
              <div className="shrink-0 text-right font-mono tabular-nums" style={{ color }}>
                <div className="text-caption font-semibold">
                  {c.resultado_usd != null ? fmt.montoConSigno(c.resultado_usd) : '—'}
                </div>
                <div className="text-label">
                  {c.resultado_pct != null ? formatoPct(c.resultado_pct) : 'sin precio actual'}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-label text-app-text-dim">
        Resultado real en USD (MEP de cada fecha), con comisiones. En un CEDEAR, las marcas ubican
        tu precio en pesos sobre la vela del subyacente de ese día: sirven para ver el momento, no
        son el precio exacto en dólares.
      </p>
      {datos.fuera_de_serie > 0 && (
        <p className="text-label text-app-text-dim">
          {datos.fuera_de_serie === 1 ? '1 operación es anterior' : `${datos.fuera_de_serie} operaciones son anteriores`}{' '}
          al inicio del gráfico y no se dibuja{datos.fuera_de_serie === 1 ? '' : 'n'}.
        </p>
      )}
      {datos.advertencias.includes('costo_incompleto') && (
        <p className="text-label text-app-text-dim">
          Falta el tipo de cambio de alguna fecha: el resultado de esa posición puede estar incompleto.
        </p>
      )}
    </div>
  )
}
