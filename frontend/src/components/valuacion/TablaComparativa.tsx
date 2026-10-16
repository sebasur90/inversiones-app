import { Fragment } from 'react'
import type { TablaComparador } from '../../api'
import { ComparabilidadBadge, NOMBRE_GRUPO, OrigenTag, fechaCorta, textoCelda } from './comun'

const GRUPOS = ['valuacion', 'calidad', 'crecimiento', 'momentum'] as const

/**
 * Tabla lado a lado: una columna por instrumento, una fila por métrica pertinente al sector. Cada fila
 * dice su unidad y el período al que se refiere el dato; lo que no hay se distingue de lo que no aplica.
 * ▲ / ▼ marcan el mejor y el peor valor de la fila entre los que entran al ranking (en valuación, el
 * más barato / el más caro).
 */
export default function TablaComparativa({ tabla }: { tabla: TablaComparador }) {
  const { columnas, filas } = tabla
  return (
    <div>
      <div className="overflow-x-auto -mx-4 px-4">
        <table className="text-caption border-separate border-spacing-0">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-app-surface text-left font-semibold text-app-text-dim pr-3 py-1.5 align-bottom">Métrica</th>
              {columnas.map(c => (
                <th key={c.ticker_base} className={`text-right px-2 py-1.5 align-bottom whitespace-nowrap ${c.en_ranking ? '' : 'opacity-70'}`}>
                  <div className={`font-mono font-bold ${c.es_objetivo ? 'text-app-accent' : 'text-app-text-dim'}`}>{c.ticker_base}</div>
                  <div className="flex justify-end">
                    {c.es_objetivo
                      ? <span className="text-label text-app-text-faint">este</span>
                      : c.nivel && <ComparabilidadBadge nivel={c.nivel} corto />}
                  </div>
                  {!c.en_ranking && <div className="text-label text-app-text-faint">no cuenta</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {GRUPOS.map(grupo => {
              const del = filas.filter(f => f.grupo === grupo)
              if (del.length === 0) return null
              return (
                <Fragment key={grupo}>
                  <tr>
                    <td colSpan={columnas.length + 1} className="sticky left-0 text-label font-bold uppercase text-app-text-dim pt-3 pb-1">
                      {NOMBRE_GRUPO[grupo]}
                    </td>
                  </tr>
                  {del.map(f => (
                    <tr key={f.clave}>
                      <td className="sticky left-0 z-10 bg-app-surface pr-3 py-1.5 border-t border-app-border-soft min-w-[130px]">
                        <div className="text-app-text whitespace-nowrap flex items-center gap-1.5">
                          {f.nombre}
                          {columnas[0] && f.celdas[columnas[0].ticker_base]?.origen !== 'observado' && (
                            <OrigenTag origen={f.celdas[columnas[0].ticker_base].origen} />
                          )}
                        </div>
                        <div className="text-label text-app-text-faint whitespace-nowrap">
                          {f.unidad} · {f.periodo}{f.solo_apoya ? ' · suma, no decide' : ''}
                        </div>
                      </td>
                      {columnas.map(c => {
                        const celda = f.celdas[c.ticker_base]
                        const mejor = f.mejor === c.ticker_base
                        const peor = f.peor === c.ticker_base
                        return (
                          <td
                            key={c.ticker_base}
                            className={`text-right font-mono px-2 py-1.5 border-t border-app-border-soft whitespace-nowrap ${
                              celda.estado !== 'dato' ? 'text-app-text-faint'
                              : mejor ? 'text-app-pos font-bold' : peor ? 'text-app-neg font-bold'
                              : c.es_objetivo ? 'text-app-text font-bold' : 'text-app-text-dim'
                            }`}
                            title={mejor ? (f.grupo === 'valuacion' ? 'El más barato del grupo' : 'El mejor del grupo')
                              : peor ? (f.grupo === 'valuacion' ? 'El más caro del grupo' : 'El peor del grupo') : undefined}
                          >
                            {celda.estado !== 'dato' ? <span className="font-sans text-label">{textoCelda(celda, f.formato)}</span> : textoCelda(celda, f.formato)}
                            {mejor && <span aria-label="mejor"> ▲</span>}
                            {peor && <span aria-label="peor"> ▼</span>}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </Fragment>
              )
            })}
            <tr>
              <td className="sticky left-0 z-10 bg-app-surface pr-3 py-1.5 border-t border-app-border text-label text-app-text-faint">Datos bajados</td>
              {columnas.map(c => (
                <td key={c.ticker_base} className="text-right px-2 py-1.5 border-t border-app-border text-label text-app-text-faint whitespace-nowrap">{fechaCorta(c.fecha_dato)}</td>
              ))}
            </tr>
            <tr>
              <td className="sticky left-0 z-10 bg-app-surface pr-3 py-1.5 text-label text-app-text-faint">Último balance</td>
              {columnas.map(c => (
                <td key={c.ticker_base} className="text-right px-2 py-1.5 text-label text-app-text-faint whitespace-nowrap">{fechaCorta(c.periodo_contable)}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-label text-app-text-faint mt-2">
        ▲ mejor valor de la fila (en valuación, el más barato) · ▼ el peor. Se marcan sólo entre los que cuentan para el ranking.
      </p>
      {tabla.no_aplican.length > 0 && (
        <div className="mt-2">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">No aplican a este tipo de instrumento</div>
          <ul className="flex flex-col gap-0.5">
            {tabla.no_aplican.map(n => (
              <li key={n.nombre} className="text-caption text-app-text-dim"><span className="text-app-text font-semibold">{n.nombre}:</span> {n.motivo}.</li>
            ))}
          </ul>
        </div>
      )}
      {tabla.sin_dato_en_ninguna.length > 0 && (
        <p className="text-caption text-app-text-dim mt-2">
          Ninguno tiene dato de: {tabla.sin_dato_en_ninguna.join(', ')}.
        </p>
      )}
    </div>
  )
}
