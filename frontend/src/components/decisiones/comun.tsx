import { useState, type ReactNode } from 'react'
import type {
  BanderaDecision, ConclusionDecision, DimensionEval, EvaluacionDecision, FuenteDecision, ObservacionSimulacion,
} from '../../api'
import Card from '../ui/Card'
import Semaforo from '../ui/Semaforo'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content'

export const AYUDA_DIMENSION: Record<string, HelpKey> = {
  fundamentales: 'decisiones_fundamentales',
  valoracion: 'decisiones_valoracion',
  riesgo: 'decisiones_riesgo',
  tecnico: 'decisiones_tecnico',
  encaje: 'decisiones_encaje',
}

/** Porcentaje desde una fracción (0,12 → "12,0 %"). Datos de mercado: no pasan por privacidad. */
export function pct(v: number | null | undefined, dec = 1, signo = false): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const n = v * 100
  const s = n.toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
  return `${signo && n > 0 ? '+' : ''}${s} %`
}

export function num(v: number | null | undefined, dec = 0): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

export function precio(v: number | null | undefined, moneda?: string | null): string {
  if (v == null) return '—'
  return `${v.toLocaleString('es-AR', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}${moneda ? ` ${moneda}` : ''}`
}

function tonoPuntaje(p: number | null): string {
  if (p == null) return 'bg-app-surface-2'
  if (p >= 60) return 'bg-app-pos'
  if (p >= 40) return 'bg-app-accent'
  return 'bg-app-neg'
}

/** El puntaje de una dimensión como barra + número. Sin dato: lo dice en palabras, nunca 0. */
export function BarraDimension({ d, compacta = false }: { d: Pick<DimensionEval, 'clave' | 'nombre' | 'puntaje' | 'estado'>; compacta?: boolean }) {
  const texto = d.estado === 'no_aplica' ? 'No aplica' : d.puntaje == null ? 'Sin datos' : num(d.puntaje)
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className={`text-caption text-app-text ${compacta ? 'w-24' : 'w-32'} shrink-0 truncate flex items-center gap-1`}>
        {d.nombre}
        {!compacta && AYUDA_DIMENSION[d.clave] && <InfoTooltip term={AYUDA_DIMENSION[d.clave]} label="" />}
      </span>
      <div className="flex-1 h-2 rounded-full bg-app-surface-2 overflow-hidden" aria-hidden="true">
        {d.puntaje != null && <div className={`h-full rounded-full ${tonoPuntaje(d.puntaje)}`} style={{ width: `${d.puntaje}%` }} />}
      </div>
      <span className={`text-caption font-mono tabular-nums w-16 text-right ${d.puntaje == null ? 'text-app-text-faint' : 'text-app-text'}`}>{texto}</span>
    </div>
  )
}

/** Puntaje de orden: siempre junto a las dimensiones y las banderas, nunca solo. */
export function Orden({ evaluacion }: { evaluacion: EvaluacionDecision }) {
  const o = evaluacion.orden
  return (
    <div className="flex items-start gap-3">
      <div className="shrink-0 w-[72px] h-[72px] rounded-2xl bg-app-surface-2 flex flex-col items-center justify-center">
        {o.puntaje != null ? (
          <>
            <span className="text-[26px] leading-none font-bold font-mono tabular-nums text-app-text">{num(o.puntaje)}</span>
            <span className="text-label text-app-text-faint mt-1">orden</span>
          </>
        ) : (
          <span className="text-label font-bold text-app-text-dim text-center px-1">Incompleto</span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-caption font-bold text-app-text flex items-center gap-1">
          Puntaje de orden <InfoTooltip term="decisiones_orden" label="" />
        </div>
        <p className="text-label text-app-text-dim mt-0.5">
          {o.puntaje != null
            ? `Sirve para priorizar qué mirar. Las dimensiones con dato cubren el ${num(o.cobertura * 100)} % del peso.`
            : o.motivo}
        </p>
      </div>
    </div>
  )
}

export function Banderas({ banderas }: { banderas: BanderaDecision[] }) {
  if (!banderas.length) return null
  return (
    <ul className="flex flex-col gap-1.5" aria-label="Banderas críticas">
      {banderas.map(b => (
        <li key={b.clave + b.texto} className="flex items-start gap-2">
          <Semaforo className="shrink-0 mt-0.5 w-16" nivel={b.severidad === 'alta' ? 'riesgo' : 'atencion'}
                    etiqueta={b.severidad === 'alta' ? 'Crítica' : 'Atención'} />
          <span className="text-caption text-app-text">{b.texto}</span>
        </li>
      ))}
    </ul>
  )
}

export function Observaciones({ items }: { items: ObservacionSimulacion[] }) {
  if (!items.length) return <p className="text-caption text-app-text-dim">Sin observaciones de concentración.</p>
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((o, i) => (
        <li key={i} className="flex flex-col gap-0.5">
          <div className="flex items-start gap-2">
            {o.nivel === 'info'
              ? <span className="text-label font-semibold text-app-text-faint shrink-0 mt-0.5 w-16">Dato</span>
              : <Semaforo className="shrink-0 mt-0.5 w-16" nivel={o.nivel === 'revisar' ? 'riesgo' : 'atencion'} etiqueta={o.nivel === 'revisar' ? 'Revisar' : 'Atención'} />}
            <span className="text-caption text-app-text">{o.texto}</span>
          </div>
          {o.regla && <span className="text-label text-app-text-faint pl-[72px]">{o.regla}</span>}
        </li>
      ))}
    </ul>
  )
}

