import { useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { crearEvento, editarEvento, type Evento, type EventoIn, type EventoVinculoIn } from '../../api'
import { qk } from '../../api/queryClient'
import { parseApiError } from '../../help/errors/apiErrors'
import Button from '../ui/Button'
import Chip from '../ui/Chip'
import { CATEGORIAS, ETIQUETA_CATEGORIA, ETIQUETA_ESTADO, ETIQUETA_PRECISION, ETIQUETA_RELACION, ETIQUETA_VERIFICACION } from '../../utils/eventos'

const CLASE_INPUT = 'w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-body text-app-text outline-none focus:border-app-accent/60'
const CLASE_AREA = 'w-full rounded-xl bg-app-surface-2 border border-app-border px-3.5 py-2.5 text-body text-app-text outline-none focus:border-app-accent/60'
const ZONAS = ['', 'America/Argentina/Buenos_Aires', 'America/New_York', 'America/Sao_Paulo', 'Europe/London', 'Europe/Berlin', 'Asia/Shanghai', 'Asia/Tokyo', 'UTC']
const RELACIONES_FORM = ['directa', 'matriz', 'sector', 'pais', 'macro', 'materia_prima', 'indice', 'otra']

function Campo({ etiqueta, children, ayuda }: { etiqueta: string; children: ReactNode; ayuda?: string }) {
  return (
    <label className="flex flex-col gap-1 mb-3">
      <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">{etiqueta}</span>
      {children}
      {ayuda && <span className="text-label text-app-text-faint">{ayuda}</span>}
    </label>
  )
}

const aLista = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean)

/** La fecha de publicación viaja en UTC; el input `datetime-local` es hora local del navegador. */
function aLocal(isoUtc: string | null): string {
  if (!isoUtc) return ''
  const d = new Date(isoUtc.endsWith('Z') ? isoUtc : isoUtc + 'Z')
  const off = d.getTimezoneOffset() * 60_000
  return new Date(d.getTime() - off).toISOString().slice(0, 16)
}
const aUtc = (local: string) => (local ? new Date(local).toISOString() : null)

/**
 * Alta y edición manual. Un evento puede no tener ticker (un acontecimiento global). Al editar uno
 * importado, el servidor recuerda qué campos tocaste y ningún proveedor los vuelve a pisar.
 */
