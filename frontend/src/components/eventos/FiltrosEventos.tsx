import { useState, type ReactNode } from 'react'
import type { CategoriaEvento, EventosOpciones } from '../../api'
import CampoBusqueda from '../ui/CampoBusqueda'
import Chip from '../ui/Chip'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import {
  CATEGORIAS, COLOR_CATEGORIA, ETIQUETA_CATEGORIA, ETIQUETA_ORIGEN, ETIQUETA_VERIFICACION, FILTROS_VACIOS,
  filtrosActivos, type FiltrosPantalla,
} from '../../utils/eventos'

function FiltroChip({ activo, onClick, children, color }: { activo: boolean; onClick: () => void; children: ReactNode; color?: string }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={activo}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[9px] px-2.5 py-1.5 text-label font-bold border transition-[background-color,border-color,transform] duration-150 active:scale-95 ${
        activo ? 'bg-app-accent-soft text-app-accent border-app-accent/40' : 'bg-app-surface text-app-text-dim border-app-border hover:border-white/20'
      }`}
    >
      {color && <span className="w-2 h-2 rounded-full" style={{ background: color }} />}
      {children}
    </button>
  )
}

function alternar<T>(lista: T[], v: T): T[] {
  return lista.includes(v) ? lista.filter(x => x !== v) : [...lista, v]
}

function Grupo({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 text-label font-bold uppercase tracking-wide text-app-text-faint">{titulo}</div>
      {children}
    </div>
  )
}

const TEMPORALIDAD = [
  { value: 'todos' as const, label: 'Todos' },
  { value: 'pasados' as const, label: 'Pasados' },
  { value: 'futuros' as const, label: 'Futuros' },
]
const IMPORTANCIA = [
  { value: '0', label: 'Cualquiera' },
  { value: '2', label: 'Media o alta' },
  { value: '3', label: 'Sólo alta' },
]
const CLASE_FECHA = 'h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-caption text-app-text'

/**
 * Lo que siempre está a mano (búsqueda y categorías) y una hoja con el resto. En el celular no entra
 * todo junto: los filtros activos de la hoja se ven igual como chips que se pueden quitar.
 */
export default function FiltrosEventos({
  filtros, onCambiar, q, onBuscar, opciones,
}: {
  filtros: FiltrosPantalla
  onCambiar: (f: FiltrosPantalla) => void
  q: string
  onBuscar: (q: string) => void
  opciones: EventosOpciones | undefined
}) {
  const [abierto, setAbierto] = useState(false)
  const set = (parcial: Partial<FiltrosPantalla>) => onCambiar({ ...filtros, ...parcial })
  const activos = filtrosActivos(filtros)

  const chips: { clave: string; texto: string; quitar: () => void }[] = [
    ...filtros.tickers.map(t => ({ clave: `t-${t}`, texto: t, quitar: () => set({ tickers: filtros.tickers.filter(x => x !== t) }) })),
    ...filtros.paises.map(p => ({ clave: `p-${p}`, texto: p, quitar: () => set({ paises: filtros.paises.filter(x => x !== p) }) })),
    ...filtros.sectores.map(s => ({ clave: `s-${s}`, texto: s, quitar: () => set({ sectores: filtros.sectores.filter(x => x !== s) }) })),
    ...(filtros.enCartera ? [{ clave: 'cartera', texto: 'Sólo mi cartera', quitar: () => set({ enCartera: false }) }] : []),
    ...(filtros.importanciaMin ? [{ clave: 'imp', texto: filtros.importanciaMin === 3 ? 'Importancia alta' : 'Importancia media o alta', quitar: () => set({ importanciaMin: null }) }] : []),
    ...(filtros.temporalidad !== 'todos' ? [{ clave: 'tmp', texto: filtros.temporalidad === 'futuros' ? 'Futuros' : 'Pasados', quitar: () => set({ temporalidad: 'todos' }) }] : []),
    ...filtros.verificaciones.map(v => ({ clave: `v-${v}`, texto: ETIQUETA_VERIFICACION[v] ?? v, quitar: () => set({ verificaciones: filtros.verificaciones.filter(x => x !== v) }) })),
    ...filtros.origenes.map(o => ({ clave: `o-${o}`, texto: ETIQUETA_ORIGEN[o] ?? o, quitar: () => set({ origenes: filtros.origenes.filter(x => x !== o) }) })),
    ...filtros.proveedores.map(p => ({ clave: `pr-${p}`, texto: p, quitar: () => set({ proveedores: filtros.proveedores.filter(x => x !== p) }) })),
    ...(filtros.desde ? [{ clave: 'desde', texto: `Desde ${filtros.desde}`, quitar: () => set({ desde: null }) }] : []),
    ...(filtros.hasta ? [{ clave: 'hasta', texto: `Hasta ${filtros.hasta}`, quitar: () => set({ hasta: null }) }] : []),
    ...(filtros.incluirDescartados ? [{ clave: 'desc', texto: 'Con descartados', quitar: () => set({ incluirDescartados: false }) }] : []),
  ]

  return (
    <div className="flex flex-col gap-2 mb-3">
      <div className="flex items-center gap-2">
        <CampoBusqueda value={q} onChange={onBuscar} placeholder="Buscar título, empresa, ticker…" ariaLabel="Buscar eventos" />
        <button
          onClick={() => setAbierto(true)}
          className={`h-11 px-3 rounded-xl border text-caption font-bold whitespace-nowrap transition-[background-color,transform] duration-150 active:scale-95 ${
            activos ? 'bg-app-accent-soft border-app-accent/40 text-app-accent' : 'bg-app-surface border-app-border text-app-text-dim'
          }`}
        >
          Filtros{activos ? ` (${activos})` : ''}
        </button>
      </div>
      <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1">
        {CATEGORIAS.map(c => (
          <FiltroChip key={c} color={COLOR_CATEGORIA[c]} activo={filtros.categorias.includes(c)}
            onClick={() => set({ categorias: alternar<CategoriaEvento>(filtros.categorias, c) })}>
            {ETIQUETA_CATEGORIA[c]}
          </FiltroChip>
        ))}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map(c => <Chip key={c.clave} onRemove={c.quitar}>{c.texto}</Chip>)}
        </div>
      )}

      <Modal open={abierto} onClose={() => setAbierto(false)} title="Filtros">
        <Grupo titulo="Cuándo">
          <Segmented options={TEMPORALIDAD} value={filtros.temporalidad} onChange={v => set({ temporalidad: v })} />
          <div className="mt-2 flex items-center gap-2">
            <label className="flex flex-col gap-1 text-label text-app-text-faint">
              Desde
              <input type="date" value={filtros.desde ?? ''} onChange={e => set({ desde: e.target.value || null })} className={CLASE_FECHA} />
            </label>
            <label className="flex flex-col gap-1 text-label text-app-text-faint">
              Hasta
              <input type="date" value={filtros.hasta ?? ''} onChange={e => set({ hasta: e.target.value || null })} className={CLASE_FECHA} />
            </label>
          </div>
        </Grupo>
        <Grupo titulo="Importancia">
          <Segmented options={IMPORTANCIA} value={String(filtros.importanciaMin ?? 0)} onChange={v => set({ importanciaMin: v === '0' ? null : Number(v) })} />
        </Grupo>
        <Grupo titulo="Instrumentos">
          <label className="mb-2 flex items-center gap-2 text-caption text-app-text">
            <input type="checkbox" checked={filtros.enCartera} onChange={e => set({ enCartera: e.target.checked })} className="h-4 w-4 accent-[#3b82f6]" />
            Sólo los que afectan a mi cartera
          </label>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
            {(opciones?.tickers ?? []).map(t => (
              <FiltroChip key={t} activo={filtros.tickers.includes(t)} onClick={() => set({ tickers: alternar(filtros.tickers, t) })}>{t}</FiltroChip>
            ))}
          </div>
        </Grupo>
        {(opciones?.paises.length ?? 0) > 0 && (
          <Grupo titulo="País o región">
            <div className="flex flex-wrap gap-1.5">
              {opciones!.paises.map(p => (
                <FiltroChip key={p} activo={filtros.paises.includes(p)} onClick={() => set({ paises: alternar(filtros.paises, p) })}>{p}</FiltroChip>
              ))}
            </div>
          </Grupo>
        )}
        {(opciones?.sectores.length ?? 0) > 0 && (
          <Grupo titulo="Sector">
            <div className="flex flex-wrap gap-1.5">
              {opciones!.sectores.map(s => (
                <FiltroChip key={s} activo={filtros.sectores.includes(s)} onClick={() => set({ sectores: alternar(filtros.sectores, s) })}>{s}</FiltroChip>
              ))}
            </div>
          </Grupo>
        )}
        <Grupo titulo="Verificación">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(ETIQUETA_VERIFICACION).map(([v, etiqueta]) => (
              <FiltroChip key={v} activo={filtros.verificaciones.includes(v)} onClick={() => set({ verificaciones: alternar(filtros.verificaciones, v) })}>{etiqueta}</FiltroChip>
            ))}
          </div>
        </Grupo>
        <Grupo titulo="Origen">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(ETIQUETA_ORIGEN).map(([o, etiqueta]) => (
              <FiltroChip key={o} activo={filtros.origenes.includes(o)} onClick={() => set({ origenes: alternar(filtros.origenes, o) })}>{etiqueta}</FiltroChip>
            ))}
          </div>
          {(opciones?.proveedores.length ?? 0) > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {opciones!.proveedores.map(p => (
                <FiltroChip key={p} activo={filtros.proveedores.includes(p)} onClick={() => set({ proveedores: alternar(filtros.proveedores, p) })}>{p}</FiltroChip>
              ))}
            </div>
          )}
        </Grupo>
        <label className="mb-4 flex items-center gap-2 text-caption text-app-text">
          <input type="checkbox" checked={filtros.incluirDescartados} onChange={e => set({ incluirDescartados: e.target.checked })} className="h-4 w-4 accent-[#3b82f6]" />
          Mostrar también los descartados
        </label>
        <div className="flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={() => onCambiar({ ...FILTROS_VACIOS, categorias: filtros.categorias })}>Limpiar</Button>
          <Button className="flex-1" onClick={() => setAbierto(false)}>Listo</Button>
        </div>
      </Modal>
    </div>
  )
}
