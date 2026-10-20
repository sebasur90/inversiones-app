import type { CicloPosicionOut, OperacionPropiaOut, OperacionesGraficoOut } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { colorResultado } from './operacionesPropias'
import { fechaCorta, formatoPct } from './formatoEjes'

const promedio = (valores: (number | null)[]): number | null => {
  const v = valores.filter((x): x is number => x != null)
  return v.length > 0 ? v.reduce((a, b) => a + b, 0) / v.length : null
}

/** Qué pasó con el precio después de la última venta de un ciclo cerrado: lo que habrías ganado o
 * perdido de no haber vendido. Prefiere los 90 días y, si todavía no pasaron, usa los 30. `null`
 * en `valor` = todavía no pasaron ni 30 días (una venta reciente): se avisa en vez de callar.
 * `undefined` = el ciclo sigue abierto, no hay nada que decir. */
function despuesDeVender(
  c: CicloPosicionOut, ops: OperacionPropiaOut[],
): { valor: number | null; dias: number; sinSerie?: boolean } | undefined {
  if (c.abierto) return undefined
  const ventas = ops.filter(o => o.ciclo === c.ciclo && o.tipo === 'venta')
  const ultima = ventas[ventas.length - 1]
  if (!ultima) return undefined
  // La venta cae antes del inicio del gráfico: no hay velas para medir qué pasó después. Sin esto se
  // decía "todavía no pasaron 30 días" para una venta de hace años.
  if (ultima.fecha_barra == null) return { valor: null, dias: 30, sinSerie: true }
  if (ultima.post_90_pct != null) return { valor: ultima.post_90_pct, dias: 90 }
  if (ultima.post_30_pct != null) return { valor: ultima.post_30_pct, dias: 30 }
  return { valor: null, dias: 30 }
}

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

  const compras = datos.operaciones.filter(o => o.tipo === 'compra')
  const rsiMedio = promedio(compras.map(o => o.rsi))
  const distMedia = promedio(compras.map(o => o.dist_sma200_pct))

  return (
    <div className="flex flex-col gap-2">
      <span className="text-label font-bold text-app-text-dim uppercase">Mis posiciones</span>

      <div className="flex flex-col divide-y divide-app-border rounded-xl bg-app-surface-2">
        {[...datos.ciclos].reverse().map(c => {
          const color = colorResultado(c.resultado_usd)
          const despues = despuesDeVender(c, datos.operaciones)
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
                {despues != null && (
                  <div className="text-label text-app-text-dim font-mono tabular-nums">
                    {despues.valor != null ? (
                      <>
                        Si no vendías: <span className={despues.valor >= 0 ? 'text-app-pos' : 'text-app-neg'}>{formatoPct(despues.valor)}</span> a {despues.dias} días
                      </>
                    ) : despues.sinSerie ? (
                      'Si no vendías: sin dato (la venta es anterior al inicio del gráfico)'
                    ) : (
                      'Si no vendías: todavía no pasaron 30 días'
                    )}
                  </div>
                )}
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

      {(rsiMedio != null || distMedia != null) && (
        <p className="text-label text-app-text-dim">
          Compraste en promedio
          {rsiMedio != null && <> con RSI <span className="font-mono">{rsiMedio.toFixed(0)}</span></>}
          {rsiMedio != null && distMedia != null && ','}
          {distMedia != null && <> a <span className="font-mono">{formatoPct(distMedia)}</span> de la SMA200</>}.
        </p>
      )}

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
