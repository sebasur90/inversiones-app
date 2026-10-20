import type { DescomposicionFxOut } from '../../api'
import { formatPctRatio } from '../../utils'
import AvisoCalculo from '../inversiones/AvisoCalculo'
import Card from '../ui/Card'
import EmptyState from '../ui/EmptyState'
import InfoTooltip from '../../help/components/InfoTooltip'

function colorDe(v: number): string {
  return v >= 0 ? 'text-app-pos' : 'text-app-neg'
}

/** La conclusión en una frase, a partir de los tres números que ya devuelve el backend. */
function frase(total: number, activos: number, dolar: number): string {
  if (activos < 0 && total > 0) {
    return 'Tus activos perdieron valor en dólares: lo que ganaste en pesos vino de la suba del dólar.'
  }
  if (dolar < 0) {
    return `El dólar bajó ${formatPctRatio(Math.abs(dolar)).replace('+', '')} y le restó a tu resultado en pesos.`
  }
  if (Math.abs(dolar) > Math.abs(activos)) {
    return `La mayor parte de lo que ganaste en pesos vino de la suba del dólar. Tus activos, medidos en dólares, rindieron ${formatPctRatio(activos)}.`
  }
  return `La mayor parte vino de tus activos, que rindieron ${formatPctRatio(activos)} en dólares. El dólar sumó ${formatPctRatio(dolar)}.`
}

function Barra({ label, nota, valor, maximo, color }: { label: string; nota?: string; valor: number; maximo: number; color: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between gap-3 text-body">
        <span className="font-semibold text-app-text">
          {label} {nota && <span className="font-normal text-app-text-dim">{nota}</span>}
        </span>
        <span className={`font-mono font-bold tabular-nums shrink-0 ${colorDe(valor)}`}>{formatPctRatio(valor)}</span>
      </div>
      <div aria-hidden="true" className="h-2 rounded bg-app-surface-2">
        <div className="h-2 rounded" style={{ width: `${maximo > 0 ? Math.min((Math.abs(valor) / maximo) * 100, 100) : 0}%`, background: color }} />
      </div>
    </div>
  )
}

export default function ActivosVsDolar({ fx }: { fx: DescomposicionFxOut }) {
  const total = fx.retorno_total_ars_pct
  const activos = fx.retorno_activo_pct
  const dolar = fx.efecto_fx_pct

  if (fx.estado !== 'ok' || total == null || activos == null || dolar == null) {
    return (
      <Card>
        <EmptyState
          title="Descomposición no disponible"
          description={
            fx.estado === 'mep_faltante'
              ? 'No hay datos de MEP suficientes para este período.'
              : 'No hay suficiente historial para separar lo que ganaste por tus activos de lo que ganaste por el dólar.'
          }
        />
      </Card>
    )
  }

  const maximo = Math.max(Math.abs(activos), Math.abs(dolar))

  return (
    <Card className="flex flex-col gap-3.5">
      <div className="flex items-baseline justify-between">
        <span className="text-body text-app-text-dim"><InfoTooltip term="rendimiento_ars" label="Rindió en pesos" /></span>
        <span className={`font-mono text-metric font-bold tabular-nums ${colorDe(total)}`}>{formatPctRatio(total)}</span>
      </div>

      <div className="flex flex-col gap-3">
        <Barra label="Tus activos" nota="(en dólares)" valor={activos} maximo={maximo} color="var(--color-app-accent)" />
        <Barra label={dolar >= 0 ? 'La suba del dólar MEP' : 'La baja del dólar MEP'} valor={dolar} maximo={maximo} color="var(--color-app-warn)" />
      </div>

      <p className="px-3 py-2.5 rounded-[10px] bg-app-surface-2 text-body text-app-text-dim">{frase(total, activos, dolar)}</p>

      {fx.mep_aproximado && <AvisoCalculo className="" mensajes={['Datos de MEP desactualizados o estimados.']} />}
      {!fx.identidad_verificada && (
        <AvisoCalculo className="" mensajes={['La descomposición no cierra exactamente (puede deberse a operaciones particulares).']} />
      )}
      <AvisoCalculo className="" mensajes={fx.advertencias ?? []} />
    </Card>
  )
}
