import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, RefObject } from 'react'

/** Mínimo de barras a la vista: con menos, las velas se vuelven bloques enormes y el gráfico
 * deja de decir nada. */
const MINIMO_VISIBLE = 20
/** Cuánto tiene que moverse el dedo para que el gesto deje de ser un toque y se decida si es
 * desplazamiento (horizontal) o scroll de la página (vertical). */
const UMBRAL_MOVIMIENTO = 8
/** Mantener apretado este tiempo sin moverse pasa a "recorrer velas" con la cruz. */
const DEMORA_CRUZ = 300
const DOBLE_TOQUE_MS = 300
const DOBLE_TOQUE_PX = 24
/** Frenado de la inercia por cada frame de 16 ms. */
const FRICCION = 0.94
/** Tras un toque, los navegadores emulan eventos de mouse (`dblclick` incluido): se ignoran. */
const IGNORAR_MOUSE_TRAS_TOQUE = 800

/** Ventana visible en índices de barra. `inicio` puede tener fracción (el desplazamiento sigue al
 * dedo píxel a píxel); `fin = inicio + visibles − 1`. Ver `useEscalaX`. */
export interface Ventana { inicio: number; fin: number }

export interface OpcionesGestos {
  /** `false` apaga todos los gestos. Las manijas de las zonas no lo necesitan: se marcan con
   * `ATRIBUTO_GESTO_PROPIO` y el resto del gráfico sigue navegable mientras se edita. */
  activo: boolean
  /** Un toque corto sobre una vela (celular). */
  onToque?: (indice: number) => void
  /** Mantener apretado y arrastrar: la cruz sigue al dedo vela por vela. */
  onCruz?: (indice: number) => void
  /** La serie de la que se está mirando una ventana (la referencia del array). Otro ticker con la
   * misma cantidad de ruedas también tiene que volver a todo el período. Tiene que ser una
   * referencia estable entre renders: no un `.slice()` hecho en el render. */
  serie?: unknown
  /** Cambió la serie (no en el primer render): la cruz fija apuntaría a una vela de otra cosa. */
  onCambioSerie?: () => void
}

export interface ControlesVentana {
  ventana: Ventana
  /** ¿Está mostrando toda la serie? Sirve para deshabilitar "restablecer". */
  completa: boolean
  /** `factor > 1` acerca, alrededor del centro del panel (lo usan los botones). */
  zoom: (factor: number) => void
  reset: () => void
  /** `true` mientras se arrastra con el mouse: el contenedor cambia el cursor. */
  arrastrando: boolean
}

function visiblesPermitidos(visibles: number, n: number): number {
  return Math.max(Math.min(MINIMO_VISIBLE, n), Math.min(visibles, n))
}

function acotar(inicio: number, visibles: number, n: number): Ventana {
  if (n <= 0) return { inicio: 0, fin: 0 }
  const v = visiblesPermitidos(visibles, n)
  const i = Math.min(Math.max(inicio, 0), n - v)
  return { inicio: i, fin: i + v - 1 }
}

/** Marca un elemento que maneja su propio arrastre: un gesto que empieza ahí no desplaza ni hace
 * zoom. Se usa como `{...{ [ATRIBUTO_GESTO_PROPIO]: '' }}` o directamente `data-gesto-propio=""`. */
export const ATRIBUTO_GESTO_PROPIO = 'data-gesto-propio'

function esGestoPropio(objetivo: EventTarget | null): boolean {
  return objetivo instanceof Element && objetivo.closest(`[${ATRIBUTO_GESTO_PROPIO}]`) !== null
}

type Gesto =
  | { tipo: 'nada' }
  /** Un dedo apoyado que todavía no se movió lo suficiente: puede ser toque, desplazamiento,
   * scroll de la página o "mantener apretado". */
  | { tipo: 'pendiente'; x0: number; y0: number; xActual: number }
  | { tipo: 'desplazando'; x0: number; inicio0: number; visibles: number }
  | { tipo: 'cruz' }
  /** `u1`/`u2`: posición (en barras, con fracción) bajo cada dedo al empezar. El pellizco mantiene
   * esas dos posiciones debajo de los dedos: zoom y desplazamiento en el mismo gesto. */
  | { tipo: 'pellizco'; id1: number; id2: number; u1: number; u2: number }
  /** Scroll vertical de la página, o el dedo que queda después de un pellizco. */
  | { tipo: 'ignorar' }
  /** Empezó sobre un elemento con su propio arrastre (`ATRIBUTO_GESTO_PROPIO`, p. ej. la manija de
   * una zona): el gráfico no se mueve, pero tampoco la página — si el navegador tomara el gesto
   * como scroll, cancelaría el arrastre de la manija a mitad de camino. */
  | { tipo: 'propio' }

