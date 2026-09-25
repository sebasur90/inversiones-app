import dayjs from 'dayjs'
import type { AporteObjetivo } from '../../api'
import Card from '../ui/Card'
import Button from '../ui/Button'
import BarraProgreso from '../ui/BarraProgreso'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'
import { mesCorto, meses } from './comun'

/** Objetivo del mes en curso: cuánto llevás, cuánto falta y a qué ritmo llegarías.
 *
 *  Sin objetivo configurado no se inventa ninguno: se invita a definirlo. Los mensajes son
 *  descriptivos ("te faltan USD 60"), nunca exhortaciones a aportar más. */
export default function ObjetivoMesCard({
  objetivo,
  onConfigurar,
}: {
  objetivo: AporteObjetivo
  onConfigurar: () => void
}) {
  const mesNombre = dayjs().format('MMMM')

  if (!objetivo.configurado || !objetivo.mes_actual) {
    return (
      <Card className="mb-4">
        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
          <InfoTooltip term="aportes_meta_mensual" label="Objetivo del mes" />
        </div>
        <div className="text-body font-bold text-app-text">Todavía no definiste un objetivo</div>
        <div className="text-caption text-app-text-dim mt-1 mb-3">
          Fijá cuánto querés aportar por mes y vas a poder ver tu cumplimiento, tu racha de meses
          cumplidos y desbloquear los logros de objetivo.
        </div>
        <Button onClick={onConfigurar}>Definir objetivo mensual</Button>
      </Card>
    )
  }

  const m = objetivo.mes_actual
  const pctCumplido = m.cumplimiento_pct ?? 0
  const tono = m.cumplido ? 'pos' : m.alcanzable_al_ritmo_actual ? 'accent' : 'warn'

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">
          <InfoTooltip term="aportes_meta_mensual" label={`Objetivo de ${mesNombre}`} />
        </div>
        <button onClick={onConfigurar} className="text-label font-semibold text-app-accent">
          Editar
        </button>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-mono text-metric-lg font-bold tabular-nums text-app-text">
          {formatUSD(m.aportado_usd)}
        </span>
        <span className="font-mono text-body text-app-text-dim tabular-nums">
          / {formatUSD(m.objetivo_usd)}
        </span>
        {m.cumplido && <span className="text-label font-semibold text-app-pos">✓ cumplido</span>}
      </div>

      <div className="mt-2 mb-1.5">
        <BarraProgreso pct={pctCumplido} tono={tono} />
      </div>
      <div className="flex justify-between text-caption">
        <span className="font-mono tabular-nums text-app-text-dim">{pctCumplido.toFixed(0)}%</span>
        <span className="text-app-text-dim">
          {m.cumplido ? 'Objetivo alcanzado' : `Te faltan ${formatUSD(m.restante_usd)}`}
        </span>
      </div>

      {!m.cumplido && (
        <div className="text-caption text-app-text-dim mt-3">
          {m.alcanzable_al_ritmo_actual ? (
            <>Al ritmo de este mes llegás al objetivo antes de que termine.</>
          ) : m.ritmo_necesario_semanal_usd != null ? (
            <>
              Para alcanzarlo harían falta unos{' '}
              <span className="font-mono font-semibold text-app-text">
                {formatUSD(m.ritmo_necesario_semanal_usd)}
              </span>{' '}
              por semana en los {m.dias_restantes} días que quedan.
            </>
          ) : (
            <>El mes ya termina: lo que falte queda para el próximo.</>
          )}
        </div>
      )}

      {(objetivo.meses_evaluados ?? 0) > 0 && (
        <div className="text-label text-app-text-faint mt-3 pt-3 border-t border-app-border">
          Cumpliste {objetivo.meses_cumplidos} de {objetivo.meses_evaluados}{' '}
          {objetivo.meses_evaluados === 1 ? 'mes evaluado' : 'meses evaluados'}
          {(objetivo.racha_cumplimiento ?? 0) > 0 && <> · racha de {meses(objetivo.racha_cumplimiento!)}</>}
          {objetivo.retroactivo
            ? ' · aplicado a todo tu historial'
            : ` · desde ${mesCorto(objetivo.vigente_desde)}`}
        </div>
      )}
      {objetivo.meses_evaluados === 0 && (
        <div className="text-label text-app-text-faint mt-3 pt-3 border-t border-app-border">
          El cumplimiento se mide desde {mesCorto(objetivo.vigente_desde)}: todavía no hay meses
          cerrados para evaluar.
        </div>
      )}
    </Card>
  )
}
