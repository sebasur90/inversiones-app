import type { MatrizCorrelacionParItem } from '../../api'
import { heatmapIntensity } from '../../utils'
import Card from '../ui/Card'

export interface CeldaSeleccionada {
  i: number
  j: number
}

interface Props {
  tickers: string[]
  matriz: (number | null)[][]
  pares: MatrizCorrelacionParItem[]
  seleccion: CeldaSeleccionada | null
  onSeleccionar: (sel: CeldaSeleccionada | null) => void
}

export default function MatrizCorrelacionHeatmap({ tickers, matriz, pares, seleccion, onSeleccionar }: Props) {
  const parPorClave = new Map<string, MatrizCorrelacionParItem>()
  for (const p of pares) {
    parPorClave.set(`${p.ticker_a}|${p.ticker_b}`, p)
    parPorClave.set(`${p.ticker_b}|${p.ticker_a}`, p)
  }

  function toggle(i: number, j: number) {
    if (i === j) return
    const esLaMisma = seleccion?.i === i && seleccion?.j === j
    onSeleccionar(esLaMisma ? null : { i, j })
  }

  return (
    <Card className="overflow-x-auto">
      <table className="text-label border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-app-surface pb-2 pr-2" />
            {tickers.map((t, j) => (
              <th
                key={t}
                className={`text-center font-bold uppercase text-label pb-2 px-0.5 min-w-[44px] ${
                  seleccion && (seleccion.j === j || seleccion.i === j) ? 'text-app-text' : 'text-app-text-faint'
                }`}
              >
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((tickerFila, i) => (
            <tr key={tickerFila}>
              <td
                className={`sticky left-0 z-10 bg-app-surface font-semibold py-1 pr-2 whitespace-nowrap ${
                  seleccion && (seleccion.i === i || seleccion.j === i) ? 'text-app-text' : 'text-app-text-dim'
                }`}
              >
                {tickerFila}
              </td>
              {tickers.map((tickerCol, j) => {
                const valor = matriz[i]?.[j] ?? null
                const esDiagonal = i === j
                const par = esDiagonal ? null : parPorClave.get(`${tickerFila}|${tickerCol}`)
                const sinDato = !esDiagonal && (par?.estado !== 'ok' || valor == null)
                const activa = seleccion && ((seleccion.i === i && seleccion.j === j) || (seleccion.i === j && seleccion.j === i))
                const label = esDiagonal
                  ? `${tickerFila}: correlación consigo mismo, 1.00`
                  : sinDato
                  ? `${tickerFila} vs ${tickerCol}: sin datos suficientes`
                  : `${tickerFila} vs ${tickerCol}: ${valor!.toFixed(2)}`
                return (
                  <td
                    key={tickerCol}
                    role={esDiagonal ? undefined : 'button'}
                    tabIndex={esDiagonal ? undefined : 0}
                    aria-label={label}
                    title={label}
                    onClick={esDiagonal ? undefined : () => toggle(i, j)}
                    onKeyDown={esDiagonal ? undefined : e => (e.key === 'Enter' || e.key === ' ') && toggle(i, j)}
                    className={`text-center font-mono tabular-nums py-1.5 px-0.5 rounded-[4px] ${
                      esDiagonal || sinDato ? 'text-app-text-faint' : 'text-app-text'
                    } ${activa ? 'ring-2 ring-app-accent' : ''} ${esDiagonal ? '' : 'cursor-pointer'}`}
                    style={esDiagonal ? undefined : heatmapIntensity(valor, 100)}
                  >
                    {esDiagonal ? '1.00' : sinDato ? '—' : valor!.toFixed(2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