/** Sección que se abre y se cierra: el resumen primero, el detalle a pedido. */
export function Seccion({ titulo, termino, resumen, children, abiertaInicial = false, estado }: {
  titulo: string; termino?: HelpKey; resumen?: ReactNode; children: ReactNode; abiertaInicial?: boolean
  estado?: { estado: string; motivo: string | null }
}) {
  const [abierta, setAbierta] = useState(abiertaInicial)
  return (
    <Card>
      <button type="button" onClick={() => setAbierta(v => !v)} aria-expanded={abierta}
              className="w-full flex items-center justify-between gap-2 text-left">
        <span className="text-strong font-bold text-app-text flex items-center gap-1">
          {titulo}
          {termino && <span onClick={e => e.stopPropagation()}><InfoTooltip term={termino} label="" /></span>}
        </span>
        <span className="text-caption font-bold text-app-accent shrink-0">{abierta ? 'Cerrar' : 'Ver'}</span>
      </button>
      {estado && estado.estado !== 'ok' && (
        <p className="text-label text-app-warn mt-1">No disponible: {estado.motivo}</p>
      )}
      {!abierta && resumen && <div className="mt-1.5">{resumen}</div>}
      {abierta && <div className="mt-3 flex flex-col gap-3">{children}</div>}
    </Card>
  )
}

export function DetalleDimension({ d }: { d: DimensionEval }) {
  return (
    <div className="flex flex-col gap-1.5">
      <BarraDimension d={d} />
      <p className="text-label text-app-text-dim">{d.resumen}</p>
      {d.factores.length > 0 && (
        <ul className="flex flex-col gap-1">
          {d.factores.map((f, i) => (
            <li key={i} className="text-caption text-app-text flex gap-2">
              <span className={`font-mono tabular-nums w-10 shrink-0 text-right ${f.efecto > 0 ? 'text-app-pos' : f.efecto < 0 ? 'text-app-neg' : 'text-app-text-faint'}`}>
                {f.efecto === 0 ? '·' : `${f.efecto > 0 ? '+' : '−'}${num(Math.abs(f.efecto), 0)}`}
              </span>
              <span>{f.texto}</span>
            </li>
          ))}
        </ul>
      )}
      {d.faltantes.length > 0 && (
        <p className="text-label text-app-text-faint">Falta: {d.faltantes.join('; ')}.</p>
      )}
      <details className="text-label text-app-text-faint">
        <summary className="cursor-pointer">Regla</summary>
        <p className="mt-1">{d.regla}</p>
      </details>
    </div>
  )
}

export function Lista({ items, vacio }: { items: string[]; vacio?: string }) {
  if (!items.length) return vacio ? <p className="text-caption text-app-text-dim">{vacio}</p> : null
  return (
    <ul className="flex flex-col gap-1 list-disc pl-4 text-caption text-app-text">
      {items.map((t, i) => <li key={i}>{t}</li>)}
    </ul>
  )
}

