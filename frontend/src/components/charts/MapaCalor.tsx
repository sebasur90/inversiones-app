import { useEffect, useMemo, useRef, useState } from 'react'
import type { MapaMercadoItem } from '../../api'
import { formatPctRatio } from '../../utils'
import {
  calcularLayout,
  colorVariacion,
  TOPE_COLOR,
  type NodoMapa,
  type Periodo,
} from '../../utils/mapaMercado'

const ALTO_TITULO = 20

/** Qué cabe en un rectángulo según su tamaño real en pantalla. */
function detalle(w: number, h: number): 'nada' | 'ticker' | 'ticker-pct' | 'completo' {
  if (w >= 78 && h >= 62) return 'completo'
  if (w >= 40 && h >= 32) return 'ticker-pct'
  if (w >= 34 && h >= 18) return 'ticker'
  return 'nada'
}

export default function MapaCalor({
  visible,
  periodo,
  onElegirGrupo,
  onElegirItem,
}: {
  /** El nodo que se está mirando: la raíz o un grupo al que se entró. */
  visible: NodoMapa
  periodo: Periodo
  onElegirGrupo: (clave: string) => void
  onElegirItem: (item: MapaMercadoItem) => void
}) {
  const contenedor = useRef<HTMLDivElement>(null)
  const [ancho, setAncho] = useState(0)

  useEffect(() => {
    const el = contenedor.current
    if (!el) return
    setAncho(el.clientWidth)
    const obs = new ResizeObserver(entradas => setAncho(Math.floor(entradas[0].contentRect.width)))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const alto = Math.round(Math.min(Math.max(ancho * 1.3, 420), 640))
  const tope = TOPE_COLOR[periodo]

  const { grupos, hojas } = useMemo(
    () => calcularLayout(visible, ancho, alto, ALTO_TITULO),
    [visible, ancho, alto],
  )

  return (
    <div
      ref={contenedor}
      className="relative w-full overflow-hidden rounded-xl bg-app-bg"
      style={{ height: alto }}
    >
      {hojas.map(({ nodo, x, y, w, h }) => {
        const item = nodo.item!
        const nivel = detalle(w, h)
        const pct = nodo.variacion != null ? formatPctRatio(nodo.variacion) : '—'
        const marca = item.en_cartera
          ? 'ring-2 ring-inset ring-white'
          : item.en_watchlist
            ? 'ring-2 ring-inset ring-app-accent'
            : ''
        return (
          <button
            key={nodo.clave}
            onClick={() => onElegirItem(item)}
            aria-label={`${item.ticker}, ${pct}`}
            className={`absolute flex flex-col items-center justify-center overflow-hidden text-white leading-tight ${marca}`}
            style={{ left: x, top: y, width: w, height: h, background: colorVariacion(nodo.variacion, tope) }}
          >
            {nivel === 'completo' && item.tiene_logo && (
              <img
                src={`/api/inversiones/logos/${encodeURIComponent(item.ticker_base)}.png`}
                alt=""
                loading="lazy"
                className="mb-0.5 h-6 w-6 rounded-full bg-white/90 object-contain"
                onError={e => {
                  e.currentTarget.style.display = 'none'
                }}
              />
            )}
            {nivel !== 'nada' && (
              <span className={`font-mono font-bold ${nivel === 'completo' ? 'text-strong' : 'text-label'}`}>
                {item.ticker}
              </span>
            )}
            {(nivel === 'ticker-pct' || nivel === 'completo') && (
              <span className={`font-mono tabular-nums opacity-90 ${nivel === 'completo' ? 'text-caption' : 'text-label'}`}>
                {pct}
              </span>
            )}
          </button>
        )
      })}

      {grupos.map(({ nodo, x, y, w, h }) => (
        <div key={nodo.clave} className="pointer-events-none absolute" style={{ left: x, top: y, width: w, height: h }}>
          <div className="absolute inset-0 border border-app-bg" />
          <button
            onClick={() => onElegirGrupo(nodo.clave)}
            aria-label={`Entrar a ${nodo.etiqueta}`}
            className="pointer-events-auto absolute left-0 top-0 flex w-full items-center gap-1 overflow-hidden bg-app-bg px-1 text-left text-label font-bold text-app-text"
            style={{ height: ALTO_TITULO }}
          >
            <span className="truncate">{nodo.etiqueta}</span>
            {nodo.variacion != null && w > 70 && (
              <span
                className={`shrink-0 font-mono tabular-nums ${nodo.variacion >= 0 ? 'text-app-pos' : 'text-app-neg'}`}
              >
                {formatPctRatio(nodo.variacion)}
              </span>
            )}
          </button>
        </div>
      ))}
    </div>
  )
}
