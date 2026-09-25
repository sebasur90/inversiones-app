import { useState } from 'react'
import dayjs from 'dayjs'
import {
  type AporteComparacion,
  type AporteHito,
  type AporteMensaje,
  type AporteProximoHito,
  type RitmoAportesOut,
} from '../../api'
import { formatUSD } from '../../utils'
import Card from '../ui/Card'
import Chip from '../ui/Chip'
import MetricTile from '../ui/MetricTile'
import Segmented from '../ui/Segmented'
import Semaforo from '../ui/Semaforo'
import BarraProgreso from '../ui/BarraProgreso'
import BotonExportarCsv from '../ui/BotonExportarCsv'
import InfoTooltip from '../../help/components/InfoTooltip'
import AportesMensualesChart from '../charts/AportesMensualesChart'
import AportesHeatmap from '../charts/AportesHeatmap'
import { claseTono, mesCorto, pct } from './comun'

type Ventana = '12' | '24' | '36' | 'all'

const VENTANAS: { value: Ventana; label: string }[] = [
  { value: '12', label: '12 m' },
  { value: '24', label: '24 m' },
  { value: '36', label: '36 m' },
  { value: 'all', label: 'Todo' },
]

const BORDE_TONO: Record<AporteMensaje['tono'], string> = {
  positivo: 'border-l-app-pos',
  neutro: 'border-l-app-accent',
  negativo: 'border-l-app-neg',
}

const ICONO_TONO: Record<AporteMensaje['tono'], string> = {
  positivo: '🔥',
  neutro: '📌',
  negativo: '⚠️',
}

