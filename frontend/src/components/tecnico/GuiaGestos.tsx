import { useCallback, useEffect, useRef, useState } from 'react'
import { ATRIBUTO_GESTO_PROPIO } from './useVentanaVisible'

/** ¿Pantalla táctil? Decide qué gestos se explican (dedo o mouse). */
export const TACTIL = typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: coarse)').matches

const CLAVE_VISTA = 'grafico-tecnico.guia-gestos-vista'

function leerVista(): boolean {
  try {
    return window.localStorage.getItem(CLAVE_VISTA) === '1'
  } catch {
    // Sin storage (modo privado, datos bloqueados): mejor mostrarla de más que nunca.
    return false
  }
}

function marcarVista() {
  try {
    window.localStorage.setItem(CLAVE_VISTA, '1')
  } catch {
    /* sin storage: se volverá a mostrar la próxima vez, no es grave */
  }
}

/** La guía se muestra sola la primera vez; después, sólo a pedido ("Cómo se usa" en el pie). */
export function useGuiaGestos() {
  const [visible, setVisible] = useState(() => !leerVista())
  const mostrar = useCallback(() => setVisible(true), [])
  const cerrar = useCallback(() => {
    marcarVista()
    setVisible(false)
  }, [])
  return { visible, mostrar, cerrar }
}

/** Aviso breve sobre el gráfico (p. ej. "acercá primero para poder deslizar"). Se va solo. */
export function useAvisoGrafico(duracion = 2600) {
  const [texto, setTexto] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  const avisar = useCallback((t: string) => {
    setTexto(t)
    if (timer.current != null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setTexto(null), duracion)
  }, [duracion])
  useEffect(() => () => { if (timer.current != null) window.clearTimeout(timer.current) }, [])
  return { texto, avisar }
}

export const AVISO_SIN_RECORRIDO = TACTIL
  ? 'Estás viendo todo el período: pellizcá o tocá + para acercar, y después deslizá.'
  : 'Estás viendo todo el período: acercá con la rueda o con + y después arrastrá.'

const GESTOS_TACTIL: [string, string][] = [
  ['Tocá una vela', 'arriba ves su fecha, precios, variación y los indicadores'],
  ['Mantené apretado y arrastrá', 'recorrés vela por vela'],
  ['Pellizcá (o + y −)', 'acercás y alejás'],
  ['Deslizá de costado', 'te movés por la historia (con zoom)'],
  ['Deslizá para arriba o abajo', 'movés la página, no el gráfico'],
  ['Doble toque', 'volvés a todo el período'],
]

const GESTOS_MOUSE: [string, string][] = [
  ['Pasá el mouse', 'arriba ves los datos de cada vela y los indicadores'],
  ['Rueda (o + y −)', 'acercás y alejás donde está el puntero'],
  ['Arrastrá', 'te movés por la historia (con zoom)'],
  ['Doble clic', 'volvés a todo el período'],
]

/** Tarjeta sobre el gráfico con los gestos. Marcada como gesto propio: tocarla no mueve el
 * gráfico ni pone la cruz. */
export default function GuiaGestos({ onCerrar, conZonas = false }: { onCerrar: () => void; conZonas?: boolean }) {
  const gestos = TACTIL ? GESTOS_TACTIL : GESTOS_MOUSE
  return (
    <div
      {...{ [ATRIBUTO_GESTO_PROPIO]: '' }}
      role="dialog" aria-label="Cómo usar el gráfico"
      className="absolute inset-x-0 top-0 z-10 rounded-xl border border-app-border bg-app-bg/95 p-3 shadow-lg"
    >
      <div className="mb-1.5 text-caption font-bold text-app-text">Cómo usar el gráfico</div>
      <ul className="flex flex-col gap-1">
        {gestos.map(([gesto, efecto]) => (
          <li key={gesto} className="text-label text-app-text-dim">
            <span className="font-semibold text-app-text">{gesto}</span> → {efecto}
          </li>
        ))}
        {conZonas && (
          <li className="text-label text-app-text-dim">
            <span className="font-semibold text-app-text">Editando zonas</span> → arrastrá las manijas ↕ de la izquierda
          </li>
        )}
      </ul>
      <button
        type="button" onClick={onCerrar}
        className="mt-2.5 h-9 w-full rounded-lg bg-app-accent text-caption font-semibold text-white"
      >
        Entendido
      </button>
    </div>
  )
}

/** Aviso flotante sobre el gráfico. No captura toques: el gesto que lo provocó sigue de largo. */
export function AvisoGrafico({ texto }: { texto: string | null }) {
  if (!texto) return null
  return (
    <div className="pointer-events-none absolute inset-x-2 top-2 z-10 flex justify-center" role="status">
      <span className="rounded-lg bg-app-surface-2/95 px-3 py-1.5 text-center text-label font-semibold text-app-text shadow-lg">
        {texto}
      </span>
    </div>
  )
}
