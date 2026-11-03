import { useMemo, useState } from 'react'
import type { CiclosCorrelacionesOut, MatrizCorrelacionParItem } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import MatrizCorrelacionHeatmap, { type CeldaSeleccionada } from '../charts/MatrizCorrelacionHeatmap'
import { fechaCorta } from '../../utils/fechas'
import { fmtNum } from './constantes'

function lectura(v: number, escala: { desde: number; texto: string }[] | undefined): string {
  const e = (escala ?? []).find(x => v >= x.desde)
  return e ? e.texto : ''
}

/**
 * Matriz de correlación entre grupos. Reutiliza la tabla de calor de la matriz de correlaciones de instrumentos
 * (mismos colores y comportamiento); sólo traduce ids a etiquetas cortas (el símbolo del proxy).
 */
export default function MatrizCiclos({ data, etiquetas }: { data: CiclosCorrelacionesOut; etiquetas: Record<string, string> }) {
  const [sel, setSel] = useState<CeldaSeleccionada | null>(null)
  const lab = (id: string) => etiquetas[id] ?? data.nombres[id] ?? id

  const { cabeceras, pares } = useMemo(() => {
    const cab = data.ids.map(lab)
    const ps: MatrizCorrelacionParItem[] = data.pares.map(p => ({
      ticker_a: lab(p.ticker_a),
      ticker_b: lab(p.ticker_b),
      valor: p.valor,
      n_obs: p.n_obs,
      solapamiento_pct: p.solapamiento_pct,
      estado: p.estado,
      motivo: p.motivo as MatrizCorrelacionParItem['motivo'],
    }))
    return { cabeceras: cab, pares: ps }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, etiquetas])

  if (!data.matriz) return null
  const par = sel ? data.pares.find(p => (p.ticker_a === data.ids[sel.i] && p.ticker_b === data.ids[sel.j]) || (p.ticker_a === data.ids[sel.j] && p.ticker_b === data.ids[sel.i])) : null
  return (
    <div className="flex flex-col gap-2">
      <MatrizCorrelacionHeatmap tickers={cabeceras} matriz={data.matriz} pares={pares} seleccion={sel} onSeleccionar={setSel} />
      {sel && par ? (
        <div className="rounded-xl border border-app-border bg-app-surface px-3 py-2 text-caption text-app-text-dim">
          <div className="font-semibold text-app-text">
            {data.nombres[data.ids[sel.i]]} vs. {data.nombres[data.ids[sel.j]]}
          </div>
          {par.valor != null ? (
            <div>
              Correlación <b className="font-mono tabular-nums text-app-text">{fmtNum(par.valor, 2)}</b>: {lectura(par.valor, data.escala)}.
            </div>
          ) : (
            <div>Sin datos suficientes para calcularla ({par.n_obs} observaciones en común).</div>
          )}
          <div className="text-label text-app-text-faint">
            {par.n_obs} observaciones {data.frecuencia === 'diaria' ? 'diarias' : 'semanales'}
            {data.periodo_efectivo?.desde && data.periodo_efectivo?.hasta
              ? ` · ${fechaCorta(data.periodo_efectivo.desde)} → ${fechaCorta(data.periodo_efectivo.hasta)}`
              : ''}
          </div>
        </div>
      ) : (
        <p className="text-label text-app-text-faint">
          Tocá una celda para ver qué significa y con cuántos datos se calculó. Qué es la <InfoTooltip term="ciclos_correlacion" label="correlación" /> y por qué no
          es causalidad.
        </p>
      )}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-label text-app-text-faint">
        {data.ids.map(id => (
          <span key={id}>
            <b className="text-app-text-dim">{lab(id)}</b> {data.nombres[id]}
          </span>
        ))}
      </div>
    </div>
  )
}