const TONO_CONCLUSION: Record<string, string> = {
  alternativa_mas_atractiva: 'bg-app-pos-soft text-app-pos',
  interesante_pendiente: 'bg-app-accent-soft text-app-accent',
  valoracion_exigente: 'bg-app-warn/15 text-app-warn',
  riesgo_elevado: 'bg-app-neg-soft text-app-neg',
  datos_insuficientes: 'bg-app-surface-2 text-app-text-dim',
  ninguna_superior: 'bg-app-surface-2 text-app-text',
}

export function ConclusionBadge({ tipo, titulo }: { tipo: string; titulo: string }) {
  return <span className={`inline-block font-bold text-label px-2 py-1 rounded-[7px] ${TONO_CONCLUSION[tipo] ?? 'bg-app-surface-2 text-app-text'}`}>{titulo}</span>
}

const TEXTO_PASO: Record<string, string> = {
  profundizar: 'Profundizar', esperar_condicion: 'Esperar una condición', descartar_por_ahora: 'Descartar por ahora',
}

export function Conclusion({ c }: { c: ConclusionDecision }) {
  const r = c.respuestas
  return (
    <div className="flex flex-col gap-3">
      <ConclusionBadge tipo={c.tipo} titulo={c.titulo} />
      <Pregunta n={1} t="¿Qué encaja mejor con tus criterios?">{r.que_encaja ?? 'Ninguno se destaca con claridad.'}</Pregunta>
      <Pregunta n={2} t="¿Por qué?">{r.por_que}</Pregunta>
      <Pregunta n={3} t="Evidencia a favor"><Lista items={r.evidencia} vacio="Sin factores a favor con los datos disponibles." /></Pregunta>
      <Pregunta n={4} t="Desventajas y evidencia en contra"><Lista items={c.evidencia_en_contra} /></Pregunta>
      <Pregunta n={5} t="¿Qué tendría que pasar para que deje de valer?"><Lista items={r.invalidaria} /></Pregunta>
      <Pregunta n={6} t="¿Profundizar, esperar o descartar?">
        <span className="font-semibold">{TEXTO_PASO[r.siguiente_paso] ?? r.siguiente_paso}.</span> {r.siguiente_paso_texto}
        {c.condiciones.length > 0 && <Lista items={c.condiciones} />}
      </Pregunta>
      <Pregunta n={7} t="Incertidumbre">
        <span className="font-semibold capitalize">{r.incertidumbre}</span>
        {r.incertidumbre_razones.length > 0 && <Lista items={r.incertidumbre_razones} />}
      </Pregunta>
      <div className="rounded-xl bg-app-surface-2 p-3">
        <div className="text-label font-bold uppercase text-app-text-faint mb-1">Preguntas para revisar tu idea</div>
        <Lista items={c.preguntas} />
      </div>
      <p className="text-label text-app-text-faint">{c.salvedad}</p>
      <details className="text-label text-app-text-faint"><summary className="cursor-pointer">Regla de la conclusión</summary><p className="mt-1">{c.regla}</p></details>
    </div>
  )
}

function Pregunta({ n, t, children }: { n: number; t: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-label font-bold uppercase text-app-text-faint">{n}. {t}</div>
      <div className="text-caption text-app-text mt-0.5">{children}</div>
    </div>
  )
}

const TONO_FUENTE: Record<FuenteDecision['estado'], string> = {
  ok: 'text-app-pos', viejo: 'text-app-warn', falta: 'text-app-text-faint',
}

export function Fuentes({ fuentes }: { fuentes: FuenteDecision[] }) {
  return (
    <ul className="flex flex-col divide-y divide-app-border">
      {fuentes.map(f => (
        <li key={f.dato} className="py-1.5 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-caption text-app-text">{f.dato}</div>
            <div className="text-label text-app-text-faint">{f.fuente}{f.nota ? ` · ${f.nota}` : ''}</div>
          </div>
          <div className={`text-label font-mono tabular-nums text-right shrink-0 ${TONO_FUENTE[f.estado]}`}>
            {f.fecha ?? (f.estado === 'falta' ? 'sin dato' : 'ok')}
            {f.antiguedad_dias != null && <div className="text-app-text-faint">{f.antiguedad_dias} d</div>}
          </div>
        </li>
      ))}
    </ul>
  )
}
