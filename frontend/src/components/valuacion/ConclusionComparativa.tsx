import { useState } from 'react'
import type { Comparador, FraseConclusion, RankingDimension } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../icons/Icons'
import { EstadoDimension, OrigenTag, TONO_FRASE } from './comun'

const TEXTO_FIRMEZA = { alta: 'firme', media: 'orientativa', baja: 'poco firme' } as const
const COLOR_FIRMEZA = { alta: 'text-app-pos', media: 'text-app-warn', baja: 'text-app-neg' } as const

function Frases({ frases }: { frases: FraseConclusion[] }) {
  return (
    <div className="flex flex-col gap-2">
      {frases.map((f, i) => (
        <div key={i} className={`border-l-2 pl-2.5 ${TONO_FRASE[f.tono]}`}>
          <div className="text-caption text-app-text flex flex-wrap items-center gap-1.5">
            <span>{f.texto}</span>
            {f.origen !== 'observado' && <OrigenTag origen={f.origen} />}
          </div>
          <div className="text-label text-app-text-faint">Regla: {f.regla}</div>
        </div>
      ))}
    </div>
  )
}

function Subtitulo({ children }: { children: React.ReactNode }) {
  return <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">{children}</div>
}

function FilaRanking({ r, objetivo }: { r: RankingDimension; objetivo: string }) {
  const [abierta, setAbierta] = useState(false)
  const orden = r.puestos.filter(p => p.posicion != null)
  return (
    <div className="border-b border-app-border last:border-b-0 py-2.5">
      <button onClick={() => setAbierta(a => !a)} className="w-full flex items-center justify-between gap-2 text-left" aria-expanded={abierta}>
        <div className="min-w-0">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-dim">{r.nombre}</div>
          <div className="flex flex-wrap items-center gap-x-2">
            <EstadoDimension nivel={r.nivel_objetivo} estado={r.estado_objetivo} />
            <span className="text-caption text-app-text">
              {r.posicion_objetivo != null && r.tercio ? `puesto ${r.posicion_objetivo} de ${r.de}` : 'sin ranking'}
            </span>
          </div>
        </div>
        <Icon name="chevron" className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`} />
      </button>
      {abierta && (
        <div className="mt-2 flex flex-col gap-2">
          <div className="text-caption text-app-text-dim">
            {orden.length > 0
              ? orden.map(p => (
                <span key={p.ticker_base} className="mr-2 whitespace-nowrap">
                  {p.posicion}.º <span className={`font-mono ${p.ticker_base === objetivo ? 'font-bold text-app-accent' : ''}`}>{p.ticker_base}</span>
                </span>
              ))
              : 'Ninguno tiene dato suficiente en esta dimensión.'}
          </div>
          <div className="bg-app-surface-2 rounded-xl p-2.5 text-caption text-app-text-dim">{r.regla}</div>
        </div>
      )}
    </div>
  )
}

function Detalle({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  const [abierta, setAbierta] = useState(false)
  return (
    <div className="border-b border-app-border last:border-b-0 py-2.5">
      <button onClick={() => setAbierta(a => !a)} className="w-full flex items-center justify-between gap-2 text-left" aria-expanded={abierta}>
        <span className="text-caption font-bold text-app-text">{titulo}</span>
        <Icon name="chevron" className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`} />
      </button>
      {abierta && <div className="mt-2">{children}</div>}
    </div>
  )
}

/** Posición en el grupo, ventajas y desventajas contra cada alternativa y la conclusión con su regla. */
export default function ConclusionComparativa({ c }: { c: Comparador }) {
  const con = c.conclusion
  if (!con) return null
  const firmeza = con.firmeza
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="text-strong font-bold text-app-text">{con.titulo}</div>
          <InfoTooltip term="comparador_conclusion" label="" />
        </div>
        <div className="text-label text-app-text-faint mb-2">
          Lectura <span className={`font-semibold ${COLOR_FIRMEZA[firmeza]}`}>{TEXTO_FIRMEZA[firmeza]}</span> · {con.regla_aplicada}
        </div>
        <Frases frases={con.frases} />
        {con.destacadas.length > 0 && (
          <div className="mt-3">
            <Subtitulo>Frente a cada alternativa</Subtitulo>
            <Frases frases={con.destacadas} />
          </div>
        )}
      </div>

      {(con.mayor.length > 0 || con.menor.length > 0) && (
        <div>
          <Subtitulo>¿Por qué podría merecer un múltiplo mayor o menor?</Subtitulo>
          {con.mayor.length > 0 && (
            <div className="mb-2">
              <div className="text-caption font-semibold text-app-pos mb-1">Mayor, porque…</div>
              <Frases frases={con.mayor} />
            </div>
          )}
          {con.menor.length > 0 && (
            <div className="mb-2">
              <div className="text-caption font-semibold text-app-warn mb-1">Menor, porque…</div>
              <Frases frases={con.menor} />
            </div>
          )}
          <p className="text-label text-app-text-faint">{con.salvedad}</p>
        </div>
      )}

      <div>
        <Subtitulo>Dónde queda dentro de este grupo <InfoTooltip term="comparador_ranking" label="" /></Subtitulo>
        {c.ranking.map(r => <FilaRanking key={r.clave} r={r} objetivo={c.ticker_base} />)}
      </div>

      {c.pares.length > 0 && (
        <div>
          <Subtitulo>Ventajas y desventajas contra cada una</Subtitulo>
          {c.pares.map(p => (
            <Detalle key={p.ticker_base} titulo={`${c.ticker_base} vs. ${p.ticker_base}${p.orientativa ? ' (orientativa)' : ''}`}>
              <div className="flex flex-col gap-2">
                {p.lineas.map((l, i) => (
                  <div key={i} className={`border-l-2 pl-2.5 ${TONO_FRASE[l.tono]}`}>
                    <div className="text-caption text-app-text">{l.texto}</div>
                    <div className="text-label text-app-text-faint">Regla: {l.regla}</div>
                  </div>
                ))}
                {p.lineas.length === 0 && <p className="text-caption text-app-text-dim">No hay métricas con dato en las dos para comparar.</p>}
                {p.orientativa && <p className="text-label text-app-text-faint">Comparabilidad baja: se muestra como referencia, no entra a la conclusión.</p>}
              </div>
            </Detalle>
          ))}
        </div>
      )}

      <div>
        <Subtitulo>¿Cómo se decide?</Subtitulo>
        <div className="bg-app-surface-2 rounded-xl p-2.5 text-caption text-app-text-dim">{con.regla}</div>
        {con.firmeza_razones.length > 0 && (
          <ul className="flex flex-col gap-0.5 mt-2">
            {con.firmeza_razones.map(r => (
              <li key={r} className="text-caption text-app-text-dim flex gap-1.5"><span aria-hidden="true">·</span><span>{r}</span></li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <Subtitulo>Qué no cubre</Subtitulo>
        <ul className="flex flex-col gap-0.5">
          {con.limites.map(l => (
            <li key={l} className="text-caption text-app-text-dim flex gap-1.5"><span aria-hidden="true">·</span><span>{l}</span></li>
          ))}
        </ul>
      </div>
    </div>
  )
}
