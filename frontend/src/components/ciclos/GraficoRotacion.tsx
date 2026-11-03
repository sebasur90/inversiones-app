import { useMemo } from 'react'
import { CartesianGrid, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import type { CicloGrupoPanorama, Cuadrante } from '../../api'
import { INFO_CUADRANTE, etiquetaCorta, fmtNum } from './constantes'
import { fechaCorta } from '../../utils/fechas'

interface PuntoDato {
  x: number
  y: number
  fecha: string
  id: string
  nombre: string
  etiqueta: string
  cuadrante: Cuadrante
  ultimo: boolean
}

interface Props {
  grupos: CicloGrupoPanorama[]
  /** Los que se ocultan desde los chips; el resto se dibuja. */
  ocultos: Set<string>
  seleccionado: string | null
  onSeleccionar: (id: string) => void
  colores: Record<string, string>
  alto?: number
}

interface FormaProps {
  cx?: number
  cy?: number
  payload?: PuntoDato
}

/**
 * Mapa de rotación relativa: RS-Ratio en X, RS-Momentum en Y, 100 como centro de los dos ejes. Cada grupo es una cola
 * de puntos (las últimas semanas) que termina en un punto grande con su símbolo: hacia dónde se mueve importa tanto
 * como dónde está. El eje es simétrico alrededor de 100 para que los cuatro cuadrantes midan lo mismo.
 */
export default function GraficoRotacion({ grupos, ocultos, seleccionado, onSeleccionar, colores, alto = 360 }: Props) {
  const series = useMemo(
    () =>
      grupos
        .filter(g => g.rrg.estado === 'ok' && !ocultos.has(g.id) && (g.rrg.trayectoria?.length ?? 0) > 0)
        .map(g => ({
          g,
          datos: (g.rrg.trayectoria ?? []).map<PuntoDato>((p, i, arr) => ({
            x: p.rs_ratio,
            y: p.rs_momentum,
            fecha: p.fecha,
            id: g.id,
            nombre: g.nombre,
            etiqueta: etiquetaCorta(g),
            cuadrante: p.cuadrante,
            ultimo: i === arr.length - 1,
          })),
        })),
    [grupos, ocultos],
  )

  const radio = useMemo(() => {
    let max = 2
    for (const s of series) for (const d of s.datos) max = Math.max(max, Math.abs(d.x - 100), Math.abs(d.y - 100))
    return Math.ceil(max * 1.15 * 2) / 2
  }, [series])
  const dominio: [number, number] = [100 - radio, 100 + radio]

  const area = (x1: number, x2: number, y1: number, y2: number, c: Cuadrante, posicion: 'insideTopRight' | 'insideBottomRight' | 'insideBottomLeft' | 'insideTopLeft') => (
    <ReferenceArea
      key={c}
      x1={x1}
      x2={x2}
      y1={y1}
      y2={y2}
      fill={INFO_CUADRANTE[c].color}
      fillOpacity={0.07}
      stroke="none"
      ifOverflow="hidden"
      label={{ value: INFO_CUADRANTE[c].nombre.toUpperCase(), position: posicion, fill: INFO_CUADRANTE[c].color, fontSize: 10, fontWeight: 700 }}
    />
  )

  return (
    <div role="img" aria-label="Mapa de rotación relativa de los grupos: fortaleza relativa en el eje horizontal y momentum relativo en el vertical">
      <ResponsiveContainer width="100%" height={alto}>
        <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 18 }}>
          <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
          {area(100, dominio[1], 100, dominio[1], 'leading', 'insideTopRight')}
          {area(100, dominio[1], dominio[0], 100, 'weakening', 'insideBottomRight')}
          {area(dominio[0], 100, dominio[0], 100, 'lagging', 'insideBottomLeft')}
          {area(dominio[0], 100, 100, dominio[1], 'improving', 'insideTopLeft')}
          <ReferenceLine x={100} stroke="#64748b" strokeWidth={1} />
          <ReferenceLine y={100} stroke="#64748b" strokeWidth={1} />
          <XAxis
            type="number"
            dataKey="x"
            name="Fortaleza relativa"
            domain={dominio}
            allowDataOverflow
            tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickFormatter={(v: number) => v.toFixed(0)}
            label={{ value: 'Fortaleza relativa (RS-Ratio) →', position: 'insideBottom', offset: -10, fill: '#94a3b8', fontSize: 10 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Momentum relativo"
            domain={dominio}
            allowDataOverflow
            width={34}
            tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <ZAxis range={[36, 36]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3', stroke: '#475569' }}
            content={({ active, payload }) => {
              const p = active ? (payload?.[0]?.payload as PuntoDato | undefined) : undefined
              if (!p) return null
              const info = INFO_CUADRANTE[p.cuadrante]
              return (
                <div className="rounded-[10px] border border-app-border bg-[#171b26] px-2.5 py-2 text-caption">
                  <div className="font-bold text-app-text">{p.nombre}</div>
                  <div className="text-app-text-dim">{fechaCorta(p.fecha)}</div>
                  <div className="font-mono tabular-nums text-app-text-dim">
                    Fortaleza {fmtNum(p.x, 1)} · Momentum {fmtNum(p.y, 1)}
                  </div>
                  <div className="font-bold" style={{ color: info.color }}>
                    {info.nombre}
                  </div>
                </div>
              )
            }}
          />
          {series.map(({ g, datos }) => {
            const color = colores[g.id] ?? '#94a3b8'
            const elegido = seleccionado === g.id
            return (
              <Scatter
                key={g.id}
                name={g.nombre}
                data={datos}
                line={{ stroke: color, strokeWidth: elegido ? 2.5 : 1.4, strokeOpacity: elegido ? 0.95 : 0.55 }}
                lineType="joint"
                isAnimationActive={false}
                shape={(props: FormaProps) => {
                  const { cx, cy, payload } = props
                  if (cx == null || cy == null || !payload) return <g />
                  if (!payload.ultimo) return <circle cx={cx} cy={cy} r={2.6} fill={color} fillOpacity={0.55} />
                  return (
                    <g
                      onClick={() => onSeleccionar(g.id)}
                      style={{ cursor: 'pointer' }}
                      role="button"
                      aria-label={`${g.nombre}: ${INFO_CUADRANTE[payload.cuadrante].nombre}. Tocá para ver el detalle`}
                    >
                      {/* Zona de toque amplia: el punto visible es chico. */}
                      <circle cx={cx} cy={cy} r={16} fill="transparent" />
                      <circle cx={cx} cy={cy} r={elegido ? 8 : 6} fill={color} stroke={elegido ? '#fff' : '#0a0e18'} strokeWidth={elegido ? 2 : 1.5} />
                      <text x={cx + 9} y={cy + 3.5} fontSize={10} fontWeight={700} fill="#e2e8f0" stroke="#0a0e18" strokeWidth={3} paintOrder="stroke">
                        {payload.etiqueta}
                      </text>
                    </g>
                  )
                }}
              />
            )
          })}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
