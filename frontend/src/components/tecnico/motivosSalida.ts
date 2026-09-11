/** Cómo se nombra y se dibuja cada motivo de salida del backtest.
 *
 * Los motivos los emite `estrategia_engine` (`Senal.motivo` / `Operacion.motivo_salida`). Tenerlos
 * en un solo lugar es lo que hace que el glifo del gráfico, la fila de la tabla de operaciones y
 * la leyenda digan lo mismo: antes toda venta era un `▼` rojo, y salir por regla o que te saque
 * el stop loss son cosas muy distintas para juzgar una estrategia. */

export const ETIQUETA_MOTIVO: Record<string, string> = {
  entrada: 'Compra',
  regla_salida: 'Regla de salida',
  stop_loss: 'Stop loss',
  take_profit: 'Take profit',
  trailing_stop: 'Trailing stop',
  max_barras: 'Máximo de barras',
}

/** Glifo del marcador en el gráfico. Los de más de un carácter se dibujan en monoespaciada chica. */
export const GLIFO_MOTIVO: Record<string, string> = {
  regla_salida: '▼',
  stop_loss: 'SL',
  take_profit: 'TP',
  trailing_stop: 'TS',
  max_barras: 'T',
}

export const COLOR_MOTIVO: Record<string, string> = {
  regla_salida: '#ef4444',
  stop_loss: '#ef4444',
  take_profit: '#10b981',
  trailing_stop: '#fbbf24',
  max_barras: '#94a3b8',
}

export const DESCRIPCION_MOTIVO: Record<string, string> = {
  regla_salida: 'se cumplió la condición de venta de la estrategia',
  stop_loss: 'el precio cayó al límite de pérdida fijado sobre el precio de entrada',
  take_profit: 'el precio llegó a la ganancia objetivo',
  trailing_stop: 'el precio retrocedió desde su máximo más de lo tolerado',
  max_barras: 'se cumplió el plazo máximo sin que se diera ninguna otra salida',
}

export function etiquetaMotivo(motivo: string | null | undefined): string {
  if (!motivo) return '—'
  return ETIQUETA_MOTIVO[motivo] ?? motivo
}
