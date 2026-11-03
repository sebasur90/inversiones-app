import { useState } from 'react'
import type { CicloEjeRegimen, CicloRegimen, CicloSerieMacro, CicloVoto } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import { Icon } from '../icons/Icons'
import { fmtNum } from './constantes'

const ETIQ_EJE: Record<string, string> = { acelerando: 'Acelera', desacelerando: 'Desacelera', no_concluyente: 'Sin conclusión' }
const ETIQ_VOTO: Record<string, string> = { acelerando: 'Acelera', desacelerando: 'Desacelera', sin_cambio: 'Sin cambio' }
const ETIQ_CONTEXTO: Record<string, string> = { liquidez: 'Liquidez', condiciones_financieras: 'Condiciones financieras', dolar: 'Dólar' }

function esPorcentaje(unidad: string): boolean {
  return unidad.startsWith('%')
}

function fmtValor(s: CicloSerieMacro, v: number | null): string {
  if (v == null) return '—'
  return esPorcentaje(s.unidad) ? `${fmtNum(v, 2)}%` : fmtNum(v, 2)
}

/** Cambio entre hoy y hace unos meses: en puntos porcentuales si la serie es un porcentaje, en unidades si es un índice. */
function fmtCambio(s: CicloSerieMacro): string {
  if (s.cambio == null) return '—'
  const t = `${s.cambio > 0 ? '+' : ''}${fmtNum(s.cambio, 2)}`
  return esPorcentaje(s.unidad) ? `${t} pp` : t
}

function EtiquetaVoto({ voto }: { voto: CicloVoto }) {
  if (!voto) return <span className="text-label text-app-text-faint">No vota</span>
  const color = voto === 'acelerando' ? 'text-app-accent' : voto === 'desacelerando' ? 'text-app-warn' : 'text-app-text-dim'
  return <span className={`text-label font-bold ${color}`}>{ETIQ_VOTO[voto]}</span>
}

function FilaSerie({ s, meses }: { s: CicloSerieMacro; meses: number }) {
  return (
    <li className="rounded-lg border border-app-border px-2.5 py-2" title={s.descripcion}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-caption font-semibold text-app-text">{s.nombre}</span>
        {s.clasifica ? <EtiquetaVoto voto={s.voto} /> : null}
      </div>
      {s.estado === 'ok' ? (
        <>
          <div className="grid grid-cols-3 gap-2 mt-1">
            <div>
              <div className="text-label text-app-text-faint">Hoy</div>
              <div className="font-mono tabular-nums text-caption font-bold text-app-text">{fmtValor(s, s.valor)}</div>
            </div>
            <div>
              <div className="text-label text-app-text-faint">Hace {meses} meses</div>
              <div className="font-mono tabular-nums text-caption text-app-text-dim">{fmtValor(s, s.valor_previo)}</div>
            </div>
            <div>
              <div className="text-label text-app-text-faint">Cambio</div>
              <div className="font-mono tabular-nums text-caption font-bold text-app-text">{fmtCambio(s)}</div>
            </div>
          </div>
          <p className="text-label text-app-text-faint mt-1">
            Dato de {s.fecha ? fechaCorta(s.fecha) : '—'}
            {s.sentido === -1 ? ' · si sube, indica menos crecimiento' : ''}
            {s.nota ? ` · ${s.nota}` : ''}
          </p>
        </>
      ) : (
        <p className="text-label text-app-text-dim mt-1">No se usa: {s.motivo ?? 'sin datos'}.</p>
      )}
    </li>
  )
}

function Eje({ eje, meses }: { eje: CicloEjeRegimen; meses: number }) {
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
        <div className="text-label font-bold uppercase text-app-text-faint">{eje.nombre}</div>
        <span className="text-label font-bold text-app-text">
          {ETIQ_EJE[eje.estado]} · {eje.acelerando} aceleran, {eje.desacelerando} desaceleran
        </span>
      </div>
      {eje.motivo && <p className="text-label text-app-text-dim mb-1.5">{eje.motivo}.</p>}
      <ul className="flex flex-col gap-1.5">
        {eje.series.map(s => (
          <FilaSerie key={s.id} s={s} meses={meses} />
        ))}
      </ul>
    </div>
  )
}

