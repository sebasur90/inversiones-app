import { CHART_COLORS } from '../../utils'

export interface DonutSlice {
  etiqueta: string
  porcentaje: number
}

export default function Donut({
  slices,
  centerLabel,
  centerValue,
}: {
  slices: DonutSlice[]
  centerLabel: string
  centerValue: string
}) {
  let acc = 0
  const stops = slices.map((s, i) => {
    const from = acc
    acc += s.porcentaje
    return `${CHART_COLORS[i % CHART_COLORS.length]} ${from}% ${acc}%`
  })
  const gradient = `conic-gradient(${stops.join(', ')})`

  return (
    <div className="flex items-center gap-4">
      <div className="relative w-[112px] h-[112px] shrink-0 rounded-full" style={{ background: gradient }}>
        <div className="absolute inset-5 rounded-full bg-app-surface flex flex-col items-center justify-center">
          <b className="font-mono text-strong text-app-text tabular-nums">{centerValue}</b>
          <span className="text-label uppercase tracking-wide text-app-text-dim mt-0.5">{centerLabel}</span>
        </div>
      </div>
      <div className="flex-1 flex flex-col gap-2 min-w-0">
        {slices.map((s, i) => (
          <div key={s.etiqueta} className="flex items-center gap-2 text-caption">
            <i className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="flex-1 text-app-text-dim truncate">{s.etiqueta}</span>
            <span className="font-mono font-bold text-app-text tabular-nums">{s.porcentaje.toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