/**
 * Ventana visible del gráfico técnico (qué tramo de las `n` barras se está mirando) y los gestos
 * que la mueven, sobre el contenedor de los paneles que apunta `ref`.
 *
 * Vive en el orquestador (`GraficoBacktest` / `GraficoTecnico`) y viaja a los paneles a través de
 * `useEscalaX`, de modo que zoom y desplazamiento quedan sincronizados entre precio, osciladores,
 * volumen y curva de rendimiento sin que cada panel maneje su propio estado.
 *
 * Gestos táctiles (estilo TradingView): arrastre horizontal desplaza con inercia, arrastre vertical
 * es el scroll de la página (el contenedor va con `touch-action: pan-y`), toque fija la cruz,
 * mantener apretado y arrastrar recorre las velas, pellizco hace zoom anclado a los dedos y doble
 * toque vuelve a todo el período. Con mouse: arrastre, rueda (zoom; horizontal del trackpad =
 * desplazamiento) y doble clic. El hover del mouse no pasa por acá: es de `crosshair.ts`.
 *
 * Los listeners son nativos y no props de React: los de React son pasivos para `wheel`/`touchmove`
 * y no dejarían llamar a `preventDefault`, que es justamente lo que separa "este gesto es del
 * gráfico" de "este gesto es scroll de la página".
 *
 * Cada gesto calcula la ventana desde su estado inicial (no por deltas acumulados) y los cambios se
 * aplican a lo sumo una vez por frame: re-renderizar por cada evento intermedio es tirar frames.
 *
 * La ventana se resetea sola cuando cambia la serie (otro ticker, otro período, otro backtest):
 * dejar el tramo anterior mostraría un rango que ya no significa lo mismo.
 */