/**
 * Régimen macroeconómico de EE.UU. (FRED): crecimiento e inflación, cada uno acelerando o desacelerando por mayoría de sus
 * series. Se muestra cada voto con su tamaño, el contexto aparte (no clasifica) y, si un eje no concluye, no hay escenario.
 */
export default function RegimenMacro({ regimen }: { regimen: CicloRegimen }) {
  const [abierto, setAbierto] = useState(false)
  const resumen =
    regimen.estado === 'disponible'
      ? `${regimen.escenario} · crecimiento ${ETIQ_EJE[regimen.ejes.crecimiento.estado].toLowerCase()}, inflación ${ETIQ_EJE[regimen.ejes.inflacion.estado].toLowerCase()}`
      : regimen.estado === 'no_concluyente'
        ? 'Sin conclusión: no se asigna ningún escenario'
        : 'No disponible: todavía no se descargaron las series macro'
  return (
    <div className="rounded-xl border border-app-border bg-app-surface">
      <button
        type="button"
        onClick={() => setAbierto(a => !a)}
        aria-expanded={abierto}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="flex flex-col">
          <span className="text-caption font-bold text-app-text">
            Régimen macroeconómico (EE.UU.) <InfoTooltip term="ciclos_regimen" />
          </span>
          <span className="text-label text-app-text-dim">{resumen}</span>
        </span>
        <Icon name="chevron" className={`w-4 h-4 text-app-text-faint transition-transform ${abierto ? 'rotate-180' : ''}`} />
      </button>
      {abierto && (
        <div className="px-3 pb-3 pt-1 border-t border-app-border flex flex-col gap-3">
          <p className="text-label text-app-text-dim">{regimen.aclaracion}</p>
          <div>
            <div className="text-label font-bold uppercase text-app-text-faint mb-1">Los cuatro escenarios</div>
            <div className="grid grid-cols-2 gap-1.5">
              {regimen.escenarios.map(e => (
                <div key={e.id} className={`rounded-lg border px-2 py-1.5 ${e.actual ? 'border-app-accent bg-app-accent-soft' : 'border-app-border'}`}>
                  <div className="text-caption font-semibold text-app-text">
                    {e.nombre}
                    {e.actual ? ' · actual' : ''}
                  </div>
                  <div className="text-label text-app-text-faint">
                    Crecimiento: {ETIQ_EJE[e.crecimiento]?.toLowerCase() ?? e.crecimiento}
                    <br />
                    Inflación: {ETIQ_EJE[e.inflacion]?.toLowerCase() ?? e.inflacion}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {regimen.estado !== 'no_disponible' && (
            <>
              <Eje eje={regimen.ejes.crecimiento} meses={regimen.meses_comparacion} />
              <Eje eje={regimen.ejes.inflacion} meses={regimen.meses_comparacion} />
              <p className="text-label text-app-text-faint">
                Cada serie compara su valor de hoy con el de hace {regimen.meses_comparacion} meses. Hace falta una mayoría estricta y al menos {regimen.minimo_votos} votos por eje.
                {regimen.dato_mas_viejo && regimen.dato_mas_reciente
                  ? ` Datos de ${fechaCorta(regimen.dato_mas_viejo)} a ${fechaCorta(regimen.dato_mas_reciente)}.`
                  : ''}
              </p>

              <div>
                <div className="text-label font-bold uppercase text-app-text-faint mb-1.5">Contexto (no clasifica)</div>
                <div className="flex flex-col gap-2">
                  {Object.entries(regimen.contexto).map(([clave, lista]) => (
                    <div key={clave}>
                      <div className="text-label font-semibold text-app-text-dim mb-1">{ETIQ_CONTEXTO[clave] ?? clave}</div>
                      <ul className="flex flex-col gap-1.5">
                        {lista.map(s => (
                          <FilaSerie key={s.id} s={s} meses={regimen.meses_comparacion} />
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {regimen.falta.length > 0 && (
            <div>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1">Qué no se pudo usar</div>
              <ul className="list-disc pl-4 text-label text-app-text-dim space-y-0.5">
                {regimen.falta.map(f => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-label text-app-text-faint">
            <div className="font-semibold text-app-text-dim mb-0.5">Fuente: {regimen.fuente}</div>
            <ul className="list-disc pl-4 space-y-0.5">
              {regimen.limitaciones.map(l => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
