import type { ReactNode } from 'react'
import type { CategoriaEvento, Evento } from '../../api'
import { fechaCorta, fechaHora } from '../../utils/fechas'
import {
  COLOR_CATEGORIA, esEstimada, ETIQUETA_CATEGORIA, ETIQUETA_ESTADO, ETIQUETA_IMPORTANCIA, ETIQUETA_PRECISION,
  ETIQUETA_VERIFICACION,
} from '../../utils/eventos'

export function PuntoCategoria({ categoria, className = 'w-2 h-2' }: { categoria: CategoriaEvento; className?: string }) {
  return <span aria-hidden="true" className={`inline-block rounded-full shrink-0 ${className}`} style={{ background: COLOR_CATEGORIA[categoria] }} />
}

export function Etiqueta({ children, tono = 'neutro', titulo }: { children: ReactNode; tono?: 'neutro' | 'pos' | 'neg' | 'warn' | 'accent' | 'violet'; titulo?: string }) {
  const clases = {
    neutro: 'bg-app-surface-2 text-app-text-dim',
    pos: 'bg-app-pos-soft text-app-pos',
    neg: 'bg-app-neg-soft text-app-neg',
    warn: 'bg-app-warn/15 text-app-warn',
    accent: 'bg-app-accent-soft text-app-accent',
    violet: 'bg-app-violet/15 text-app-violet',
  }[tono]
  return <span title={titulo} className={`inline-flex items-center gap-1 font-bold text-label px-1.5 py-0.5 rounded-[6px] whitespace-nowrap ${clases}`}>{children}</span>
}

export function EtiquetaCategoria({ categoria }: { categoria: CategoriaEvento }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-label font-bold text-app-text-dim whitespace-nowrap">
      <PuntoCategoria categoria={categoria} />
      {ETIQUETA_CATEGORIA[categoria]}
    </span>
  )
}

export function EtiquetaImportancia({ importancia }: { importancia: number }) {
  const tono = importancia >= 3 ? 'neg' : importancia === 2 ? 'warn' : 'neutro'
  return <Etiqueta tono={tono} titulo="Importancia para el mercado (no indica dirección)">Importancia {ETIQUETA_IMPORTANCIA[importancia]?.toLowerCase()}</Etiqueta>
}

export function EtiquetaVerificacion({ verificacion }: { verificacion: string }) {
  const tono = verificacion === 'fuente_oficial' || verificacion === 'verificado_usuario' ? 'pos'
    : verificacion === 'multiples_fuentes' ? 'accent'
    : verificacion === 'rumor' ? 'neg'
    : verificacion === 'catalogo_revisar' ? 'violet' : 'neutro'
  return <Etiqueta tono={tono}>{ETIQUETA_VERIFICACION[verificacion] ?? verificacion}</Etiqueta>
}

/** Programado, confirmado, estimado o en desarrollo: lo que hay que saber de la fecha y el estado. */
export function EtiquetasEstado({ evento }: { evento: Evento }) {
  return (
    <>
      {evento.programado && <Etiqueta tono="accent">Programado</Etiqueta>}
      <Etiqueta tono={evento.estado === 'en_desarrollo' ? 'warn' : evento.estado === 'cancelado' ? 'neg' : 'neutro'}>
        {ETIQUETA_ESTADO[evento.estado] ?? evento.estado}
      </Etiqueta>
      {esEstimada(evento) && <Etiqueta tono="warn">{ETIQUETA_PRECISION[evento.precision_fecha]}</Etiqueta>}
    </>
  )
}

export function textoFechaEvento(e: Evento): string {
  const base = e.precision_fecha === 'mes'
    ? fechaCorta(e.fecha_evento).replace(/^\d+\s/, '')
    : e.precision_fecha === 'anio' ? e.fecha_evento.slice(0, 4) : fechaCorta(e.fecha_evento)
  const hora = e.hora_evento ? ` · ${e.hora_evento}${e.zona_horaria ? ` (${e.zona_horaria.split('/').pop()?.replace(/_/g, ' ')})` : ''}` : ''
  const fin = e.fecha_fin ? ` → ${fechaCorta(e.fecha_fin)}` : ''
  return `${e.precision_fecha === 'aproximada' ? '≈ ' : ''}${base}${fin}${hora}`
}

/** La fecha de conocimiento sólo se muestra si cae otro día que el evento. */
export function textoConocimiento(e: Evento): string | null {
  if (!e.fecha_publicacion) return null
  const pub = e.fecha_publicacion.slice(0, 10)
  if (pub === e.fecha_evento && !e.hora_evento) return `Publicado ${fechaHora(e.fecha_publicacion + 'Z')}`
  return pub === e.fecha_evento ? null : `Conocido el ${fechaHora(e.fecha_publicacion + 'Z')}`
}

/** Enlace externo seguro: sólo http/https, sin `referrer` ni acceso a `window.opener`. */
export function EnlaceFuente({ url, children }: { url: string | null; children: ReactNode }) {
  if (!url || !/^https?:\/\//i.test(url)) return <>{children}</>
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="text-app-accent hover:underline break-all">
      {children}
    </a>
  )
}

export function dominio(url: string | null): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
