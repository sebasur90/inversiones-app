import type { Severidad } from '../components/inversiones/SeverityBadge'

/**
 * Estado de una posición respecto de sus niveles de precio (stop-loss y objetivo), que se
 * cargan por ticker desde la pestaña `Instrumentos` del Sheet.
 *
 * El backend sólo distingue "cruzó / no cruzó" (`stop_loss_disparado`, `objetivo_alcanzado`).
 * Los estados `*_cerca` se derivan acá a partir de las distancias que ya vienen calculadas:
 * avisar recién cuando el precio cruzó el nivel no deja margen para reaccionar.
 */
/**
 * Los estados `compra_*` son el mismo mecanismo aplicado a la Watchlist (`WatchlistItemOut`):
 * el `Objetivo` ahí es un precio de compra, así que se cruza hacia abajo -- misma semántica que
 * el stop-loss (`en_zona` equivale a `precio_actual <= precio_objetivo`), y el signo de
 * `pct_a_objetivo` sigue la misma convención.
 */
export type EstadoAlerta =
  | 'stop_loss_disparado' | 'objetivo_alcanzado' | 'stop_loss_cerca' | 'objetivo_cerca'
  | 'compra_en_zona' | 'compra_cerca'

/**
 * Los campos de niveles de precio, que vienen idénticos en `RendimientoPorTickerItem` (la
 * lista de posiciones) y en `TickerPositionOut` (el detalle de un ticker). Se pide sólo esto
 * para que las dos pantallas compartan la misma lógica sin adaptadores.
 */
export interface NivelesPrecio {
  pct_a_objetivo: number | null
  objetivo_alcanzado: boolean | null
  pct_a_stop_loss: number | null
  stop_loss_disparado: boolean | null
}

export interface PosicionConNiveles extends NivelesPrecio {
  ticker: string
  nombre: string
}

/** Los campos de watchlist que hacen falta para calcular su estado de alerta. */
export interface WatchlistConNivel {
  ticker: string
  nombre: string
  pct_a_objetivo: number | null
  en_zona: boolean | null
}

export interface AlertaPrecio {
  ticker: string
  nombre: string
  estado: EstadoAlerta
  severidad: Severidad
  /** Distancia al nivel, como ratio. Ver `estadoAlerta` para el signo. */
  pct: number | null
}

export interface ConteoAlertas {
  criticas: number
  advertencias: number
  info: number
  total: number
}

const CONTEO_VACIO: ConteoAlertas = { criticas: 0, advertencias: 0, info: 0, total: 0 }

const SEVERIDAD_POR_ESTADO: Record<EstadoAlerta, Severidad> = {
  stop_loss_disparado: 'critico',
  stop_loss_cerca: 'advertencia',
  objetivo_cerca: 'advertencia',
  objetivo_alcanzado: 'info',
  // Entrar en zona de compra es accionable (dorado) pero no urgente como un stop-loss; "cerca"
  // es sólo un aviso temprano.
  compra_en_zona: 'advertencia',
  compra_cerca: 'info',
}

// Orden en que se muestran: lo que exige una decisión primero. El stop-loss manda sobre el
// objetivo dentro de cada nivel de urgencia — perder capital pesa más que dejar de tomar
// ganancias —, y un cruce consumado pesa más que una aproximación.
const PRIORIDAD: Record<EstadoAlerta, number> = {
  stop_loss_disparado: 0,
  objetivo_alcanzado: 1,
  stop_loss_cerca: 2,
  objetivo_cerca: 3,
  compra_en_zona: 4,
  compra_cerca: 5,
}

export function severidadDeEstado(estado: EstadoAlerta): Severidad {
  return SEVERIDAD_POR_ESTADO[estado]
}

export function esEstadoDeStopLoss(estado: EstadoAlerta): boolean {
  return estado === 'stop_loss_disparado' || estado === 'stop_loss_cerca'
}

/**
 * El estado de alerta de una posición, o `null` si no tiene niveles cargados o el precio
 * está lejos de ellos.
 *
 * `umbralProximidad` es un ratio (0.05 = 5%); con 0 se apaga la detección de "cerca" y sólo
 * quedan los cruces, que es el comportamiento binario del backend.
 *
 * Sobre el signo de `pct_a_*`: el backend devuelve `(precio_nivel − precio_actual) / precio_actual`.
 * Mientras no se cruzó, el stop-loss queda por debajo del precio (pct negativo) y el objetivo
 * por encima (pct positivo); en ambos casos el valor absoluto es la distancia, así que la misma
 * comparación sirve para los dos.
 */
