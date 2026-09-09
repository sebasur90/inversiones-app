import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent, TouchEvent as ReactTouchEvent, WheelEvent as ReactWheelEvent } from 'react'

/** Mínimo de barras a la vista: con menos, las velas se vuelven bloques enormes y el gráfico
 * deja de decir nada. */
const MINIMO_VISIBLE = 20

export interface Ventana { inicio: number; fin: number }

export interface ControlesVentana {
  ventana: Ventana
  /** ¿Está mostrando toda la serie? Sirve para deshabilitar "restablecer". */
  completa: boolean
  zoom: (factor: number, centro?: number) => void
  desplazar: (deltaBarras: number) => void
  reset: () => void
  /** Handlers para el contenedor de los paneles: rueda = zoom, arrastre = desplazamiento,
   * doble clic = restablecer, dos dedos = pellizco. */
  handlers: {
    onWheel: (e: ReactWheelEvent) => void
    onMouseDown: (e: ReactMouseEvent) => void
    onDoubleClick: () => void
    onTouchStart: (e: ReactTouchEvent) => void
    onTouchMove: (e: ReactTouchEvent) => void
    onTouchEnd: () => void
  }
  /** `true` mientras se arrastra: el contenedor cambia el cursor y los paneles ignoran el hover. */
  arrastrando: boolean
}

function acotar(inicio: number, fin: number, n: number): Ventana {
  if (n <= 0) return { inicio: 0, fin: 0 }
  const maximoVisible = n
  let visibles = Math.round(fin - inicio + 1)
  visibles = Math.max(Math.min(MINIMO_VISIBLE, n), Math.min(visibles, maximoVisible))

  let i = Math.round(inicio)
  if (i < 0) i = 0
  if (i + visibles > n) i = n - visibles
  return { inicio: i, fin: i + visibles - 1 }
}

/**
 * Ventana visible del gráfico técnico: qué tramo de las `n` barras se está mirando.
 *
 * Vive en el orquestador (`GraficoBacktest` / `GraficoTecnico`) y viaja a los paneles a través de
 * `useEscalaX`, de modo que zoom y desplazamiento quedan sincronizados entre precio, osciladores,
 * volumen y curva de rendimiento sin que cada panel maneje su propio estado.
 *
 * La ventana se resetea sola cuando cambia `n` (otro ticker, otro período, otro backtest): dejar
 * el tramo anterior mostraría un rango que ya no significa lo mismo.
 *
 * Recibe `ancho` en vez de la `EscalaX` para no quedar en un ciclo con ella: la escala se deriva
 * de esta ventana, así que el hook rehace acá el mismo par de cuentas (paso por barra e índice
 * bajo el cursor) que `useEscalaX` expone hacia afuera.
 */
export function useVentanaVisible(n: number, ancho: number): ControlesVentana {
  const [ventana, setVentana] = useState<Ventana>(() => ({ inicio: 0, fin: Math.max(0, n - 1) }))
  const [arrastrando, setArrastrando] = useState(false)

  useEffect(() => {
    setVentana({ inicio: 0, fin: Math.max(0, n - 1) })
  }, [n])

  const reset = useCallback(() => setVentana({ inicio: 0, fin: Math.max(0, n - 1) }), [n])

  /** `factor > 1` acerca. `centro` (índice de barra) se queda quieto: hacer zoom con la rueda
   * sobre una vela tiene que agrandar alrededor de esa vela, no del medio del panel. */
  const zoom = useCallback((factor: number, centro?: number) => {
    setVentana(v => {
      const visibles = v.fin - v.inicio + 1
      const nuevoAncho = visibles / factor
      const pivote = centro != null ? Math.min(Math.max(centro, v.inicio), v.fin) : (v.inicio + v.fin) / 2
      const proporcion = visibles > 1 ? (pivote - v.inicio) / (visibles - 1) : 0.5
      const inicio = pivote - proporcion * (nuevoAncho - 1)
      return acotar(inicio, inicio + nuevoAncho - 1, n)
    })
  }, [n])

  const desplazar = useCallback((deltaBarras: number) => {
    setVentana(v => acotar(v.inicio + deltaBarras, v.fin + deltaBarras, n))
  }, [n])

  const visibles = Math.max(1, ventana.fin - ventana.inicio + 1)
  const pasoX = ancho > 0 ? ancho / visibles : 0
  const indiceDeX = useCallback(
    (x: number) => (pasoX > 0 ? Math.min(ventana.fin, Math.max(ventana.inicio, ventana.inicio + Math.floor(x / pasoX))) : ventana.inicio),
    [pasoX, ventana.inicio, ventana.fin],
  )

  // Refs y no estado: el arrastre y el pellizco actualizan en cada movimiento del puntero, y
  // re-renderizar por cada píxel intermedio sólo para guardar la posición previa es tirar frames.
  const arrastreRef = useRef<{ x: number; pasoX: number } | null>(null)
  const pellizcoRef = useRef<number | null>(null)

  const onWheel = useCallback((e: ReactWheelEvent) => {
    if (n <= MINIMO_VISIBLE) return
    // Sin `preventDefault`: el listener de React es pasivo y el navegador lo ignoraría con un
    // warning. El zoom igual se aplica; la página no scrollea porque el contenedor no desborda.
    const rect = e.currentTarget.getBoundingClientRect()
    zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, indiceDeX(e.clientX - rect.left))
  }, [n, indiceDeX, zoom])

  const onMouseDown = useCallback((e: ReactMouseEvent) => {
    if (e.button !== 0 || pasoX <= 0) return
    arrastreRef.current = { x: e.clientX, pasoX }
    setArrastrando(true)
  }, [pasoX])

  // El seguimiento del arrastre va en `window` y no en el SVG: si el puntero se va del gráfico con
  // el botón apretado, el desplazamiento tiene que seguir (y el `mouseup` de afuera, terminarlo).
  useEffect(() => {
    if (!arrastrando) return

    function onMove(e: MouseEvent) {
      const inicio = arrastreRef.current
      if (!inicio || inicio.pasoX <= 0) return
      const deltaBarras = Math.round((inicio.x - e.clientX) / inicio.pasoX)
      if (deltaBarras === 0) return
      arrastreRef.current = { ...inicio, x: e.clientX }
      desplazar(deltaBarras)
    }
    function onUp() {
      arrastreRef.current = null
      setArrastrando(false)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [arrastrando, desplazar])

  const onTouchStart = useCallback((e: ReactTouchEvent) => {
    if (e.touches.length === 2) {
      pellizcoRef.current = Math.abs(e.touches[0].clientX - e.touches[1].clientX)
    }
  }, [])

  const onTouchMove = useCallback((e: ReactTouchEvent) => {
    if (e.touches.length !== 2 || pellizcoRef.current == null) return
    const distancia = Math.abs(e.touches[0].clientX - e.touches[1].clientX)
    const previa = pellizcoRef.current
    if (previa <= 0 || Math.abs(distancia - previa) < 8) return
    pellizcoRef.current = distancia
    const rect = e.currentTarget.getBoundingClientRect()
    const centroX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left
    zoom(distancia > previa ? 1.15 : 1 / 1.15, indiceDeX(centroX))
  }, [indiceDeX, zoom])

  const onTouchEnd = useCallback(() => { pellizcoRef.current = null }, [])

  return {
    ventana,
    completa: ventana.inicio === 0 && ventana.fin >= n - 1,
    zoom,
    desplazar,
    reset,
    arrastrando,
    handlers: { onWheel, onMouseDown, onDoubleClick: reset, onTouchStart, onTouchMove, onTouchEnd },
  }
}
