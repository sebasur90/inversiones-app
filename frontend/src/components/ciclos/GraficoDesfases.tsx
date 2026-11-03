import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CiclosDesfasesOut } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fmtNum } from './constantes'

/**
 * Correlación entre el retorno semanal de «a» y el de «b» desplazado k semanas. La franja marca lo que puede salir
 * por puro azar: una barra que la supera es una hipótesis estadística, no una predicción ni una relación causal.
 */
export default function GraficoDesfases({ data }: { data: CiclosDesfasesOut }) {
  const a = data.a ? data.nombres[data.a] : 'a'
  const b = data.b ? data.nombres[data.b] : 'b'
  const banda = data.banda_azar
  const datos = data.desfases.map(d => ({ k: d.desfase_semanas, valor: d.valor, supera: d.supera_azar, n: d.n_obs }))
  return (
    <div className="flex flex-col gap-2">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={datos} margin={{ top: 8, right: 8, left: 0, bottom: 14 }}>
          <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
          <XAxis
            dataKey="k"
            tick={{ fontSize: 10, fill: '#94a3b8' }}
            label={{ value: `semanas de desfase (positivo: ${a} va primero)`, position: 'insideBottom', offset: -8, fill: '#94a3b8', fontSize: 10 }}
          />
          <YAxis domain={[-1, 1]} tick={{ fontSize: 10, fill: '#94a3b8' }} width={32} tickFormatter={(v: number) => v.toFixed(1)} />
          <ReferenceLine y={0} stroke="#64748b" />
          {banda != null && <ReferenceLine y={banda} stroke="#94a3b8" strokeDasharray="4 3" />}
          {banda != null && <ReferenceLine y={-banda} stroke="#94a3b8" strokeDasharray="4 3" />}
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
            labelFormatter={(k: number) => `Desfase de ${k} semanas`}
            formatter={(v, _n, p) => [
              typeof v === 'number' ? `${fmtNum(v, 2)} (${(p?.payload as { n: number } | undefined)?.n ?? 0} obs.)` : 'sin datos',
              'Correlación',
            ]}
          />
          <Bar dataKey="valor" isAnimationActive={false}>
            {datos.map(d => (
              <Cell key={d.k} fill={d.valor == null ? '#475569' : d.valor >= 0 ? '#10b981' : '#ef4444'} fillOpacity={d.supera ? 1 : 0.35} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {data.mejor && (
        <p className="text-caption text-app-text-dim">
          La mayor correlación en valor absoluto aparece con <b className="text-app-text">{data.mejor.desfase_semanas} semanas</b> de desfase (
          {fmtNum(data.mejor.valor, 2)}, {data.mejor.n_obs} observaciones){data.mejor.supera_azar ? ', por encima de la franja de azar' : ', dentro de la franja de azar'}.
        </p>
      )}
      <p className="text-label text-app-text-faint">
        Barras tenues: dentro de la franja de azar (±{fmtNum(banda, 2)}). Es una <InfoTooltip term="ciclos_desfase" label="hipótesis estadística" />, no una predicción.
      </p>
    </div>
  )
}