export function estadoAlerta(item: NivelesPrecio, umbralProximidad: number): EstadoAlerta | null {
  if (item.stop_loss_disparado) return 'stop_loss_disparado'
  if (item.objetivo_alcanzado) return 'objetivo_alcanzado'
  if (umbralProximidad <= 0) return null
  if (item.pct_a_stop_loss != null && Math.abs(item.pct_a_stop_loss) <= umbralProximidad) return 'stop_loss_cerca'
  if (item.pct_a_objetivo != null && Math.abs(item.pct_a_objetivo) <= umbralProximidad) return 'objetivo_cerca'
  return null
}

/** La distancia al nivel que corresponde al estado, para mostrarla junto al badge. */
export function pctDelEstado(item: NivelesPrecio, estado: EstadoAlerta): number | null {
  return esEstadoDeStopLoss(estado) ? item.pct_a_stop_loss : item.pct_a_objetivo
}

/** Posiciones con alguna alerta de precio, ordenadas por urgencia y luego por cercanía al nivel. */
export function alertasDePrecio(items: PosicionConNiveles[], umbralProximidad: number): AlertaPrecio[] {
  const alertas: AlertaPrecio[] = []
  for (const it of items) {
    const estado = estadoAlerta(it, umbralProximidad)
    if (estado === null) continue
    alertas.push({
      ticker: it.ticker,
      nombre: it.nombre,
      estado,
      severidad: severidadDeEstado(estado),
      pct: pctDelEstado(it, estado),
    })
  }
  return alertas.sort((a, b) => {
    const porPrioridad = PRIORIDAD[a.estado] - PRIORIDAD[b.estado]
    if (porPrioridad !== 0) return porPrioridad
    // A igual estado, primero lo más cerca del nivel. Sin distancia va al final.
    return Math.abs(a.pct ?? Infinity) - Math.abs(b.pct ?? Infinity)
  })
}

/** Conteo por severidad para el indicador de la barra de navegación. */
export function contarAlertas(items: NivelesPrecio[], umbralProximidad: number): ConteoAlertas {
  const conteo = { ...CONTEO_VACIO }
  for (const it of items) {
    const estado = estadoAlerta(it, umbralProximidad)
    if (estado === null) continue
    const severidad = severidadDeEstado(estado)
    if (severidad === 'critico') conteo.criticas += 1
    else if (severidad === 'advertencia') conteo.advertencias += 1
    else conteo.info += 1
    conteo.total += 1
  }
  return conteo
}

/**
 * El estado de alerta de un ítem de la Watchlist, o `null` si no tiene objetivo/precio cargado
 * o el precio está lejos de la zona de compra. Mismo contrato que `estadoAlerta`, aplicado a
 * `en_zona`/`pct_a_objetivo` en vez de a los cuatro campos de posiciones.
 */
export function estadoWatchlist(item: WatchlistConNivel, umbralProximidad: number): EstadoAlerta | null {
  if (item.en_zona) return 'compra_en_zona'
  if (umbralProximidad <= 0) return null
  if (item.pct_a_objetivo != null && Math.abs(item.pct_a_objetivo) <= umbralProximidad) return 'compra_cerca'
  return null
}

/** Ítems de la watchlist con alguna alerta, ordenados por urgencia y luego por cercanía. */
export function alertasDeCompra(items: WatchlistConNivel[], umbralProximidad: number): AlertaPrecio[] {
  const alertas: AlertaPrecio[] = []
  for (const it of items) {
    const estado = estadoWatchlist(it, umbralProximidad)
    if (estado === null) continue
    alertas.push({
      ticker: it.ticker,
      nombre: it.nombre,
      estado,
      severidad: severidadDeEstado(estado),
      pct: it.pct_a_objetivo,
    })
  }
  return alertas.sort((a, b) => {
    const porPrioridad = PRIORIDAD[a.estado] - PRIORIDAD[b.estado]
    if (porPrioridad !== 0) return porPrioridad
    return Math.abs(a.pct ?? Infinity) - Math.abs(b.pct ?? Infinity)
  })
}

/** Conteo por severidad de la watchlist, para el contador en el menú Más. */
export function contarAlertasCompra(items: WatchlistConNivel[], umbralProximidad: number): ConteoAlertas {
  const conteo = { ...CONTEO_VACIO }
  for (const it of items) {
    const estado = estadoWatchlist(it, umbralProximidad)
    if (estado === null) continue
    const severidad = severidadDeEstado(estado)
    if (severidad === 'critico') conteo.criticas += 1
    else if (severidad === 'advertencia') conteo.advertencias += 1
    else conteo.info += 1
    conteo.total += 1
  }
  return conteo
}
