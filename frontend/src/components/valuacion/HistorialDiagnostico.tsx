import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getBacktestHistorial, getHistorialDiagnostico, type BacktestHistorial, type HistorialItem } from '../../api'
import { qk } from '../../api/queryClient'
import Card from '../ui/Card'
import QueryBoundary from '../ui/QueryBoundary'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'

const NOMBRE_DIMENSION: Record<string, string> = {
  valuacion: 'Valuación', calidad: 'Calidad', crecimiento: 'Crecimiento', solidez: 'Solidez', confianza: 'Confianza',
}
const ORDEN = ['valuacion', 'calidad', 'crecimiento', 'solidez'] as const

const fecha = (iso: string | null) => (iso ? fechaCorta(iso) : '—')
const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`)

function Foto({ item, esLaPrimera }: { item: HistorialItem; esLaPrimera: boolean }) {
  return (
    <li className="border-b border-app-border last:border-b-0 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-caption font-semibold text-app-text">Registrado el {fecha(item.fecha)}</span>
        <span className="text-label text-app-text-faint">dato del {fecha(item.fecha_dato)} · reglas v{item.version_diagnostico}</span>
      </div>
      {item.cambio_de_reglas && (
        <div className="text-label text-app-warn mt-0.5">
          Cambiaron las reglas del diagnóstico: los estados de esta foto no se pueden comparar con los de la anterior.
        </div>
      )}
      {esLaPrimera ? (
        <div className="text-label text-app-text-faint mt-0.5">Primera foto: el punto de partida.</div>
      ) : item.cambios.length > 0 ? (
        <ul className="mt-0.5">
          {item.cambios.map(c => (
            <li key={c.dimension} className="text-caption text-app-text">
              <span className="font-semibold">{NOMBRE_DIMENSION[c.dimension] ?? c.dimension}:</span> {c.de ?? '—'} → <span className="font-semibold">{c.a ?? '—'}</span>
            </li>
          ))}
        </ul>
      ) : !item.cambio_de_reglas ? (
        <div className="text-label text-app-text-faint mt-0.5">Sin cambios de estado (cambió el dato o los pares).</div>
      ) : null}
      <div className="text-label text-app-text-dim mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {ORDEN.map(d => item.estados[d] && item.estados[d].nivel !== 'no_aplica' && (
          <span key={d}>{NOMBRE_DIMENSION[d]}: <span className="text-app-text">{item.estados[d].estado}</span></span>
        ))}
      </div>
    </li>
  )
}

function Backtest({ data }: { data: BacktestHistorial }) {
  const celdas = data.estados.filter(e => Object.values(e.horizontes).some(h => h.suficiente))
  return (
    <div className="rounded-xl border border-app-border p-3 flex flex-col gap-1.5">
      <div className="text-label font-bold uppercase tracking-wide text-app-text-faint flex items-center gap-1">
        ¿Anticiparon algo estos estados? <InfoTooltip term="historial_backtest" label="" />
      </div>
      {!data.suficiente ? (
        <p className="text-caption text-app-text-dim">
          Todavía no hay muestra suficiente: se necesitan al menos {data.minimo_muestra} entradas a un mismo estado con su precio posterior
          (hay {data.eventos_totales} registradas en total). El historial recién empieza a acumularse, así que por ahora no se muestra ningún promedio.
        </p>
      ) : (
        <div className="overflow-x-auto -mx-3 px-3">
          <table className="text-caption w-full">
            <thead>
              <tr className="text-label text-app-text-faint">
                <th className="text-left font-semibold pr-2 pb-1">Estado</th>
                <th className="text-right font-semibold px-1 pb-1">n</th>
                {data.horizontes.map(h => <th key={h} className="text-right font-semibold px-1 pb-1">{h} d</th>)}
              </tr>
            </thead>
            <tbody>
              {celdas.map(e => (
                <tr key={`${e.dimension}-${e.estado}-${e.version}`} className="border-t border-app-border">
                  <td className="pr-2 py-1">{NOMBRE_DIMENSION[e.dimension]}: {e.estado} <span className="text-label text-app-text-faint">v{e.version}</span></td>
                  <td className="text-right px-1 font-mono">{e.eventos}</td>
                  {data.horizontes.map(h => (
                    <td key={h} className="text-right px-1 font-mono whitespace-nowrap">{e.horizontes[String(h)].suficiente ? pct(e.horizontes[String(h)].mediana) : '—'}</td>
                  ))}
                </tr>
              ))}
              <tr className="border-t border-app-border text-app-text-dim">
                <td className="pr-2 py-1">Todos los eventos</td><td />
                {data.horizontes.map(h => <td key={h} className="text-right px-1 font-mono">{data.base[String(h)].suficiente ? pct(data.base[String(h)].mediana) : '—'}</td>)}
              </tr>
            </tbody>
          </table>
          <p className="text-label text-app-text-faint mt-1">Mediana del retorno posterior del precio en USD. Compará cada fila con «Todos los eventos».</p>
        </div>
      )}
      <ul className="flex flex-col gap-0.5">
        {data.limites.map(l => <li key={l} className="text-label text-app-text-faint">· {l}</li>)}
      </ul>
    </div>
  )
}

/**
 * "Cómo fue cambiando el diagnóstico": las fotos que fue guardando la app (sólo cuando algo cambia), con la
 * versión de las reglas de cada una. Empieza a acumularse desde que existe: no reconstruye el pasado.
 */
export default function HistorialDiagnostico({ ticker }: { ticker: string }) {
  const [abierto, setAbierto] = useState(false)
  const historial = useQuery({
    queryKey: qk.de('valuacion-historial', ticker), queryFn: () => getHistorialDiagnostico(ticker), enabled: abierto,
  })
  const backtest = useQuery({ queryKey: qk.de('valuacion-backtest'), queryFn: getBacktestHistorial, enabled: abierto })
  const h = historial.data

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <div className="text-strong font-bold text-app-text flex items-center gap-1">
          Cómo fue cambiando <InfoTooltip term="historial_que_es" label="" />
        </div>
        <button onClick={() => setAbierto(v => !v)} className="text-caption font-bold text-app-accent" aria-expanded={abierto}>
          {abierto ? 'Cerrar' : 'Ver historial'}
        </button>
      </div>
      {!abierto && (
        <p className="text-caption text-app-text-dim mt-1">
          Las fotos del diagnóstico que fue guardando la app cada vez que cambió algo, con la versión de las reglas de cada una.
        </p>
      )}
      {abierto && (
        <div className="mt-3 flex flex-col gap-3">
          <QueryBoundary isLoading={historial.isLoading} error={historial.error} onRetry={() => void historial.refetch()}>
            {h && h.items.length === 0 && (
              <p className="text-caption text-app-text-dim">
                Todavía no hay fotos de este emisor: la app empieza a guardarlas después de cada actualización de fundamentales,
                para lo que tenés en cartera o en la watchlist.
              </p>
            )}
            {h && h.items.length > 0 && (
              <ul>{h.items.map((it, i) => <Foto key={it.id} item={it} esLaPrimera={i === h.items.length - 1} />)}</ul>
            )}
          </QueryBoundary>
          {backtest.data && <Backtest data={backtest.data} />}
          <p className="text-label text-app-text-faint text-center">Es un registro de lo que decía la app, no una promesa sobre el futuro.</p>
        </div>
      )}
    </Card>
  )
}
