import { useState } from 'react'

// Tickers cuyo logo ya dio 404: no se vuelve a pedir en cada render ni en cada fila.
const SIN_LOGO = new Set<string>()

/**
 * Avatar cuadrado de un instrumento: el logo que baja el servidor (`/api/inversiones/logos`) con
 * `object-fit: cover`, y si no hay, las iniciales del ticker. El logo va sobre fondo claro porque
 * la mayoría son PNG con fondo transparente pensados para papel blanco.
 */
export default function AvatarTicker({
  ticker,
  className = '',
  grande = false,
}: {
  ticker: string
  className?: string
  /** 46 px, para el encabezado del detalle del ticker; por defecto 36 px, para filas. */
  grande?: boolean
}) {
  const [falla, setFalla] = useState(SIN_LOGO.has(ticker))
  const tamano = grande ? 'w-[46px] h-[46px] rounded-2xl' : 'w-9 h-9 rounded-[11px]'
  const base = `${tamano} border flex items-center justify-center shrink-0 overflow-hidden ${className}`

  if (falla) {
    return (
      <div className={`${base} bg-app-surface-2 font-mono font-bold ${grande ? 'text-caption' : 'text-label'}`} aria-hidden="true">
        {ticker.slice(0, 4)}
      </div>
    )
  }

  return (
    <div className={`${base} bg-slate-100`} aria-hidden="true">
      <img
        src={`/api/inversiones/logos/${encodeURIComponent(ticker)}.png`}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => {
          SIN_LOGO.add(ticker)
          setFalla(true)
        }}
        className="w-full h-full object-cover"
      />
    </div>
  )
}
