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
  params: ParamEspec[]
  color: string
  necesitaVolumen?: boolean
}

export const INDICADORES_UI: EspecIndicadorUi[] = [
  { tipo: 'SMA', label: 'Media móvil simple', destino: 'precio', color: '#d8b14a',
    params: [{ nombre: 'periodo', label: 'Período', default: 50, min: 2, max: 500 }] },
  { tipo: 'EMA', label: 'Media móvil exponencial', destino: 'precio', color: '#5b8ba0',
    params: [{ nombre: 'periodo', label: 'Período', default: 20, min: 2, max: 500 }] },
  { tipo: 'BOLLINGER', label: 'Bandas de Bollinger', destino: 'precio', color: '#9c7aa0',
    params: [
      { nombre: 'periodo', label: 'Período', default: 20, min: 2, max: 500 },
      { nombre: 'desvios', label: 'Desvíos', default: 2, min: 0.5, max: 4, step: 0.5 },
    ] },
  { tipo: 'RSI', label: 'RSI', destino: 'oscilador', color: '#9c7aa0',
    params: [{ nombre: 'periodo', label: 'Período', default: 14, min: 2, max: 500 }] },
  { tipo: 'MACD', label: 'MACD', destino: 'oscilador', color: '#4fd1ae',
    params: [
      { nombre: 'rapida', label: 'Rápida', default: 12, min: 1, max: 500 },
      { nombre: 'lenta', label: 'Lenta', default: 26, min: 2, max: 500 },
      { nombre: 'senal', label: 'Señal', default: 9, min: 1, max: 500 },
    ] },
  { tipo: 'ESTOCASTICO', label: 'Estocástico', destino: 'oscilador', color: '#5b8ba0',
    params: [
      { nombre: 'periodo_k', label: '%K', default: 14, min: 1, max: 500 },
      { nombre: 'suavizado_k', label: 'Suavizado %K', default: 3, min: 1, max: 100 },
      { nombre: 'periodo_d', label: '%D', default: 3, min: 1, max: 100 },
    ] },
  { tipo: 'ATR', label: 'ATR', destino: 'oscilador', color: '#e2665a',
    params: [{ nombre: 'periodo', label: 'Período', default: 14, min: 2, max: 500 }] },
  { tipo: 'OBV', label: 'On Balance Volume', destino: 'volumen', color: '#4fd1ae', params: [], necesitaVolumen: true },
  { tipo: 'VOLUMEN_PROMEDIO', label: 'Volumen promedio', destino: 'volumen', color: '#d8b14a',
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
