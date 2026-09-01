import type { CorrelacionesOut } from '../../api'
import { heatmapIntensity } from '../../utils'
import Card from '../ui/Card'

interface CorrelacionMatrizProps {
  data: CorrelacionesOut
}

export default function CorrelacionMatriz({ data }: CorrelacionMatrizProps) {
  const { tickers, matriz, pares } = data

  const estadoPorPar = new Map<string, string>()
  for (const p of pares) {
    estadoPorPar.set(`${p.ticker_a}|${p.ticker_b}`, p.estado)
    estadoPorPar.set(`${p.ticker_b}|${p.ticker_a}`, p.estado)
  }

  return (
    <Card className="overflow-x-auto">
      <table className="text-label border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-app-surface pb-2 pr-2" />
            {tickers.map(t => (
              <th key={t} className="text-center text-app-text-faint font-bold uppercase text-label pb-2 px-0.5 min-w-[44px]">
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((tickerFila, i) => (
            <tr key={tickerFila}>
              <td className="sticky left-0 z-10 bg-app-surface font-semibold text-app-text py-1 pr-2 whitespace-nowrap">
                {tickerFila}
              </td>
              {tickers.map((tickerCol, j) => {
                const valor = matriz[i]?.[j] ?? null
                const esDiagonal = i === j
                const estado = esDiagonal ? 'ok' : estadoPorPar.get(`${tickerFila}|${tickerCol}`)
                const sinDato = estado !== 'ok' || valor == null
                return (
                  <td
                    key={tickerCol}
                    className={`text-center font-mono tabular-nums py-1.5 px-0.5 rounded-[4px] ${
                      esDiagonal ? 'text-app-text-faint' : sinDato ? 'text-app-text-faint' : 'text-app-text'
                    }`}
                    style={esDiagonal ? undefined : heatmapIntensity(valor, 100)}
                  >
                    {sinDato ? '—' : valor!.toFixed(2)}
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
