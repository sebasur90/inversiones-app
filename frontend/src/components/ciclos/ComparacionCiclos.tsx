import type { CiclosComparacionOut } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import BadgeCuadrante from './BadgeCuadrante'
import GraficoBase100 from './GraficoBase100'
import { fmtPct, tonoDe } from './constantes'

const TONO = { pos: 'text-app-pos', neg: 'text-app-neg' }

function Dato({ etiqueta, valor, tono }: { etiqueta: string; valor: string; tono?: 'pos' | 'neg' }) {
  return (
    <div>
      <div className="text-label text-app-text-faint">{etiqueta}</div>
      <div className={`font-mono tabular-nums text-caption font-bold ${tono ? TONO[tono] : 'text-app-text'}`}>{valor}</div>
    </div>
  )
}

/** Varios grupos sobre el MISMO período exacto: rendimiento, volatilidad, caída y recuperación, una tarjeta por grupo. */
export default function ComparacionCiclos({ data }: { data: CiclosComparacionOut }) {
  const colores = data.series.map((s, i) => ({ ...s, rol: i === 0 ? ('grupo' as const) : ('adicional' as const) }))
  return (
    <div className="flex flex-col gap-3">
      {data.periodo && (
        <p className="text-caption text-app-text-dim">
          Período analizado: <b className="text-app-text">{fechaCorta(data.periodo.desde)}</b> → <b className="text-app-text">{fechaCorta(data.periodo.hasta)}</b>
          {data.etiqueta_periodo ? ` (${data.etiqueta_periodo})` : ''}
        </p>
      )}
      {data.filas.length > 0 && <GraficoBase100 filas={data.filas} series={colores} />}
      <ul className="flex flex-col gap-2">
        {data.grupos.map(g => {
          const dd = g.drawdown
          return (
            <li key={g.id} className="rounded-xl border border-app-border bg-app-surface px-3 py-2.5">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-caption font-bold text-app-text">{g.nombre}</span>
                {g.rotacion_actual?.cuadrante && <BadgeCuadrante cuadrante={g.rotacion_actual.cuadrante} />}
              </div>
              {g.retorno == null ? (
                <p className="text-label text-app-text-faint">Sin datos suficientes en este período{g.motivo ? ` (${g.motivo})` : ''}.</p>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  <Dato etiqueta="Rendimiento" valor={fmtPct(g.retorno)} tono={tonoDe(g.retorno)} />
                  <Dato etiqueta="vs. referencia" valor={fmtPct(g.relativo)} tono={tonoDe(g.relativo)} />
                  <Dato etiqueta="Volatilidad" valor={fmtPct(g.volatilidad?.anualizada, 1, false)} />
                  <Dato etiqueta="Máx. caída" valor={fmtPct(dd?.maximo, 1, false)} tono={dd?.maximo ? 'neg' : undefined} />
                  <Dato
                    etiqueta="Recuperación"
                    valor={dd?.maximo == null ? '—' : dd.maximo === 0 ? 'sin caída' : dd.recuperacion_semanas != null ? `${dd.recuperacion_semanas} sem.` : 'sin recuperar'}
                  />
                  <Dato etiqueta="Semanas" valor={String(g.semanas)} />
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <p className="text-label text-app-text-faint">
        Qué miden la <InfoTooltip term="ciclos_volatilidad" label="volatilidad" /> y la <InfoTooltip term="ciclos_drawdown" label="máxima caída" />. Es comportamiento
        observado en ese período; no implica que se repita.
      </p>
    </div>
  )
}
