import type { Evento } from '../../api'
import { Icon } from '../icons/Icons'
import { ETIQUETA_ORIGEN } from '../../utils/eventos'
import {
  dominio, EtiquetaCategoria, EtiquetaImportancia, EtiquetasEstado, EtiquetaVerificacion, textoConocimiento,
  textoFechaEvento,
} from './comun'

/** Un evento en la timeline o en la lista de un día. Tocarla abre la ficha completa. */
export default function TarjetaEvento({ evento, onAbrir }: { evento: Evento; onAbrir: (id: number) => void }) {
  const tickers = evento.instrumentos.filter(v => v.estado_revision !== 'descartada')
  const conocimiento = textoConocimiento(evento)
  const lugar = [evento.pais, evento.region && evento.region !== evento.pais ? evento.region : null, ...(evento.entidades.sectores ?? [])]
    .filter(Boolean).join(' · ')
  const resumen = evento.resumen || evento.descripcion
  return (
    <button
      onClick={() => onAbrir(evento.id)}
      className={`w-full text-left bg-app-surface border rounded-2xl p-3.5 flex flex-col gap-1.5 transition-[border-color,transform] duration-150 hover:border-white/20 active:scale-[0.99] ${
        evento.fijado ? 'border-app-accent/50' : 'border-app-border'
      } ${evento.descartado ? 'opacity-50' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <EtiquetaCategoria categoria={evento.categoria} />
        <span className={`font-mono tabular-nums text-label ${evento.es_futuro ? 'text-app-accent' : 'text-app-text-faint'}`}>
          {textoFechaEvento(evento)}
        </span>
      </div>
      <div className="text-body font-semibold text-app-text leading-snug">
        {evento.fijado && <span aria-label="Fijado" className="mr-1">📌</span>}
        {evento.titulo}
      </div>
      {conocimiento && <div className="text-label text-app-text-faint">{conocimiento}</div>}
      {resumen && <p className="text-caption text-app-text-dim line-clamp-2">{resumen}</p>}
      <div className="flex flex-wrap items-center gap-1">
        <EtiquetaImportancia importancia={evento.importancia} />
        <EtiquetasEstado evento={evento} />
        <EtiquetaVerificacion verificacion={evento.verificacion} />
      </div>
      {(lugar || tickers.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-app-text-dim">
          {lugar && <span>{lugar}</span>}
          {tickers.slice(0, 6).map(v => (
            <span key={v.ticker} className={`font-mono font-bold ${v.estado_revision === 'propuesta' ? 'text-app-text-faint' : 'text-app-text'}`}>
              {v.ticker}
            </span>
          ))}
          {tickers.length > 6 && <span>+{tickers.length - 6}</span>}
        </div>
      )}
      <div className="flex items-center justify-between gap-2 text-label text-app-text-faint">
        <span className="truncate">
          {ETIQUETA_ORIGEN[evento.origen] ?? evento.origen}
          {evento.fuente_principal ? ` · ${evento.fuente_principal}` : dominio(evento.url_fuente) ? ` · ${dominio(evento.url_fuente)}` : ''}
        </span>
        <span className="flex items-center gap-2 shrink-0">
          {evento.n_noticias > 0 && <span>{evento.n_noticias} noticia{evento.n_noticias === 1 ? '' : 's'}</span>}
          <Icon name="back" className="w-3.5 h-3.5 rotate-180" />
        </span>
      </div>
    </button>
  )
}
