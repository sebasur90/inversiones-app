import { useMemo } from 'react'
import type { MarcaEvento, PuntoSerieEvento } from '../../api'
import { useAnchoContenedor } from '../tecnico/useAnchoContenedor'
import { fechaCorta as fechaEje, formatoPrecio } from '../tecnico/formatoEjes'
import { fechaCorta, mesAnioCorto } from '../../utils/fechas'
import { COLOR_CATEGORIA, diasHabilesEntre } from '../../utils/eventos'

const ALTO = 230
const PAD = { top: 22, right: 46, bottom: 22, left: 6 }
const SEPARACION_GRUPO = 9      // px: marcas más cerca que esto se agrupan en una burbuja
const MAX_RANURAS_FUTURO = 160  // días hábiles de eje futuro como máximo

interface Grupo { x: number; marcas: MarcaEvento[]; futuro: boolean }

function primerIndiceDesde(fechas: string[], f: string): number {
  let lo = 0
  let hi = fechas.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (fechas[mid] < f) lo = mid + 1
    else hi = mid
  }
  return lo
}

/**
 * Serie de precios con los eventos marcados en su rueda de referencia. El eje X es por rueda (sin
 * huecos de fin de semana) y se extiende con **días hábiles sin precio** hasta el último evento futuro:
 * la línea termina en la última cotización real y el tramo de la derecha queda rayado, sin valores
 * inventados. Las marcas muy juntas se agrupan en una burbuja con la cantidad; tocarla abre la lista.
 */
