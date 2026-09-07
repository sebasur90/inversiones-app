/** Configuración de indicadores para el selector y los paneles del gráfico técnico.
 * Espejo liviano, del lado del front, de `INDICADORES` en `services/indicadores_engine.py`. */

export type DestinoIndicador = 'precio' | 'oscilador' | 'volumen'

export interface ParamEspec {
  nombre: string
  label: string
  default: number
  min: number
  max: number
  step?: number
}

export interface EspecIndicadorUi {
  tipo: string
  label: string
  destino: DestinoIndicador
  /** Espejo de `EspecIndicador.salidas` del backend: los nombres de serie que produce el
   * indicador. Un solo elemento (`['valor']`) = mono-salida. Es la única fuente de verdad para
   * poblar los selectores de operando del editor y para excluir salidas de un panel. */
  salidas: string[]
  params: ParamEspec[]
  color: string
  necesitaVolumen?: boolean
  /** Clave de ayuda contextual (`HelpKey`), si el indicador tiene una nota que conviene mostrar
   * en el selector — p.ej. el alcance de "histórico" de EXTREMOS/PERCENTIL con `ventana=0`. */
  ayuda?: string
}

export const INDICADORES_UI: EspecIndicadorUi[] = [
  { tipo: 'SMA', label: 'Media móvil simple', destino: 'precio', color: '#d8b14a', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 50, min: 2, max: 500 }] },
  { tipo: 'EMA', label: 'Media móvil exponencial', destino: 'precio', color: '#5b8ba0', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 20, min: 2, max: 500 }] },
  { tipo: 'BOLLINGER', label: 'Bandas de Bollinger', destino: 'precio', color: '#9c7aa0',
    salidas: ['media', 'superior', 'inferior', 'ancho_pct', 'pctb'],
    params: [
      { nombre: 'periodo', label: 'Período', default: 20, min: 2, max: 500 },
      { nombre: 'desvios', label: 'Desvíos', default: 2, min: 0.5, max: 4, step: 0.5 },
    ] },
  { tipo: 'EXTREMOS', label: 'Extremos (canal)', destino: 'precio', color: '#c98a3c',
    salidas: ['maximo', 'minimo', 'medio', 'dist_max_pct', 'dist_min_pct'],
    ayuda: 'analisis_tecnico_extremos',
    params: [{ nombre: 'ventana', label: 'Ventana', default: 20, min: 0, max: 500 }] },
  { tipo: 'RSI', label: 'RSI', destino: 'oscilador', color: '#9c7aa0', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 14, min: 2, max: 500 }] },
  { tipo: 'MACD', label: 'MACD', destino: 'oscilador', color: '#4fd1ae', salidas: ['macd', 'senal', 'histograma'],
    params: [
      { nombre: 'rapida', label: 'Rápida', default: 12, min: 1, max: 500 },
      { nombre: 'lenta', label: 'Lenta', default: 26, min: 2, max: 500 },
      { nombre: 'senal', label: 'Señal', default: 9, min: 1, max: 500 },
    ] },
  { tipo: 'ESTOCASTICO', label: 'Estocástico', destino: 'oscilador', color: '#5b8ba0', salidas: ['k', 'd'],
    params: [
      { nombre: 'periodo_k', label: '%K', default: 14, min: 1, max: 500 },
      { nombre: 'suavizado_k', label: 'Suavizado %K', default: 3, min: 1, max: 100 },
      { nombre: 'periodo_d', label: '%D', default: 3, min: 1, max: 100 },
    ] },
  { tipo: 'ATR', label: 'ATR', destino: 'oscilador', color: '#e2665a', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 14, min: 2, max: 500 }] },
  { tipo: 'PERCENTIL', label: 'Percentil', destino: 'oscilador', color: '#7aa07a', salidas: ['valor'],
    ayuda: 'analisis_tecnico_percentil',
    params: [{ nombre: 'ventana', label: 'Ventana', default: 100, min: 0, max: 500 }] },
  { tipo: 'RETORNO', label: 'Retorno %', destino: 'oscilador', color: '#c07a9c', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 20, min: 1, max: 500 }] },
  { tipo: 'OBV', label: 'On Balance Volume', destino: 'volumen', color: '#4fd1ae', salidas: ['valor'], necesitaVolumen: true, params: [] },
  { tipo: 'VOLUMEN_PROMEDIO', label: 'Volumen promedio', destino: 'volumen', color: '#d8b14a', salidas: ['valor'],
    params: [{ nombre: 'periodo', label: 'Período', default: 20, min: 2, max: 500 }], necesitaVolumen: true },
]

export const ESPEC_POR_TIPO: Record<string, EspecIndicadorUi> = Object.fromEntries(
  INDICADORES_UI.map(e => [e.tipo, e]),
)

/** Espejo de `indicadores_engine.clave()`: "SMA(50)", "MACD(12,26,9)", "OBV" (sin params). */
export function claveIndicador(tipo: string, params: Record<string, number>): string {
  const espec = ESPEC_POR_TIPO[tipo]
  if (!espec || espec.params.length === 0) return tipo
  return `${tipo}(${espec.params.map(p => params[p.nombre] ?? p.default).join(',')})`
}

export function paramsPorDefecto(tipo: string): Record<string, number> {
  const espec = ESPEC_POR_TIPO[tipo]
  if (!espec) return {}
  return Object.fromEntries(espec.params.map(p => [p.nombre, p.default]))
}
