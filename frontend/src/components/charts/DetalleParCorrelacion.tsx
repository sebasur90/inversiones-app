import type { MatrizCorrelacionParItem } from '../../api'
import Card from '../ui/Card'

interface Props {
  tickerA: string
  tickerB: string
  par: MatrizCorrelacionParItem | undefined
}

const MOTIVO_TEXTO: Record<string, string> = {
  sin_solapamiento: 'No hay ningún período en común con datos para los dos instrumentos.',
  menos_de_min_obs: 'Hay muy pocos períodos en común como para calcular una correlación confiable.',
  serie_constante: 'Uno de los dos instrumentos no varió de precio en el período: no se puede calcular correlación.',
}

function fraseInterpretativa(valor: number): string {
  if (valor >= 0.7) return 'Se movieron de manera muy similar.'
  if (valor >= 0.3) return 'Se movieron en la misma dirección con bastante frecuencia.'
  if (valor > -0.3) return 'No se observa una relación lineal clara entre los dos.'
  if (valor > -0.7) return 'Se movieron en direcciones opuestas con bastante frecuencia.'
  return 'Se movieron en direcciones opuestas de manera muy marcada.'
}

function colorValor(valor: number): string {
  if (valor > 0.05) return 'text-app-pos'
  if (valor < -0.05) return 'text-app-neg'
  return 'text-app-text-dim'
}

export default function DetalleParCorrelacion({ tickerA, tickerB, par }: Props) {
  if (!par || par.estado !== 'ok' || par.valor == null) {
    const motivo = par ? MOTIVO_TEXTO[par.motivo] ?? 'Sin datos suficientes para este par.' : null
    return (
      <Card>
        <div className="font-semibold text-app-text mb-1">{tickerA} ↔ {tickerB}</div>
        <div className="text-body text-app-text-dim">{motivo ?? 'Tocá una celda de la matriz para ver el detalle del par.'}</div>
      </Card>
    )
  }

  return (
    <Card>
      <div className="font-semibold text-app-text mb-1">{tickerA} ↔ {tickerB}</div>
      <div className={`font-mono text-strong font-bold tabular-nums ${colorValor(par.valor)}`}>{par.valor.toFixed(2)}</div>
      <div className="text-body text-app-text-dim mt-1">{fraseInterpretativa(par.valor)}</div>
      <div className="flex gap-4 mt-3 text-label text-app-text-faint">
        <span>{par.n_obs} observaciones en común</span>
        {par.solapamiento_pct != null && <span>{par.solapamiento_pct.toFixed(0)}% de solapamiento</span>}
      </div>
    </Card>
  )
}
