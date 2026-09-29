import type { OperacionOut } from '../../api'
import BotonExportarCsv from '../ui/BotonExportarCsv'
import { DESCRIPCION_MOTIVO, etiquetaMotivo } from './motivosSalida'

function formatPctSigned(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

/** Tabla de operaciones de un backtest, con export CSV y la leyenda de los motivos de salida que
 * efectivamente aparecieron. Compartida por `ResultadoBacktest` (Análisis técnico) y
 * `DetalleEstrategiaBacktest` (Comparador de estrategias): antes vivía duplicada en la primera. */
export default function TablaOperaciones({ ticker, operaciones }: { ticker: string; operaciones: OperacionOut[] }) {
  const motivosUsados = Array.from(
    new Set(operaciones.map(o => o.motivo_salida).filter((x): x is string => !!x)),
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="font-semibold text-caption text-app-text">Operaciones ({operaciones.length})</div>
        {operaciones.length > 0 && (
          <BotonExportarCsv
            nombre={`backtest-${ticker}`}
            encabezados={['Entrada', 'Salida', 'Precio entrada', 'Precio salida', 'Barras', 'Retorno neto %', 'Motivo salida', 'Abierta']}
            filas={() => operaciones.map(o => [
              o.fecha_entrada, o.fecha_salida ?? '', o.precio_entrada, o.precio_salida ?? '', o.barras,
              Number(o.retorno_neto_pct.toFixed(4)), o.motivo_salida ? etiquetaMotivo(o.motivo_salida) : '', o.abierta ? 'sí' : 'no',
            ])}
          />
        )}
      </div>
      <div className="overflow-x-auto -mx-4 px-4">
        <table className="w-full text-caption">
          <thead>
            <tr className="text-label text-app-text-faint uppercase text-left">
              <th className="py-1 pr-2 font-semibold">Entrada</th>
              <th className="py-1 pr-2 font-semibold">Salida</th>
              <th className="py-1 pr-2 font-semibold text-right">Retorno neto</th>
              <th className="py-1 pr-2 font-semibold">Motivo</th>
            </tr>
          </thead>
          <tbody>
            {operaciones.map((o, i) => (
              <tr key={i} className="border-t border-app-border-soft">
                <td className="py-1.5 pr-2 font-mono whitespace-nowrap">{o.fecha_entrada}</td>
                <td className="py-1.5 pr-2 font-mono whitespace-nowrap">{o.fecha_salida ?? (o.abierta ? 'Abierta' : '—')}</td>
                <td className={`py-1.5 pr-2 text-right font-mono tabular-nums ${o.retorno_neto_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                  {formatPctSigned(o.retorno_neto_pct)}
                </td>
                <td className="py-1.5 pr-2 text-app-text-dim">{etiquetaMotivo(o.motivo_salida)}</td>
              </tr>
            ))}
            {operaciones.length === 0 && (
              <tr><td colSpan={4} className="py-3 text-app-text-dim text-center">Sin operaciones en el rango</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {motivosUsados.length > 0 && (
        <div className="mt-2 text-label text-app-text-dim space-y-0.5">
          {motivosUsados.map(m => (
            <div key={m}>
              <span className="text-app-text font-semibold">{etiquetaMotivo(m)}</span>: {DESCRIPCION_MOTIVO[m] ?? '—'}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
