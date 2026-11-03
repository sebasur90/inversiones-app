import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CicloAtajo, CicloPaisOut } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import Segmented from '../ui/Segmented'
import { fechaCorta } from '../../utils/fechas'
import BadgeCuadrante from './BadgeCuadrante'
import MetricasGrupo from './MetricasGrupo'
import { fmtNum, fmtPct, tonoDe } from './constantes'

const HORIZ = [
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1A', label: '1A' },
  { value: '3A', label: '3A' },
]

function Fila({ etiqueta, valor, motivo, nota, termino }: { etiqueta: string; valor: number | null; motivo?: string; nota?: string; termino?: 'ciclos_efecto_cambiario' | 'ciclos_vehiculo_pais' }) {
  const tono = tonoDe(valor)
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-app-border last:border-b-0">
      <div className="min-w-0">
        <div className="text-caption font-semibold text-app-text">{termino ? <InfoTooltip term={termino} label={etiqueta} /> : etiqueta}</div>
        {nota && <div className="text-label text-app-text-faint">{nota}</div>}
      </div>
      <div className="text-right shrink-0">
        {valor == null ? (
          <div className="text-label text-app-text-faint max-w-[170px]">Sin dato{motivo ? `: ${motivo}` : ''}</div>
        ) : (
          <div className={`font-mono tabular-nums text-caption font-bold ${tono === 'pos' ? 'text-app-pos' : tono === 'neg' ? 'text-app-neg' : 'text-app-text'}`}>{fmtPct(valor, 1)}</div>
        )}
      </div>
    </div>
  )
}

interface Props {
  data: CicloPaisOut
  onComparar: (a: CicloAtajo) => void
}

/**
 * Ficha de un país o región. Separa tres medidas que NO son equivalentes: el ETF en dólares (incluye gastos y
 * distribuciones), el índice local en su moneda y el efecto del tipo de cambio.
 */
export default function FichaPais({ data, onComparar }: Props) {
  const [h, setH] = useState('1A')
  const d = data.descomposicion?.[h]
  const r = data.resumen
  const local = data.grupo.indice_local
  const fxInfo = data.grupo.fx
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeCuadrante cuadrante={r?.rotacion.actual?.cuadrante} />
        <span className="text-label text-app-text-dim">contra {data.benchmark?.nombre ?? 'sin referencia'}</span>
      </div>
      {r && <MetricasGrupo rrg={r.rotacion} rendimientos={r.rendimientos} riesgo={r.riesgo} tendencia={r.tendencia} />}

      <div>
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-label font-bold uppercase text-app-text-faint">Tres medidas distintas</div>
          <Segmented options={HORIZ} value={h} onChange={setH} />
        </div>
        {d ? (
          <div className="rounded-xl border border-app-border bg-app-surface px-3">
            <Fila etiqueta={`ETF ${data.grupo.proxy ?? ''} en USD`} valor={d.proxy_usd} motivo={d.motivos.proxy_usd} nota="Incluye distribuciones, gastos y la composición propia del fondo" />
            <Fila
              etiqueta={`Índice local${local ? ` (${local.simbolo}, ${local.moneda})` : ''}`}
              valor={d.indice_local}
              motivo={d.motivos.indice_local}
              nota="En su moneda y de precio (sin dividendos)"
            />
            <Fila
              etiqueta="Efecto cambiario"
              termino="ciclos_efecto_cambiario"
              valor={d.efecto_fx}
              motivo={d.motivos.efecto_fx}
              nota={fxInfo?.cotizacion === 'mep' ? 'Con el dólar MEP de cada fecha' : fxInfo?.simbolo ? `Con ${fxInfo.simbolo}` : undefined}
            />
            <Fila etiqueta="Índice local llevado a USD" valor={d.indice_local_usd} nota="(1 + local) × (1 + efecto cambiario) − 1" />
            <Fila etiqueta="Diferencia del vehículo" termino="ciclos_vehiculo_pais" valor={d.diferencia_vehiculo} nota="ETF en USD menos índice local en USD, en puntos" />
          </div>
        ) : (
          <p className="text-caption text-app-text-dim">Sin descomposición para este período.</p>
        )}
        {d && (
          <p className="text-label text-app-text-faint mt-1">
            Del {fechaCorta(d.desde)} al {fechaCorta(d.hasta)}. No son medidas equivalentes: si falta algún dato, esa pieza queda sin dato en vez de estimarse.
          </p>
        )}
      </div>

      {data.moneda_local_vs_usd && data.moneda_local_vs_usd.length > 1 && (
        <div>
          <div className="text-label font-bold uppercase text-app-text-faint mb-1">Moneda local frente al dólar (base 100)</div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={data.moneda_local_vs_usd} margin={{ top: 4, right: 6, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
              <XAxis dataKey="fecha" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(f: string) => `${f.slice(5, 7)}/${f.slice(2, 4)}`} minTickGap={32} />
              <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={36} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(0)} />
              <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 3" />
              <Tooltip
                contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
                labelFormatter={(f: string) => fechaCorta(f)}
                formatter={(v: number) => [fmtNum(v, 1), 'Moneda local en USD']}
              />
              <Line type="monotone" dataKey="valor" stroke="#22d3ee" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-label text-app-text-faint">Sube cuando la moneda local se aprecia frente al dólar.</div>
        </div>
      )}

      <div>
        <div className="text-label font-bold uppercase text-app-text-faint mb-1">Contexto macroeconómico</div>
        {data.macro?.estado === 'parcial' ? (
          <div className="rounded-xl border border-app-border bg-app-surface px-3 py-2 text-caption text-app-text-dim flex flex-col gap-1">
            {Object.entries(data.macro.ultimo ?? {}).map(([k, v]) =>
              v ? (
                <div key={k} className="flex justify-between gap-2">
                  <span>{k === 'riesgo_pais' ? 'Riesgo país' : k.toUpperCase()}</span>
                  <span className="font-mono tabular-nums text-app-text">
                    {fmtNum(v.valor, 0)} <span className="text-app-text-faint">({fechaCorta(v.fecha)})</span>
                  </span>
                </div>
              ) : null,
            )}
            <div className="text-label text-app-text-faint">{data.macro.motivo}</div>
          </div>
        ) : (
          <p className="text-caption text-app-text-dim">{data.macro?.motivo ?? 'Sin datos macroeconómicos.'}</p>
        )}
      </div>

      {data.relacion_commodities && (
        <div>
          <div className="text-label font-bold uppercase text-app-text-faint mb-1">Relación observada con commodities</div>
          <p className="text-caption text-app-text-dim">
            {data.relacion_commodities.valor != null ? (
              <>
                Correlación <b className="font-mono text-app-text">{fmtNum(data.relacion_commodities.valor, 2)}</b> ({data.relacion_commodities.n_obs} semanas).{' '}
              </>
            ) : (
              <>Sin datos suficientes. </>
            )}
            {data.relacion_commodities.lectura}
          </p>
        </div>
      )}

      {data.comparaciones && data.comparaciones.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.comparaciones.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => onComparar(c)}
              className="px-2.5 py-1.5 rounded-lg text-caption font-semibold bg-app-surface border border-app-border text-app-text-dim hover:text-app-text active:scale-95"
            >
              Comparar: {c.nombre}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