export default function EventoForm({ evento, onListo, onCancelar }: { evento?: Evento | null; onListo: (e: Evento) => void; onCancelar: () => void }) {
  const qc = useQueryClient()
  const [titulo, setTitulo] = useState(evento?.titulo ?? '')
  const [categoria, setCategoria] = useState<string>(evento?.categoria ?? 'otro')
  const [subcategoria, setSubcategoria] = useState(evento?.subcategoria ?? '')
  const [fecha, setFecha] = useState(evento?.fecha_evento ?? '')
  const [fechaFin, setFechaFin] = useState(evento?.fecha_fin ?? '')
  const [hora, setHora] = useState(evento?.hora_evento ?? '')
  const [zona, setZona] = useState(evento?.zona_horaria ?? '')
  const [publicacion, setPublicacion] = useState(aLocal(evento?.fecha_publicacion ?? null))
  const [precision, setPrecision] = useState(evento?.precision_fecha ?? 'exacta')
  const [estado, setEstado] = useState(evento?.estado ?? '')
  const [programado, setProgramado] = useState(evento?.programado ?? false)
  const [pais, setPais] = useState(evento?.pais ?? '')
  const [region, setRegion] = useState(evento?.region ?? '')
  const [empresas, setEmpresas] = useState((evento?.entidades.empresas ?? []).join(', '))
  const [sectores, setSectores] = useState((evento?.entidades.sectores ?? []).join(', '))
  const [importancia, setImportancia] = useState<number>(evento?.importancia ?? 2)
  const [verificacion, setVerificacion] = useState(evento?.verificacion ?? 'sin_verificar')
  const [url, setUrl] = useState(evento?.url_fuente ?? '')
  const [fuente, setFuente] = useState(evento?.fuente_principal ?? '')
  const [descripcion, setDescripcion] = useState(evento?.descripcion ?? '')
  const [notas, setNotas] = useState(evento?.notas ?? '')
  const [instrumentos, setInstrumentos] = useState<EventoVinculoIn[]>(
    (evento?.instrumentos ?? []).filter(v => v.estado_revision !== 'descartada').map(v => ({
      ticker: v.ticker, tipo_relacion: v.tipo_relacion, relevancia: v.relevancia ?? 1, justificacion: v.justificacion, estado_revision: 'confirmada',
    })),
  )
  const [nuevoTicker, setNuevoTicker] = useState('')
  const [nuevaRelacion, setNuevaRelacion] = useState('directa')

  const agregarTicker = () => {
    const t = nuevoTicker.trim().toUpperCase()
    if (!t || instrumentos.some(v => v.ticker === t)) return
    const relevancia = nuevaRelacion === 'directa' ? 1 : nuevaRelacion === 'sector' ? 0.5 : nuevaRelacion === 'indice' ? 0.5 : 0.35
    setInstrumentos([...instrumentos, { ticker: t, tipo_relacion: nuevaRelacion, relevancia, estado_revision: 'confirmada' }])
    setNuevoTicker('')
  }

  const guardar = useMutation({
    mutationFn: () => {
      const body: EventoIn = {
        titulo: titulo.trim(), categoria, subcategoria: subcategoria.trim() || null, fecha_evento: fecha,
        fecha_fin: fechaFin || null, hora_evento: hora || null, zona_horaria: hora ? zona || null : null,
        fecha_publicacion: aUtc(publicacion), precision_fecha: precision, programado,
        pais: pais.trim() || null, region: region.trim() || null,
        entidades: { empresas: aLista(empresas), sectores: aLista(sectores) }, importancia, verificacion,
        url_fuente: url.trim() || null, fuente_principal: fuente.trim() || null, descripcion: descripcion.trim() || null,
        notas: notas.trim() || null, instrumentos, ...(estado ? { estado } : {}),
      }
      return evento ? editarEvento(evento.id, body) : crearEvento(body)
    },
    onSuccess: e => {
      void qc.invalidateQueries({ queryKey: qk.de('eventos') })
      onListo(e)
    },
  })
  const error = guardar.error ? parseApiError(guardar.error) : null
  const valido = titulo.trim() && fecha && (!fechaFin || fechaFin >= fecha) && (!url || /^https?:\/\//i.test(url.trim()))

  return (
    <form onSubmit={e => { e.preventDefault(); if (valido) guardar.mutate() }}>
      <Campo etiqueta="Título">
        <input value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={300} required className={CLASE_INPUT} placeholder="Ej.: Reunión de la Reserva Federal" />
      </Campo>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Categoría">
          <select value={categoria} onChange={e => setCategoria(e.target.value)} className={CLASE_INPUT}>
            {CATEGORIAS.map(c => <option key={c} value={c}>{ETIQUETA_CATEGORIA[c]}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Subcategoría">
          <input value={subcategoria} onChange={e => setSubcategoria(e.target.value)} maxLength={300} className={CLASE_INPUT} placeholder="Opcional" />
        </Campo>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Fecha del evento">
          <input type="date" value={fecha} onChange={e => setFecha(e.target.value)} required className={CLASE_INPUT} />
        </Campo>
        <Campo etiqueta="Termina (si dura)">
          <input type="date" value={fechaFin} min={fecha || undefined} onChange={e => setFechaFin(e.target.value)} className={CLASE_INPUT} />
        </Campo>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Hora">
          <input type="time" value={hora} onChange={e => setHora(e.target.value)} className={CLASE_INPUT} />
        </Campo>
        <Campo etiqueta="Zona horaria">
          <select value={zona} onChange={e => setZona(e.target.value)} disabled={!hora} className={CLASE_INPUT}>
            {ZONAS.map(z => <option key={z} value={z}>{z ? z.split('/').pop()!.replace(/_/g, ' ') : '—'}</option>)}
          </select>
        </Campo>
      </div>
      <Campo etiqueta="Lo supo el mercado (si difiere)" ayuda="Por ejemplo, una noticia publicada después del cierre. Es tu hora local.">
        <input type="datetime-local" value={publicacion} onChange={e => setPublicacion(e.target.value)} className={CLASE_INPUT} />
      </Campo>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Precisión de la fecha">
          <select value={precision} onChange={e => setPrecision(e.target.value as typeof precision)} className={CLASE_INPUT}>
            {Object.entries(ETIQUETA_PRECISION).map(([v, et]) => <option key={v} value={v}>{et}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Estado">
          <select value={estado} onChange={e => setEstado(e.target.value)} className={CLASE_INPUT}>
            <option value="">{evento ? ETIQUETA_ESTADO[evento.estado] : 'Según la fecha'}</option>
            {Object.entries(ETIQUETA_ESTADO).map(([v, et]) => <option key={v} value={v}>{et}</option>)}
          </select>
        </Campo>
      </div>
      <label className="mb-3 flex items-center gap-2 text-caption text-app-text">
        <input type="checkbox" checked={programado} onChange={e => setProgramado(e.target.checked)} className="h-4 w-4 accent-[#3b82f6]" />
        Es un evento programado (con fecha anunciada de antemano)
      </label>
      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="País">
          <input value={pais} onChange={e => setPais(e.target.value)} maxLength={300} className={CLASE_INPUT} placeholder="Argentina" />
        </Campo>
        <Campo etiqueta="Región">
          <input value={region} onChange={e => setRegion(e.target.value)} maxLength={300} className={CLASE_INPUT} placeholder="Opcional" />
        </Campo>
      </div>
      <Campo etiqueta="Empresas u organismos" ayuda="Separados por coma.">
        <input value={empresas} onChange={e => setEmpresas(e.target.value)} className={CLASE_INPUT} />
      </Campo>
      <Campo etiqueta="Sectores" ayuda="Separados por coma (Tecnología, Energía, Financiero…).">
        <input value={sectores} onChange={e => setSectores(e.target.value)} className={CLASE_INPUT} />
      </Campo>

      <div className="mb-3">
        <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Tickers relacionados</span>
        <div className="mt-1 flex gap-2">
          <input value={nuevoTicker} onChange={e => setNuevoTicker(e.target.value.toUpperCase())} maxLength={16}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); agregarTicker() } }}
            className={`${CLASE_INPUT} flex-1`} placeholder="AAPL, GGAL, ^MERV…" aria-label="Ticker" />
          <select value={nuevaRelacion} onChange={e => setNuevaRelacion(e.target.value)} className={`${CLASE_INPUT} w-32`} aria-label="Tipo de relación">
            {RELACIONES_FORM.map(r => <option key={r} value={r}>{ETIQUETA_RELACION[r]}</option>)}
          </select>
          <Button type="button" variant="outline" onClick={agregarTicker} disabled={!nuevoTicker.trim()}>+</Button>
        </div>
        {instrumentos.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {instrumentos.map(v => (
              <Chip key={v.ticker} onRemove={() => setInstrumentos(instrumentos.filter(x => x.ticker !== v.ticker))}>
                {v.ticker} · {ETIQUETA_RELACION[v.tipo_relacion ?? 'otra']}
              </Chip>
            ))}
          </div>
        )}
        <p className="mt-1 text-label text-app-text-faint">Puede quedar vacío: un evento global afecta a muchos activos de forma indirecta.</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="Importancia">
          <select value={importancia} onChange={e => setImportancia(Number(e.target.value))} className={CLASE_INPUT}>
            <option value={1}>Baja</option><option value={2}>Media</option><option value={3}>Alta</option>
          </select>
        </Campo>
        <Campo etiqueta="Verificación">
          <select value={verificacion} onChange={e => setVerificacion(e.target.value)} className={CLASE_INPUT}>
            {Object.entries(ETIQUETA_VERIFICACION).map(([v, et]) => <option key={v} value={v}>{et}</option>)}
          </select>
        </Campo>
      </div>
      <Campo etiqueta="URL de la fuente">
        <input type="url" value={url} onChange={e => setUrl(e.target.value)} maxLength={2000} className={CLASE_INPUT} placeholder="https://…" />
      </Campo>
      <Campo etiqueta="Fuente">
        <input value={fuente} onChange={e => setFuente(e.target.value)} maxLength={300} className={CLASE_INPUT} placeholder="Reserva Federal, Reuters…" />
      </Campo>
      <Campo etiqueta="Descripción">
        <textarea value={descripcion} onChange={e => setDescripcion(e.target.value)} maxLength={4000} rows={3} className={CLASE_AREA} />
      </Campo>
      <Campo etiqueta="Notas personales">
        <textarea value={notas} onChange={e => setNotas(e.target.value)} maxLength={4000} rows={2} className={CLASE_AREA} />
      </Campo>

      {error && <p className="mb-3 text-caption text-app-neg">{error.message}</p>}
      <div className="flex gap-2">
        <Button type="button" variant="ghost" className="flex-1" onClick={onCancelar}>Cancelar</Button>
        <Button type="submit" className="flex-1" loading={guardar.isPending} disabled={!valido}>{evento ? 'Guardar' : 'Crear evento'}</Button>
      </div>
    </form>
  )
}