export default function GraficoEventos({
  serie, benchmark, marcas, onElegir, elegido,
}: {
  serie: PuntoSerieEvento[]
  benchmark?: { nombre: string; serie: PuntoSerieEvento[] } | null
  marcas: MarcaEvento[]
  onElegir: (marcas: MarcaEvento[]) => void
  elegido: number | null
}) {
  const [ref, ancho] = useAnchoContenedor<HTMLDivElement>(280)
  const fechas = useMemo(() => serie.map(p => p.fecha), [serie])
  const n = serie.length
  const ultima = fechas[n - 1]
  const futuras = useMemo(() => {
    const maxFuturo = marcas.filter(m => m.futuro).reduce<string | null>((acc, m) => (!acc || m.fecha_evento > acc ? m.fecha_evento : acc), null)
    return ultima && maxFuturo ? diasHabilesEntre(ultima, maxFuturo, MAX_RANURAS_FUTURO) : []
  }, [marcas, ultima])
  const total = Math.max(2, n + futuras.length + (futuras.length ? 1 : 0))
  const anchoUtil = ancho - PAD.left - PAD.right
  const x = (i: number) => PAD.left + (i / (total - 1)) * anchoUtil

  const benchEscalado = useMemo(() => {
    // El índice se dibuja normalizado al primer cierre de la serie: una sola escala, comparable en forma.
    if (!benchmark?.serie.length || !n) return null
    const porFecha = new Map(benchmark.serie.map(p => [p.fecha, p.cierre]))
    const base = porFecha.get(fechas[0]) ?? benchmark.serie.find(p => p.fecha >= fechas[0])?.cierre
    if (!base) return null
    return fechas.map(f => {
      const v = porFecha.get(f)
      return v == null ? null : (v / base) * serie[0].cierre
    })
  }, [benchmark, fechas, n, serie])

  const { min, max } = useMemo(() => {
    const valores = serie.map(p => p.cierre).concat((benchEscalado ?? []).filter((v): v is number => v != null))
    const mn = Math.min(...valores)
    const mx = Math.max(...valores)
    const m = (mx - mn) * 0.06 || mx * 0.05 || 1
    return { min: mn - m, max: mx + m }
  }, [serie, benchEscalado])
  const y = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * (ALTO - PAD.top - PAD.bottom)

  const trazo = (valores: (number | null)[]) => {
    let d = ''
    let abierto = false
    valores.forEach((v, i) => {
      if (v == null) { abierto = false; return }
      d += `${abierto ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
      abierto = true
    })
    return d
  }

  const grupos = useMemo<Grupo[]>(() => {
    const ubicadas = marcas.map(m => {
      const idx = m.futuro
        ? n + Math.min(primerIndiceDesde(futuras, m.fecha_evento), Math.max(0, futuras.length - 1))
        : Math.min(primerIndiceDesde(fechas, m.fecha_referencia ?? m.fecha_evento), n - 1)
      return { m, px: x(idx) }
    }).sort((a, b) => a.px - b.px)
    const out: Grupo[] = []
    for (const u of ubicadas) {
      const ultimo = out[out.length - 1]
      if (ultimo && u.px - ultimo.x < SEPARACION_GRUPO && ultimo.futuro === u.m.futuro) ultimo.marcas.push(u.m)
      else out.push({ x: u.px, marcas: [u.m], futuro: u.m.futuro })
    }
    return out
  }, [marcas, fechas, futuras, n, ancho, total]) // `x` depende de `ancho` y `total`

  const ticks = useMemo(() => {
    const todas = [...fechas, ...futuras]
    const cantidad = Math.max(2, Math.floor(anchoUtil / 90))
    const paso = Math.max(1, Math.floor(todas.length / cantidad))
    const out: { i: number; texto: string }[] = []
    for (let i = 0; i < todas.length; i += paso) out.push({ i, texto: todas.length > 400 ? mesAnioCorto(todas[i]) : fechaEje(todas[i]) })
    return out
  }, [fechas, futuras, anchoUtil])

  if (n < 2) return null
  const xUltima = x(n - 1)

  return (
    <div ref={ref} className="w-full select-none">
      <svg width={ancho} height={ALTO} role="img" aria-label="Cotización con eventos marcados">
        <defs>
          <pattern id="rayado-futuro" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="#334155" strokeWidth="1.5" />
          </pattern>
        </defs>
        {futuras.length > 0 && (
          <g>
            <rect x={xUltima} y={PAD.top} width={x(total - 1) - xUltima} height={ALTO - PAD.top - PAD.bottom} fill="url(#rayado-futuro)" opacity={0.5} />
            <text x={(xUltima + x(total - 1)) / 2} y={ALTO - PAD.bottom - 6} textAnchor="middle" fontSize="10" fill="#94a3b8">sin cotización</text>
          </g>
        )}
        {[min + (max - min) * 0.1, (min + max) / 2, max - (max - min) * 0.1].map(v => (
          <g key={v}>
            <line x1={PAD.left} x2={ancho - PAD.right} y1={y(v)} y2={y(v)} stroke="#1c1f2a" strokeDasharray="3 3" />
            <text x={ancho - PAD.right + 4} y={y(v) + 3} fontSize="10" fill="#94a3b8" className="tabular-nums">{formatoPrecio(v)}</text>
          </g>
        ))}
        {benchEscalado && <path d={trazo(benchEscalado)} fill="none" stroke="#94a3b8" strokeWidth={1.2} strokeDasharray="4 3" opacity={0.7} />}
        <path d={trazo(serie.map(p => p.cierre))} fill="none" stroke="#3b82f6" strokeWidth={1.8} strokeLinejoin="round" />
        <circle cx={xUltima} cy={y(serie[n - 1].cierre)} r={3} fill="#3b82f6" />

        {grupos.map(g => {
          const una = g.marcas.length === 1 ? g.marcas[0] : null
          const color = una ? COLOR_CATEGORIA[una.categoria] : '#e2e8f0'
          const activo = g.marcas.some(m => m.evento_id === elegido)
          const titulo = g.marcas.map(m => `${fechaCorta(m.fecha_evento)} · ${m.titulo}`).join('\n')
          return (
            <g key={`${g.x}-${g.marcas[0].evento_id}`} onClick={() => onElegir(g.marcas)} className="cursor-pointer">
              <title>{titulo}</title>
              <line x1={g.x} x2={g.x} y1={PAD.top} y2={ALTO - PAD.bottom} stroke={color} strokeWidth={activo ? 1.6 : 1}
                strokeDasharray={g.futuro ? '3 3' : undefined} opacity={activo ? 0.9 : 0.4} />
              <circle cx={g.x} cy={PAD.top - 8} r={14} fill="transparent" />
              <circle cx={g.x} cy={PAD.top - 8} r={una ? (una.importancia >= 3 ? 5 : 4) : 7}
                fill={g.futuro ? '#0a0e18' : color} stroke={color} strokeWidth={activo ? 2.5 : 1.5} />
              {!una && <text x={g.x} y={PAD.top - 5} textAnchor="middle" fontSize="9" fontWeight="bold" fill={g.futuro ? color : '#0a0e18'}>{g.marcas.length}</text>}
            </g>
          )
        })}

        {ticks.map(t => (
          <text key={t.i} x={x(t.i)} y={ALTO - 6} textAnchor="middle" fontSize="10" fill={t.i >= n ? '#64748b' : '#94a3b8'}>{t.texto}</text>
        ))}
      </svg>
    </div>
  )
}