/** Barras horizontales comparando este mes (real + tramo proyectado) contra las referencias. */
function BarrasComparativas({
  neto,
  proyeccion,
  referencias,
}: {
  neto: number
  proyeccion: number
  referencias: { etiqueta: string; cmp: AporteComparacion | null }[]
}) {
  const validas = referencias.filter(r => r.cmp != null) as { etiqueta: string; cmp: AporteComparacion }[]
  const maxAbs = Math.max(Math.abs(neto), Math.abs(proyeccion), ...validas.map(r => Math.abs(r.cmp.referencia_usd)), 1)
  const ancho = (v: number) => `${(Math.abs(v) / maxAbs) * 100}%`
  const filas = [
    { etiqueta: 'Este mes', valor: neto, proy: proyeccion, delta: null as number | null },
    ...validas.map(r => ({ etiqueta: r.etiqueta, valor: r.cmp.referencia_usd, proy: null as number | null, delta: r.cmp.delta_proyectado_pct })),
  ]
  return (
    <div className="flex flex-col gap-2.5">
      {filas.map(f => (
        <div key={f.etiqueta}>
          <div className="flex justify-between items-baseline text-caption mb-1.5">
            <span className="text-app-text">{f.etiqueta}</span>
            <span className="font-mono font-bold text-app-text tabular-nums">
              {formatUSD(f.valor)}
              {f.delta != null && (
                <span className={`ml-2 text-label font-semibold ${claseTono(f.delta)}`}>{pct(f.delta)} al ritmo actual</span>
              )}
            </span>
          </div>
          <div className="relative h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
            {f.proy != null && (
              <div
                className={`absolute inset-y-0 left-0 rounded-full ${f.proy < 0 ? 'bg-app-neg/30' : 'bg-app-pos/30'}`}
                style={{ width: ancho(f.proy) }}
              />
            )}
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${f.valor < 0 ? 'bg-app-neg' : f.proy != null ? 'bg-app-pos' : 'bg-app-text-faint'}`}
              style={{ width: ancho(f.valor) }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function MensajeCard({ mensaje }: { mensaje: AporteMensaje }) {
  return (
    <Card className={`mb-2 py-3 border-l-[3px] ${BORDE_TONO[mensaje.tono]}`}>
      <div className="text-body font-bold text-app-text">
        <span className="mr-1.5" aria-hidden="true">{ICONO_TONO[mensaje.tono]}</span>
        {mensaje.titulo}
      </div>
      <div className="text-caption text-app-text-dim mt-0.5">{mensaje.detalle}</div>
    </Card>
  )
}

function ProximoHito({ hito }: { hito: AporteProximoHito }) {
  const falta = hito.unidad === 'usd' ? formatUSD(hito.falta) : `${hito.falta} ${hito.falta === 1 ? 'mes' : 'meses'}`
  return (
    <div className="mb-2">
      <div className="flex justify-between items-baseline text-caption mb-1">
        <span className="text-app-text">{hito.titulo}</span>
        <span className="text-app-text-dim">Faltan {falta}</span>
      </div>
      <BarraProgreso pct={hito.progreso_pct} />
    </div>
  )
}

function ListaHitos({ hitos }: { hitos: AporteHito[] }) {
  return (
    <ul className="flex flex-col gap-1.5 mt-2">
      {hitos.map(h => (
        <li key={h.clave} className="text-caption">
          <span className="font-semibold text-app-text">{h.titulo}</span>
          <span className="text-app-text-faint"> · {mesCorto(h.fecha)}</span>
          <div className="text-app-text-dim">{h.descripcion}</div>
        </li>
      ))}
    </ul>
  )
}

/** Pestaña "Análisis": el detalle estadístico del ritmo de aportes contra el propio historial.
 *  Es el contenido histórico de la pantalla, intacto. */
export default function AportesAnalisis({ datos, cartera }: { datos: RitmoAportesOut; cartera: string | null }) {
  const [ventana, setVentana] = useState<Ventana>('12')
  const [verTodosLosLogros, setVerTodosLosLogros] = useState(false)

  const em = datos.este_mes!
  const anio = datos.anio_en_curso!
  const rachas = datos.rachas!
  const est = datos.estadisticas!
  const estado = datos.estado_ritmo!

  // La referencia de promedio cae a 6m / 3m / histórico cuando no hay 12 meses cerrados.
  const promedioRef: { etiqueta: string; cmp: AporteComparacion | null } =
    em.vs_promedio_12 ? { etiqueta: 'Promedio 12 meses', cmp: em.vs_promedio_12 }
    : em.vs_promedio_6 ? { etiqueta: 'Promedio 6 meses', cmp: em.vs_promedio_6 }
    : em.vs_promedio_3 ? { etiqueta: 'Promedio 3 meses', cmp: em.vs_promedio_3 }
    : { etiqueta: 'Promedio', cmp: null }

  const serieVisible = ventana === 'all' ? datos.serie_mensual : datos.serie_mensual.slice(-Number(ventana))
  const hitosRecientes = datos.hitos_alcanzados.filter(h => h.reciente)
  const maxProyeccion = Math.max(...anio.proyecciones.map(p => Math.abs(p.total_fin_anio_usd ?? 0)), 1)
  const anioAnterior = anio.anio - 1

  return (
    <>
      {/* 1. Este mes */}
      <Card className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">
            <InfoTooltip term="aportes_mes_en_curso" label={`Este mes · ${mesCorto(em.mes)}`} />
          </div>
          <div className="flex items-center gap-1">
            <Semaforo nivel={estado.nivel} etiqueta={estado.etiqueta} />
            <InfoTooltip term="aportes_estado_ritmo" label="" />
          </div>
        </div>
        <div className={`font-mono text-metric-lg font-bold tabular-nums ${em.neto_usd < 0 ? 'text-app-neg' : 'text-app-text'}`}>
          {formatUSD(em.neto_usd)}
          {em.neto_usd < 0 && <span className="text-label font-semibold text-app-neg ml-2">retiro neto</span>}
          {em.es_record_parcial && <span className="text-label font-semibold text-app-pos ml-2">🏆 récord</span>}
        </div>
        <div className="text-caption text-app-text-dim mt-1">
          Día {em.dia} de {em.dias_mes} · al ritmo actual: <span className="font-mono font-semibold text-app-text">{formatUSD(em.proyeccion_usd)}</span>
          {!em.proyeccion_fiable && <span className="text-app-text-faint"> (estimación temprana)</span>}
          <InfoTooltip term="aportes_proyeccion_mes" label="" />
        </div>
        <div className="text-label text-app-text-faint mb-3">
          Compras {formatUSD(em.compras_usd)} · Salidas {formatUSD(em.salidas_usd)}
        </div>
        <div className="text-caption text-app-text-dim mb-3">{estado.detalle}</div>
        <BarrasComparativas
          neto={em.neto_usd}
          proyeccion={em.proyeccion_usd}
          referencias={[{ etiqueta: 'Mes anterior', cmp: em.vs_mes_anterior }, promedioRef]}
        />
        <div className="text-label text-app-text-dim mt-3 flex items-center gap-1">
          Mismo mes de {anioAnterior}:{' '}
          {em.vs_mismo_mes_anio_anterior ? (
            <>
              <span className="font-mono text-app-text">{formatUSD(em.vs_mismo_mes_anio_anterior.referencia_usd)}</span>
              <span className={claseTono(em.vs_mismo_mes_anio_anterior.delta_proyectado_pct)}>
                ({pct(em.vs_mismo_mes_anio_anterior.delta_proyectado_pct)} al ritmo actual)
              </span>
            </>
          ) : (
            '—'
          )}
          <InfoTooltip term="aportes_mismo_periodo" label="" />
        </div>
      </Card>

      {/* 2. Mensajes y logros */}
      {datos.mensajes.length > 0 && (
        <div className="mb-4">
          {datos.mensajes.map(m => (
            <MensajeCard key={m.clave} mensaje={m} />
          ))}
        </div>
      )}

      <Card className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-body font-bold text-app-text">
            <InfoTooltip term="aportes_hitos" label="Hitos" />
          </h3>
          <button
            onClick={() => setVerTodosLosLogros(v => !v)}
            className="text-label font-semibold text-app-accent"
          >
            {verTodosLosLogros ? 'Ocultar' : `Ver todos (${datos.hitos_alcanzados.length})`}
          </button>
        </div>
        {hitosRecientes.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {hitosRecientes.map(h => (
              <Chip key={h.clave}>Nuevo: {h.titulo}</Chip>
            ))}
          </div>
        )}
        {datos.proximos_hitos.map(h => (
          <ProximoHito key={h.clave} hito={h} />
        ))}
        {verTodosLosLogros && <ListaHitos hitos={datos.hitos_alcanzados} />}
      </Card>

      {/* 3. Métricas */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        <MetricTile
          label="Racha actual"
          value={`${rachas.aportando_actual.meses} ${rachas.aportando_actual.meses === 1 ? 'mes' : 'meses'}`}
          infoTerm="aportes_racha"
          tone={rachas.aportando_actual.meses > 0 ? 'pos' : undefined}
          sub={
            rachas.aportando_record.meses > 0
              ? `Récord: ${rachas.aportando_record.meses} (${mesCorto(rachas.aportando_record.desde)} → ${mesCorto(rachas.aportando_record.hasta)})`
              : 'Todavía sin racha'
          }
        />
        <MetricTile
          label="Mejor mes"
          value={formatUSD(est.mejor_mes?.neto_usd)}
          insuficiente={est.mejor_mes == null}
          sub={est.mejor_mes ? mesCorto(est.mejor_mes.mes) : undefined}
        />
        <MetricTile
          label="Promedio 12 m"
          value={formatUSD(est.promedio_12_usd)}
          infoTerm="aportes_promedio"
          insuficiente={est.promedio_12_usd == null}
          sub={est.promedio_3_usd != null ? `3 m: ${formatUSD(est.promedio_3_usd)}` : undefined}
        />
        <MetricTile
          label="Constancia"
          value={est.desvio_usd != null ? `± ${formatUSD(est.desvio_usd)}` : '—'}
          infoTerm="aportes_constancia"
          insuficiente={est.constancia == null}
          nivel={est.constancia}
        />
        <MetricTile
          label="Total aportado"
          value={formatUSD(est.total_neto_usd)}
          infoTerm="aportes_neto_criterio"
          sub={`Compras ${formatUSD(est.total_compras_usd)} · Salidas ${formatUSD(est.total_salidas_usd)}`}
        />
        <MetricTile
          label="Meses sin aportar"
          value={`${rachas.meses_sin_aportar_ultimos_12}`}
          tone={rachas.meses_sin_aportar_ultimos_12 > 0 ? 'neg' : 'pos'}
          sub={`de los últimos ${rachas.meses_considerados_ultimos_12} cerrados`}
        />
      </div>

      {/* 4. Gráfico mensual */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <h3 className="text-body font-bold text-app-text">
          <InfoTooltip term="aportes_promedio_movil" label="Mes a mes" />
        </h3>
        <Segmented options={VENTANAS} value={ventana} onChange={setVentana} />
      </div>
      <Card className="mb-4">
        <AportesMensualesChart serie={serieVisible} promedio12={est.promedio_12_usd} />
      </Card>

      {/* 5. Proyección a fin de año */}
      <Card className="mb-4">
        <h3 className="text-body font-bold text-app-text mb-1">
          <InfoTooltip term="aportes_proyeccion_fin_anio" label={`Cómo termina ${anio.anio}`} />
        </h3>
        <div className="text-caption text-app-text-dim mb-3">
          Llevás <span className="font-mono font-semibold text-app-text">{formatUSD(anio.ytd_usd)}</span> en{' '}
          {anio.meses_cerrados} {anio.meses_cerrados === 1 ? 'mes cerrado' : 'meses cerrados'} + el actual
          {anio.vs_mismo_periodo_anio_anterior && (
            <>
              {' '}· vs. {anioAnterior} a esta altura:{' '}
              <span className={claseTono(anio.vs_mismo_periodo_anio_anterior.delta_pct)}>{pct(anio.vs_mismo_periodo_anio_anterior.delta_pct)}</span>
            </>
          )}
        </div>
        <div className="flex flex-col gap-2.5">
          {anio.proyecciones.map(p => (
            <div key={p.clave}>
              <div className="flex justify-between items-baseline text-caption mb-1.5">
                <span className="text-app-text">
                  {p.etiqueta}
                  {p.ritmo_mensual_usd != null && <span className="text-app-text-faint"> · {formatUSD(p.ritmo_mensual_usd)}/mes</span>}
                </span>
                <span className="font-mono font-bold text-app-text tabular-nums">
                  {p.total_fin_anio_usd != null ? formatUSD(p.total_fin_anio_usd) : <span className="text-app-text-faint font-normal">insuficiente</span>}
                </span>
              </div>
              <BarraProgreso
                pct={(Math.abs(p.total_fin_anio_usd ?? 0) / maxProyeccion) * 100}
                tono={(p.total_fin_anio_usd ?? 0) < 0 ? 'neg' : 'accent'}
              />
            </div>
          ))}
        </div>
        <div className="text-label text-app-text-dim mt-3">
          {anio.anio_anterior_total_usd != null && <>{anioAnterior}: {formatUSD(anio.anio_anterior_total_usd)}</>}
          {anio.anio_anterior_total_usd != null && datos.mejor_anio && ' · '}
          {datos.mejor_anio && <>Tu mejor año: {datos.mejor_anio.anio} ({formatUSD(datos.mejor_anio.total_usd)})</>}
        </div>
      </Card>

      {/* 6. Calendario */}
      <h3 className="text-body font-bold text-app-text mb-2">Calendario de aportes</h3>
      <AportesHeatmap meses={datos.serie_mensual} anios={datos.por_anio} />

      {/* 7. Tabla por año */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <h3 className="text-body font-bold text-app-text">Por año</h3>
        <BotonExportarCsv
          nombre={`aportes-${cartera || 'consolidado'}`}
          encabezados={['Mes', 'Neto USD', 'Compras USD', 'Salidas USD', 'En curso']}
          filas={() => datos.serie_mensual.filter(s => !s.futuro).map(s => [s.mes, s.neto_usd, s.compras_usd, s.salidas_usd, s.en_curso])}
        />
      </div>
      <Card className="mb-4 overflow-x-auto">
        <table className="w-full text-label border-separate border-spacing-0">
          <thead>
            <tr className="text-app-text-faint font-bold uppercase text-label">
              <th className="text-left pb-2 pr-2">Año</th>
              <th className="text-right pb-2 px-1">Total</th>
              <th className="text-right pb-2 px-1">Prom/mes</th>
              <th className="text-right pb-2 px-1">Meses c/aporte</th>
              <th className="text-right pb-2 px-1">Var. anual</th>
              <th className="text-right pb-2 pl-1">Mejor mes</th>
            </tr>
          </thead>
          <tbody>
            {datos.por_anio.map(a => (
              <tr key={a.anio} className="border-t border-app-border">
                <td className="font-semibold text-app-text py-1.5 pr-2">
                  {a.anio}
                  {a.en_curso ? '*' : ''}
                </td>
                <td className={`text-right font-mono font-bold tabular-nums py-1.5 px-1 ${a.total_usd < 0 ? 'text-app-neg' : 'text-app-text'}`}>{formatUSD(a.total_usd)}</td>
                <td className="text-right font-mono tabular-nums text-app-text py-1.5 px-1">{formatUSD(a.promedio_mensual_usd)}</td>
                <td className="text-right font-mono tabular-nums text-app-text py-1.5 px-1">
                  {a.meses_con_aporte}/{a.meses_en_rango}
                </td>
                <td className={`text-right font-mono tabular-nums py-1.5 px-1 ${claseTono(a.var_vs_anio_anterior_pct)}`}>{pct(a.var_vs_anio_anterior_pct)}</td>
                <td className="text-right font-mono tabular-nums text-app-text py-1.5 pl-1">
                  {a.mejor_mes ? `${formatUSD(a.mejor_mes.neto_usd)} (${dayjs(`${a.mejor_mes.mes}-01`).format('MMM')})` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {datos.por_anio.some(a => a.en_curso) && <div className="text-label text-app-text-faint mt-2">* año en curso (total con el mes actual, promedio sólo de meses cerrados)</div>}
      </Card>
    </>
  )
}
