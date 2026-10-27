import type { AnalisisEvento as AnalisisEventoT } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import { AVISO_ANALISIS, ETIQUETA_CATEGORIA, MOTIVO_VENTANA, pct, tonoPct } from '../../utils/eventos'
import type { CategoriaEvento } from '../../api'

function Celda({ v, dif }: { v: number | null; dif?: boolean }) {
  return <td className={`px-1.5 py-1.5 text-right font-mono tabular-nums ${dif ? 'text-app-text-dim' : tonoPct(v)}`}>{pct(v)}</td>
}

/**
 * Lo que hizo el precio alrededor del evento, ventana por ventana, contra el índice y con las fechas
 * exactas que se usaron. Siempre con la leyenda: es comportamiento observado, no causa demostrada.
 */
export default function AnalisisEvento({ analisis }: { analisis: AnalisisEventoT }) {
  const ref = analisis.referencia
  const con = analisis.benchmark
  const avisos = [...new Set(analisis.avisos)].filter(a => AVISO_ANALISIS[a])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-caption text-app-text">
          <span className="font-mono font-bold">{analisis.ticker}</span>
          {analisis.moneda && <span className="text-app-text-faint"> · {analisis.moneda}{analisis.variante === 'subyacente' ? ' (subyacente)' : ''}</span>}
          {analisis.mercado && <span className="text-app-text-faint"> · {analisis.mercado}</span>}
        </div>
        <InfoTooltip term="eventos_comportamiento" label="" />
      </div>
      {ref && (
        <div className="text-label text-app-text-dim flex items-start gap-1">
          <span>
            Rueda de referencia: <span className="font-mono text-app-text">{ref.fecha ? fechaCorta(ref.fecha) : '—'}</span>. {ref.regla}.
          </span>
          <InfoTooltip term="eventos_rueda_referencia" label="" />
        </div>
      )}
      {analisis.ventanas.length > 0 ? (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-caption">
            <thead>
              <tr className="text-label text-app-text-faint">
                <th className="px-1.5 py-1 text-left font-semibold">Ruedas</th>
                <th className="px-1.5 py-1 text-right font-semibold">Antes</th>
                <th className="px-1.5 py-1 text-right font-semibold">Rueda</th>
                <th className="px-1.5 py-1 text-right font-semibold">Después</th>
                <th className="px-1.5 py-1 text-right font-semibold">Total</th>
                {con && <th className="px-1.5 py-1 text-right font-semibold">Dif. vs. índice</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-app-border-soft">
              {analisis.ventanas.map(w => (
                <tr key={w.n}>
                  <td className="px-1.5 py-1.5 font-mono text-app-text">±{w.n}</td>
                  <Celda v={w.previo_pct} />
                  <Celda v={w.rueda_pct} />
                  <Celda v={w.posterior_pct} />
                  <Celda v={w.acumulado_pct} />
                  {con && <Celda v={w.dif_posterior_pct} />}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-caption text-app-text-dim">Todavía no hay datos para medir alrededor de este evento.</p>
      )}
      {analisis.ventanas.length > 0 && (
        <details className="text-label text-app-text-dim">
          <summary className="cursor-pointer text-app-text-faint">Fechas, índice, volatilidad y volumen</summary>
          <div className="mt-1.5 flex flex-col gap-1.5">
            {analisis.ventanas.map(w => (
              <div key={w.n} className="rounded-lg bg-app-surface-2 p-2">
                <div className="font-bold text-app-text">±{w.n} ruedas · {w.observaciones} cotizaciones</div>
                <div>
                  {w.fechas.inicio ? fechaCorta(w.fechas.inicio) : '—'} → {w.fechas.previa ? fechaCorta(w.fechas.previa) : '—'} ·
                  {' '}{w.fechas.referencia ? fechaCorta(w.fechas.referencia) : '—'} → {w.fechas.fin ? fechaCorta(w.fechas.fin) : '—'}
                </div>
                {con && (
                  <div>
                    {con.nombre}: antes {pct(w.bench_previo_pct)}, rueda {pct(w.bench_rueda_pct)}, después {pct(w.bench_posterior_pct)}
                    {' '}(diferencia en la rueda {pct(w.dif_rueda_pct)}, en la ventana {pct(w.dif_acumulado_pct)})
                  </div>
                )}
                {(w.volatilidad_previa_pct != null || w.volatilidad_posterior_pct != null) && (
                  <div>Variación diaria típica: {pct(w.volatilidad_previa_pct, 2).replace('+', '')} antes, {pct(w.volatilidad_posterior_pct, 2).replace('+', '')} después</div>
                )}
                {w.volumen_relativo != null && <div>Volumen después: {w.volumen_relativo.toFixed(2).replace('.', ',')}× el de las 20 ruedas previas</div>}
                {w.motivos.length > 0 && <div className="text-app-warn">Incompleta: {w.motivos.map(m => MOTIVO_VENTANA[m] ?? m).join(', ')}</div>}
              </div>
            ))}
          </div>
        </details>
      )}
      {analisis.superpuestos.length > 0 && (
        <div className="rounded-lg border border-app-warn/30 bg-app-warn/10 p-2 text-label text-app-text-dim">
          <div className="flex items-center gap-1 font-bold text-app-warn">
            Otros eventos en la ventana <InfoTooltip term="eventos_superpuestos" label="" />
          </div>
          <ul className="mt-1 flex flex-col gap-0.5">
            {analisis.superpuestos.slice(0, 6).map(s => (
              <li key={`${s.evento_id}-${s.distancia_ruedas}`}>
                {s.distancia_ruedas === 0 ? 'Misma rueda' : `${s.distancia_ruedas > 0 ? '+' : ''}${s.distancia_ruedas} ruedas`}: {s.titulo}
                {s.categoria ? ` (${ETIQUETA_CATEGORIA[s.categoria as CategoriaEvento] ?? s.categoria})` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
      {avisos.map(a => <p key={a} className="text-label text-app-warn">{AVISO_ANALISIS[a]}</p>)}
      <p className="text-label text-app-text-faint">{analisis.leyenda}</p>
    </div>
  )
}
