import { useMemo } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import { useMontosOcultos } from '../utils/privacidad'
import {
  formatCompacto,
  formatMonto,
  montoCompactoOculto,
  type Granularidad,
  type Moneda,
} from '../utils/formatoMonto'

export interface FormatoMoneda {
  moneda: Moneda
  esARS: boolean
  /** Si el modo privacidad está activo. Para textos que hablan del monto en vez de mostrarlo. */
  ocultos: boolean
  /** Un importe de la cartera. `null` sigue siendo `—`: tapar no debe inventar datos. */
  monto: (v: number | null | undefined) => string
  /** Igual que `monto` pero con el `+` explícito en los positivos (deltas, variaciones). */
  montoConSigno: (v: number | null | undefined) => string
  /** Abreviado para ejes de gráficos y celdas angostas (`U$S 34K`). */
  compacto: (v: number) => string
  /** Abreviado con un escalón más entre 1k y 10k, para tablas de muchas columnas (`$1.2k`). */
  compactoFino: (v: number) => string
}

/**
 * Formateadores de importes de la cartera, sujetos al modo privacidad. **Toda cifra que salga de
 * las tenencias, movimientos o aportes del usuario va por acá**; los precios de mercado y el
 * capital simulado de los backtests usan los formateadores crudos de `utils.ts`.
 *
 * Para una moneda que no dependa del selector del encabezado (los aportes, por ejemplo, son
 * siempre USD) usar `useFormatoFijo('USD')` — si esos archivos leyeran el contexto empezarían a
 * seguir el toggle USD/ARS, que sería otro cambio disfrazado de privacidad.
 */
export function useFormatoFijo(moneda: Moneda): FormatoMoneda {
  const ocultos = useMontosOcultos()

  // Memoizado: `compacto` se pasa como `tickFormatter` a Recharts, así que su identidad tiene que
  // cambiar sólo cuando cambia la moneda o el interruptor, no en cada render del padre.
  return useMemo<FormatoMoneda>(() => {
    const monto = (v: number | null | undefined): string => formatMonto(v, moneda, ocultos)
    const compactoCon = (granularidad: Granularidad) => (v: number): string =>
      ocultos ? montoCompactoOculto(moneda, granularidad, v < 0) : formatCompacto(v, moneda, granularidad)

    return {
      moneda,
      esARS: moneda === 'ARS',
      ocultos,
      monto,
      montoConSigno: v => (v != null && v >= 0 ? `+${monto(v)}` : monto(v)),
      compacto: compactoCon('normal'),
      compactoFino: compactoCon('fina'),
    }
  }, [moneda, ocultos])
}

/** Como `useFormatoFijo`, en la moneda elegida en el encabezado. */
export function useFormatoMoneda(): FormatoMoneda {
  const { monedaSeleccionada } = useInversionesContext()
  return useFormatoFijo(monedaSeleccionada)
}
