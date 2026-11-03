import type { CicloRendCelda, CicloRiesgo, CicloRrg, CicloTendencia } from '../../api'
import MetricTile from '../ui/MetricTile'
import { fechaCorta } from '../../utils/fechas'
import { fmtNum, fmtPct, tonoDe } from './constantes'

interface Props {
  rrg: CicloRrg | null | undefined
  rendimientos: Record<string, CicloRendCelda>
  riesgo: CicloRiesgo | null | undefined
  tendencia: CicloTendencia | null | undefined
}

/**
 * Cada dimensión por separado y con su explicación: no se combinan en un puntaje único (rendimiento pasado,
 * fortaleza relativa, momentum, tendencia, riesgo son cosas distintas).
 */
export default function MetricasGrupo({ rrg, rendimientos, riesgo, tendencia }: Props) {
  const a = rrg?.actual ?? null
  const r1a = rendimientos['1A']
  const dd = riesgo?.drawdown
  const vol = riesgo?.volatilidad
  return (
    <div className="grid grid-cols-2 gap-2">
      <MetricTile
        label="Fortaleza relativa"
        infoTerm="ciclos_rs_ratio"
        value={a ? fmtNum(a.rs_ratio, 1) : '—'}
        sub={a ? (a.rs_ratio >= 100 ? 'Por encima de 100' : 'Por debajo de 100') : undefined}
        insuficiente={!a}
      />
      <MetricTile
        label="Momentum relativo"
        infoTerm="ciclos_rs_momentum"
        value={a ? fmtNum(a.rs_momentum, 1) : '—'}
        sub={a ? (a.rs_momentum >= 100 ? 'Mejorando' : 'Empeorando') : undefined}
        insuficiente={!a}
      />
      <MetricTile
        label="Rendimiento 1 año"
        value={fmtPct(r1a?.absoluto)}
        tone={tonoDe(r1a?.absoluto)}
        sub={r1a?.motivo ?? undefined}
        insuficiente={r1a?.absoluto == null}
      />
      <MetricTile
        label="Relativo a la referencia (1A)"
        infoTerm="ciclos_rendimiento_relativo"
        value={fmtPct(r1a?.relativo)}
        tone={tonoDe(r1a?.relativo)}
        insuficiente={r1a?.relativo == null}
      />
      <MetricTile
        label="Volatilidad anual"
        infoTerm="ciclos_volatilidad"
        value={fmtPct(vol?.anualizada, 1, false)}
        sub={vol?.n_obs ? `${vol.n_obs} semanas` : undefined}
        insuficiente={vol?.anualizada == null}
      />
      <MetricTile
        label="Máxima caída"
        infoTerm="ciclos_drawdown"
        value={fmtPct(dd?.maximo, 1, false)}
        tone={dd?.maximo ? 'neg' : undefined}
        sub={
          dd?.maximo == null
            ? undefined
            : dd.maximo === 0
            ? 'Sin caídas en el período'
            : dd.recuperacion_semanas != null
            ? `Recuperada en ${dd.recuperacion_semanas} sem. · mínimo ${dd.fecha_valle ? fechaCorta(dd.fecha_valle) : '—'}`
            : `Sin recuperar · mínimo ${dd.fecha_valle ? fechaCorta(dd.fecha_valle) : '—'}`
        }
        insuficiente={dd?.maximo == null}
      />
      <MetricTile
        label="Distancia a su media de 40 sem."
        infoTerm="ciclos_tendencia"
        value={fmtPct(tendencia?.distancia)}
        tone={tonoDe(tendencia?.distancia)}
        insuficiente={tendencia?.distancia == null}
      />
      <MetricTile
        label="Pendiente de esa media"
        infoTerm="ciclos_tendencia"
        value={fmtPct(tendencia?.pendiente, 2)}
        tone={tonoDe(tendencia?.pendiente)}
        sub="en las últimas 4 semanas"
        insuficiente={tendencia?.pendiente == null}
      />
    </div>
  )
}
