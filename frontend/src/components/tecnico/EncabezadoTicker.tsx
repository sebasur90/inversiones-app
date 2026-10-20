import { useState } from 'react'
import type { BarraOut, IntervaloSerie, TickerTecnicoOut, VarianteSerie } from '../../api'
import Modal from '../ui/Modal'
import { Icon } from '../icons/Icons'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatoPct, formatoPrecio } from './formatoEjes'

const ORIGEN: Record<TickerTecnicoOut['origen'], string> = {
  cartera: 'en tu cartera',
  watchlist: 'en tu watchlist',
  ambos: 'en cartera y watchlist',
}

const PERIODO_VELA: Record<IntervaloSerie, string> = { D: 'en la última rueda', S: 'en la semana', M: 'en el mes' }

/** Arriba de todo en Análisis técnico: el ticker como título (tocarlo abre el buscador), el último
 * precio con su variación contra la vela anterior y, si el ticker tiene dos series, cuál se mira. */
export default function EncabezadoTicker({
  tickers, ticker, onElegir, barras, moneda, intervalo, seriesDisponibles, variante, referencia, onVariante,
}: {
  tickers: TickerTecnicoOut[]
  ticker: string
  onElegir: (ticker: string) => void
  /** Las barras de la serie a la vista; mientras carga, `undefined`. */
  barras?: BarraOut[]
  moneda: string
  intervalo: IntervaloSerie
  seriesDisponibles: { variante: VarianteSerie; moneda: string }[]
  variante: VarianteSerie
  referencia: VarianteSerie
  onVariante: (v: VarianteSerie) => void
}) {
  const [abierto, setAbierto] = useState(false)
  const meta = tickers.find(t => t.ticker === ticker)
  const ultima = barras?.[barras.length - 1]
  const previa = barras && barras.length > 1 ? barras[barras.length - 2] : undefined
  const cambio = ultima && previa ? ultima.cierre - previa.cierre : null
  const cambioPct = cambio != null && previa && previa.cierre ? (cambio / previa.cierre) * 100 : null
  const sube = (cambio ?? 0) >= 0

  return (
    <div className="flex flex-col gap-2 mb-3">
      <button
        type="button" onClick={() => setAbierto(true)} aria-label={`${ticker}: elegir otro ticker`}
        className="self-start flex flex-col items-start min-h-[44px] text-left"
      >
        <span className="inline-flex items-center gap-1">
          <span className="font-mono text-heading font-bold text-app-text">{ticker}</span>
          <Icon name="chevron" className="w-4 h-4 text-app-text-dim" />
        </span>
        {meta && (
          <span className="text-label text-app-text-dim">
            {meta.nombre}{meta.tipo_instrumento ? ` · ${meta.tipo_instrumento}` : ''} · {ORIGEN[meta.origen]}
          </span>
        )}
      </button>

      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 min-h-[36px]">
        {ultima ? (
          <>
            <span className="font-mono tabular-nums text-body font-semibold text-app-text-dim">{moneda}</span>
            <span className="font-mono tabular-nums text-metric-lg font-bold text-app-text">{formatoPrecio(ultima.cierre)}</span>
            {cambio != null && cambioPct != null && (
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-mono tabular-nums text-label font-semibold ${
                  sube ? 'bg-app-pos-soft text-app-pos' : 'bg-app-neg-soft text-app-neg'
                }`}
              >
                <Icon name={sube ? 'up' : 'down'} className="w-3 h-3" />
                {formatoPct(cambioPct)} {PERIODO_VELA[intervalo]}
              </span>
            )}
          </>
        ) : (
          <span className="h-8 w-40 rounded-lg bg-app-surface-2 animate-pulse" aria-hidden="true" />
        )}
      </div>

      {seriesDisponibles.length > 1 && (
        <div role="group" aria-label="Serie" className="flex flex-wrap items-center gap-1.5">
          {seriesDisponibles.map(s => {
            const activa = s.variante === variante
            return (
              <button
                key={s.variante} type="button" onClick={() => onVariante(s.variante)} aria-pressed={activa}
                className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-caption font-semibold border transition-colors ${
                  activa ? 'bg-app-accent-soft border-app-accent/60 text-app-text' : 'border-app-border text-app-text-dim'
                }`}
              >
                {s.variante === 'local' ? 'Local' : 'Subyacente'} {s.moneda}
                {s.variante === referencia && (
                  <span className="font-mono text-[10px] font-bold tracking-wider px-1 rounded bg-app-accent/25 text-app-accent">REF</span>
                )}
              </button>
            )
          })}
          <InfoTooltip term="serie_referencia" />
        </div>
      )}
      {seriesDisponibles.length > 1 && variante !== referencia && (
        <p className="text-label text-app-text-dim">
          Para decidir sobre {ticker}, la referencia es {referencia === 'subyacente' ? 'el precio en dólares de la acción en EE.UU.' : 'la serie local'}.
        </p>
      )}

      <SelectorTicker
        open={abierto} onClose={() => setAbierto(false)} tickers={tickers} actual={ticker}
        onElegir={t => { onElegir(t); setAbierto(false) }}
      />
    </div>
  )
}

function SelectorTicker({
  open, onClose, tickers, actual, onElegir,
}: {
  open: boolean
  onClose: () => void
  tickers: TickerTecnicoOut[]
  actual: string
  onElegir: (ticker: string) => void
}) {
  const [busqueda, setBusqueda] = useState('')
  const q = busqueda.trim().toLowerCase()
  const filtrados = q
    ? tickers.filter(t => t.ticker.toLowerCase().includes(q) || t.nombre.toLowerCase().includes(q))
    : tickers
  const grupos = [
    { titulo: 'En tu cartera', items: filtrados.filter(t => t.origen !== 'watchlist') },
    { titulo: 'En tu watchlist', items: filtrados.filter(t => t.origen === 'watchlist') },
  ].filter(g => g.items.length > 0)

  function cerrar() {
    setBusqueda('')
    onClose()
  }

  return (
    <Modal open={open} onClose={cerrar} title="Elegir ticker">
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 h-11 px-3 rounded-xl bg-app-bg border border-app-border text-app-text-dim">
          <Icon name="search" className="w-4 h-4" />
          <span className="sr-only">Buscar ticker</span>
          <input
            autoFocus value={busqueda} onChange={e => setBusqueda(e.target.value)}
            placeholder="Ticker o nombre"
            className="flex-1 min-w-0 bg-transparent outline-none text-body text-app-text"
          />
        </label>
        {grupos.length === 0 && <p className="text-caption text-app-text-dim">Ningún ticker coincide con «{busqueda}».</p>}
        {grupos.map(g => (
          <section key={g.titulo} className="flex flex-col">
            <h3 className="text-label font-bold uppercase tracking-wide text-app-text-dim pb-1">{g.titulo}</h3>
            {g.items.map(t => (
              <button
                key={t.ticker} type="button" onClick={() => { setBusqueda(''); onElegir(t.ticker) }}
                aria-current={t.ticker === actual}
                className={`flex items-center gap-3 min-h-[52px] px-2 -mx-2 rounded-xl text-left ${
                  t.ticker === actual ? 'bg-app-accent-soft' : ''
                }`}
              >
                <span className="w-20 shrink-0 font-mono font-bold text-body text-app-text">{t.ticker}</span>
                <span className="min-w-0 flex-1 truncate text-caption text-app-text-dim">{t.nombre}</span>
                {t.ticker === actual && <Icon name="check" className="w-4 h-4 text-app-accent" />}
              </button>
            ))}
          </section>
        ))}
      </div>
    </Modal>
  )
}