export function useVentanaVisible(
  n: number,
  ancho: number,
  ref: RefObject<HTMLElement | null>,
  opciones: OpcionesGestos,
): ControlesVentana {
  const [ventana, setVentana] = useState<Ventana>(() => ({ inicio: 0, fin: Math.max(0, n - 1) }))
  const [arrastrando, setArrastrando] = useState(false)

  // Lo que leen los listeners: siempre el último valor, sin volver a registrarlos en cada render.
  const ventanaRef = useRef(ventana)
  const anchoRef = useRef(ancho)
  anchoRef.current = ancho
  const nRef = useRef(n)
  nRef.current = n
  const opcionesRef = useRef(opciones)
  opcionesRef.current = opciones

  const frameRef = useRef<number | null>(null)
  const inerciaRef = useRef<number | null>(null)

  const aplicar = useCallback((v: Ventana) => {
    ventanaRef.current = v
    if (frameRef.current != null) return
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null
      setVentana(ventanaRef.current)
    })
  }, [])

  const detenerInercia = useCallback(() => {
    if (inerciaRef.current != null) cancelAnimationFrame(inerciaRef.current)
    inerciaRef.current = null
  }, [])

  const serie = opciones.serie
  // Contra qué se compara para saber si la serie cambió. Arranca con la del primer render: montar el
  // gráfico no es un cambio (abrir la pantalla completa monta otro sobre la misma serie y no tiene
  // que borrar la cruz que se venía mirando).
  const serieVistaRef = useRef({ n, serie })
  useEffect(() => {
    const previa = serieVistaRef.current
    if (previa.n === n && previa.serie === serie) return
    serieVistaRef.current = { n, serie }
    detenerInercia()
    const v = { inicio: 0, fin: Math.max(0, n - 1) }
    ventanaRef.current = v
    setVentana(v)
    opcionesRef.current.onCambioSerie?.()
  }, [n, serie, detenerInercia])

  useEffect(() => () => {
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    detenerInercia()
  }, [detenerInercia])

  /** Posición en barras (con fracción) bajo la coordenada `x` del panel. */
  const posicionEn = useCallback((x: number) => {
    const v = ventanaRef.current
    return v.inicio + (x * (v.fin - v.inicio + 1)) / (anchoRef.current || 1)
  }, [])

  /** Zoom que deja quieta la barra que está bajo `x` (o el centro del panel). */
  const zoomEn = useCallback((factor: number, x?: number) => {
    const v = ventanaRef.current
    const a = anchoRef.current || 1
    const px = x ?? a / 2
    const u = posicionEn(px)
    const visibles = visiblesPermitidos((v.fin - v.inicio + 1) / factor, nRef.current)
    aplicar(acotar(u - (px * visibles) / a, visibles, nRef.current))
  }, [aplicar, posicionEn])

  const zoom = useCallback((factor: number) => {
    detenerInercia()
    zoomEn(factor)
  }, [detenerInercia, zoomEn])

  const reset = useCallback(() => {
    detenerInercia()
    aplicar({ inicio: 0, fin: Math.max(0, nRef.current - 1) })
  }, [aplicar, detenerInercia])

  const activo = opciones.activo
  useEffect(() => {
    const el = ref.current
    if (!el || !activo) return
    const contenedor: HTMLElement = el

    let gesto: Gesto = { tipo: 'nada' }
    let timerCruz: number | null = null
    let ultimoToque = 0
    let toqueAnterior: { t: number; x: number; y: number } | null = null
    let muestras: { t: number; inicio: number }[] = []
    let cruzPendiente: number | null = null
    let frameCruz: number | null = null
    let arrastreMouse: { x0: number; inicio0: number; visibles: number } | null = null

    const xEnPanel = (clientX: number) => clientX - contenedor.getBoundingClientRect().left
    const indiceEn = (x: number) => Math.min(nRef.current - 1, Math.max(0, Math.floor(posicionEn(x))))

    function limpiarTimer() {
      if (timerCruz != null) window.clearTimeout(timerCruz)
      timerCruz = null
    }

    function pedirCruz(indice: number) {
      cruzPendiente = indice
      if (frameCruz != null) return
      frameCruz = requestAnimationFrame(() => {
        frameCruz = null
        if (cruzPendiente != null) opcionesRef.current.onCruz?.(cruzPendiente)
      })
    }

    function iniciarInercia() {
      if (muestras.length < 2) return
      const primera = muestras[0]
      const ultima = muestras[muestras.length - 1]
      // Si el dedo se quedó quieto antes de soltar, no hay envión.
      if (performance.now() - ultima.t > 60 || ultima.t - primera.t <= 0) return
      let velocidad = (ultima.inicio - primera.inicio) / (ultima.t - primera.t) // barras por ms
      let previo = performance.now()

      const paso = (ahora: number) => {
        const dt = Math.min(40, ahora - previo)
        previo = ahora
        const v = ventanaRef.current
        const visibles = v.fin - v.inicio + 1
        const nueva = acotar(v.inicio + velocidad * dt, visibles, nRef.current)
        const pxPorFrame = (Math.abs(velocidad) * 16 * (anchoRef.current || 1)) / visibles
        // Se frena al llegar a un extremo o cuando el movimiento ya no se nota.
        if (Math.abs(nueva.inicio - v.inicio) < 1e-4 || pxPorFrame < 0.3) {
          inerciaRef.current = null
          return
        }
        ventanaRef.current = nueva
        setVentana(nueva)
        velocidad *= Math.pow(FRICCION, dt / 16)
        inerciaRef.current = requestAnimationFrame(paso)
      }
      inerciaRef.current = requestAnimationFrame(paso)
    }

    function buscarToque(lista: TouchList, id: number): Touch | undefined {
      for (let i = 0; i < lista.length; i++) if (lista[i].identifier === id) return lista[i]
      return undefined
    }

    function onTouchStart(e: TouchEvent) {
      ultimoToque = Date.now()
      detenerInercia()
      limpiarTimer()

      if (gesto.tipo === 'propio' || esGestoPropio(e.target)) {
        gesto = { tipo: 'propio' }
        return
      }

      if (e.touches.length >= 2) {
        const a = e.touches[0]
        const b = e.touches[1]
        const x1 = xEnPanel(a.clientX)
        const x2 = xEnPanel(b.clientX)
        if (Math.abs(x2 - x1) < 10 || nRef.current <= MINIMO_VISIBLE) {
          gesto = { tipo: 'ignorar' }
          return
        }
        gesto = { tipo: 'pellizco', id1: a.identifier, id2: b.identifier, u1: posicionEn(x1), u2: posicionEn(x2) }
        if (e.cancelable) e.preventDefault()
        return
      }

      const t = e.touches[0]
      if (!t) return
      gesto = { tipo: 'pendiente', x0: t.clientX, y0: t.clientY, xActual: t.clientX }
      timerCruz = window.setTimeout(() => {
        timerCruz = null
        if (gesto.tipo !== 'pendiente') return
        const x = gesto.xActual
        gesto = { tipo: 'cruz' }
        navigator.vibrate?.(8)
        pedirCruz(indiceEn(xEnPanel(x)))
      }, DEMORA_CRUZ)
    }

    function onTouchMove(e: TouchEvent) {
      ultimoToque = Date.now()
      const g = gesto

      if (g.tipo === 'propio') {
        if (e.cancelable) e.preventDefault()
        return
      }

      if (g.tipo === 'pellizco') {
        const a = buscarToque(e.touches, g.id1)
        const b = buscarToque(e.touches, g.id2)
        if (!a || !b) return
        if (e.cancelable) e.preventDefault()
        const x1 = xEnPanel(a.clientX)
        const x2 = xEnPanel(b.clientX)
        if (Math.abs(x2 - x1) < 10) return
        const ancho = anchoRef.current || 1
        const pedidos = ((g.u2 - g.u1) * ancho) / (x2 - x1)
        if (!(pedidos > 0)) return
        const visibles = visiblesPermitidos(pedidos, nRef.current)
        aplicar(acotar(g.u1 - (x1 * visibles) / ancho, visibles, nRef.current))
        return
      }

      const t = e.touches[0]
      if (!t) return

      if (g.tipo === 'pendiente') {
        g.xActual = t.clientX
        const dx = t.clientX - g.x0
        const dy = t.clientY - g.y0
        if (Math.max(Math.abs(dx), Math.abs(dy)) < UMBRAL_MOVIMIENTO) return
        limpiarTimer()
        if (Math.abs(dx) > Math.abs(dy)) {
          const v = ventanaRef.current
          gesto = { tipo: 'desplazando', x0: t.clientX, inicio0: v.inicio, visibles: v.fin - v.inicio + 1 }
          muestras = [{ t: performance.now(), inicio: v.inicio }]
          if (e.cancelable) e.preventDefault()
        } else {
          // Vertical: es scroll de la página y lo maneja el navegador.
          gesto = { tipo: 'ignorar' }
        }
        return
      }

      if (g.tipo === 'desplazando') {
        if (e.cancelable) e.preventDefault()
        const inicio = g.inicio0 + ((g.x0 - t.clientX) * g.visibles) / (anchoRef.current || 1)
        const nueva = acotar(inicio, g.visibles, nRef.current)
        aplicar(nueva)
        const ahora = performance.now()
        muestras.push({ t: ahora, inicio: nueva.inicio })
        while (muestras.length > 2 && ahora - muestras[0].t > 100) muestras.shift()
        return
      }

      if (g.tipo === 'cruz') {
        if (e.cancelable) e.preventDefault()
        pedirCruz(indiceEn(xEnPanel(t.clientX)))
      }
    }

    function onTouchEnd(e: TouchEvent) {
      ultimoToque = Date.now()
      limpiarTimer()
      if (e.touches.length > 0) {
        // Se levantó uno de los dos dedos del pellizco: el que queda no arranca otro gesto.
        if (gesto.tipo === 'pellizco') gesto = { tipo: 'ignorar' }
        return
      }
      if (gesto.tipo === 'propio') {
        gesto = { tipo: 'nada' }
        // Que el toque sobre la manija no mueva la cruz con un `mousemove` emulado.
        if (e.cancelable) e.preventDefault()
        return
      }
      const g = gesto
      gesto = { tipo: 'nada' }

      if (g.tipo === 'desplazando') {
        iniciarInercia()
        return
      }
      if (g.tipo !== 'pendiente') return

      // Toque corto. `preventDefault` evita los eventos de mouse emulados (un `mousemove` fantasma
      // movería la cruz que el toque acaba de fijar).
      if (e.cancelable) e.preventDefault()
      const t = e.changedTouches[0]
      if (!t) return
      const ahora = Date.now()
      if (
        toqueAnterior
        && ahora - toqueAnterior.t < DOBLE_TOQUE_MS
        && Math.hypot(t.clientX - toqueAnterior.x, t.clientY - toqueAnterior.y) < DOBLE_TOQUE_PX
      ) {
        toqueAnterior = null
        reset()
        return
      }
      toqueAnterior = { t: ahora, x: t.clientX, y: t.clientY }
      opcionesRef.current.onToque?.(indiceEn(xEnPanel(t.clientX)))
    }

    function onTouchCancel() {
      limpiarTimer()
      gesto = { tipo: 'nada' }
    }

    function onWheel(e: WheelEvent) {
      if (nRef.current <= MINIMO_VISIBLE) return
      e.preventDefault()
      detenerInercia()
      const escala = e.deltaMode === 1 ? 16 : 1
      const dx = e.deltaX * escala
      const dy = e.deltaY * escala
      if (Math.abs(dx) > Math.abs(dy)) {
        // Trackpad hacia el costado: desplazamiento, no zoom.
        const v = ventanaRef.current
        const visibles = v.fin - v.inicio + 1
        aplicar(acotar(v.inicio + (dx * visibles) / (anchoRef.current || 1), visibles, nRef.current))
        return
      }
      zoomEn(Math.exp(-Math.max(-100, Math.min(100, dy)) * 0.0025), xEnPanel(e.clientX))
    }

    function onPointerMoveVentana(e: PointerEvent) {
      const a = arrastreMouse
      if (!a) return
      const inicio = a.inicio0 + ((a.x0 - e.clientX) * a.visibles) / (anchoRef.current || 1)
      aplicar(acotar(inicio, a.visibles, nRef.current))
    }

    function onPointerUpVentana() {
      arrastreMouse = null
      setArrastrando(false)
      window.removeEventListener('pointermove', onPointerMoveVentana)
      window.removeEventListener('pointerup', onPointerUpVentana)
    }

    // El seguimiento del arrastre va en `window`: si el puntero se va del gráfico con el botón
    // apretado, el desplazamiento tiene que seguir (y el `pointerup` de afuera, terminarlo).
    function onPointerDown(e: PointerEvent) {
      if (e.pointerType !== 'mouse' || e.button !== 0 || esGestoPropio(e.target)) return
      detenerInercia()
      const v = ventanaRef.current
      arrastreMouse = { x0: e.clientX, inicio0: v.inicio, visibles: v.fin - v.inicio + 1 }
      setArrastrando(true)
      window.addEventListener('pointermove', onPointerMoveVentana)
      window.addEventListener('pointerup', onPointerUpVentana)
    }

    function onDoubleClick() {
      if (Date.now() - ultimoToque < IGNORAR_MOUSE_TRAS_TOQUE) return
      reset()
    }

    /** Mantener apretado abre el menú contextual en algunos Android: es el gesto de la cruz. */
    function onContextMenu(e: Event) {
      if (Date.now() - ultimoToque < IGNORAR_MOUSE_TRAS_TOQUE) e.preventDefault()
    }

    contenedor.addEventListener('touchstart', onTouchStart, { passive: false })
    contenedor.addEventListener('touchmove', onTouchMove, { passive: false })
    contenedor.addEventListener('touchend', onTouchEnd, { passive: false })
    contenedor.addEventListener('touchcancel', onTouchCancel)
    contenedor.addEventListener('wheel', onWheel, { passive: false })
    contenedor.addEventListener('pointerdown', onPointerDown)
    contenedor.addEventListener('dblclick', onDoubleClick)
    contenedor.addEventListener('contextmenu', onContextMenu)
    return () => {
      limpiarTimer()
      if (frameCruz != null) cancelAnimationFrame(frameCruz)
      contenedor.removeEventListener('touchstart', onTouchStart)
      contenedor.removeEventListener('touchmove', onTouchMove)
      contenedor.removeEventListener('touchend', onTouchEnd)
      contenedor.removeEventListener('touchcancel', onTouchCancel)
      contenedor.removeEventListener('wheel', onWheel)
      contenedor.removeEventListener('pointerdown', onPointerDown)
      contenedor.removeEventListener('dblclick', onDoubleClick)
      contenedor.removeEventListener('contextmenu', onContextMenu)
      onPointerUpVentana()
    }
  }, [ref, activo, aplicar, detenerInercia, posicionEn, reset, zoomEn])

  return {
    ventana,
    completa: ventana.inicio <= 1e-6 && ventana.fin >= n - 1 - 1e-6,
    zoom,
    reset,
    arrastrando,
  }
}

/** Estilo del contenedor de los paneles: el scroll vertical de la página sigue siendo del
 * navegador (`pan-y`); el horizontal y el pellizco, del gráfico. */
export function estiloContenedorGestos(): CSSProperties {
  return {
    touchAction: 'pan-y',
    WebkitTouchCallout: 'none',
    WebkitUserSelect: 'none',
    userSelect: 'none',
  }
}
