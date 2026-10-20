import type { ReactNode } from 'react'
import type { LecturaNivelOut, LecturaTecnicaOut } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta, formatoPct, formatoPrecio, formatoValor } from './formatoEjes'

type Tono = 'pos' | 'neg' | 'warn' | 'accent' | 'neutro'

const CLASE_TONO: Record<Tono, string> = {
  pos: 'bg-app-pos-soft text-app-pos',
  neg: 'bg-app-neg-soft text-app-neg',
  warn: 'bg-app-warn/15 text-app-warn',
  accent: 'bg-app-accent-soft text-app-accent',
  neutro: 'bg-app-surface-2 text-app-text-dim',
}

const TENDENCIA: Record<'alcista' | 'bajista' | 'mixta', { texto: string; tono: Tono }> = {
  alcista: { texto: 'Alcista', tono: 'pos' },
  bajista: { texto: 'Bajista', tono: 'neg' },
  mixta: { texto: 'Sin dirección clara', tono: 'neutro' },
}

// Sobrecompra no es "malo" ni sobreventa "bueno": son avisos de que el precio se estiró. Por eso
// no van en verde y rojo.
const MOMENTUM: Record<'sobrecompra' | 'sobreventa' | 'neutral', { texto: string; tono: Tono; frase: string }> = {
  sobrecompra: { texto: 'Sobrecompra', tono: 'warn', frase: 'subió mucho en poco tiempo; muchas veces pausa o corrige.' },
  sobreventa: { texto: 'Sobreventa', tono: 'accent', frase: 'cayó mucho en poco tiempo; muchas veces rebota.' },
  neutral: { texto: 'Neutral', tono: 'neutro', frase: 'ni estirado para arriba ni para abajo.' },
}

const FUERZA: Record<'mejor' | 'peor' | 'parecida', { tono: Tono; texto: (indice: string) => string }> = {
  mejor: { tono: 'pos', texto: indice => `Mejor que el ${indice}` },
  peor: { tono: 'neg', texto: indice => `Peor que el ${indice}` },
  parecida: { tono: 'neutro', texto: indice => `Parecido al ${indice}` },
}

function Estado({ tono, children }: { tono: Tono; children: string }) {
  return <span className={`shrink-0 px-2 py-0.5 rounded-full text-label font-semibold ${CLASE_TONO[tono]}`}>{children}</span>
}

function Fila({ titulo, estado, children }: { titulo: string; estado?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 px-3.5 py-2.5 border-t border-app-border">
      <div className="flex items-center justify-between gap-2">
        <span className="text-label font-bold uppercase tracking-wide text-app-text-dim">{titulo}</span>
        {estado}
      </div>
      <div className="text-caption text-app-text">{children}</div>
    </div>
  )
}

function Nivel({ titulo, nivel, moneda, tono }: { titulo: string; nivel: LecturaNivelOut | null; moneda: string; tono: string }) {
  return (
    <div className="flex flex-col min-w-0">
      <span className="text-label text-app-text-dim">{titulo}</span>
      {nivel ? (
        <>
          <span className="font-mono tabular-nums text-body font-semibold text-app-text">
            {moneda} {formatoPrecio(nivel.precio)} <span className={`text-label ${tono}`}>{formatoPct(nivel.distancia_pct)}</span>
          </span>
          <span className="text-label text-app-text-faint">{nivel.toques} toques · último {fechaCorta(nivel.ultima_fecha)}</span>
        </>
      ) : (
        <span className="text-label text-app-text-faint">Ninguno claro en el último año</span>
      )}
    </div>
  )
}

/** "Qué dice el gráfico": la lectura del backend contada en palabras, con el número que decide
 * cada estado al lado para que se pueda verificar en el gráfico. */
export default function LecturaGrafico({
  lectura, cargando, error, onActivarFuerzaRelativa,
}: {
  lectura?: LecturaTecnicaOut
  cargando: boolean
  error: boolean
  /** Si el índice todavía no se bajó, la fila de fuerza relativa ofrece prender el panel (que lo baja). */
  onActivarFuerzaRelativa?: () => void
}) {
  return (
    <section aria-labelledby="lectura-grafico" className="rounded-2xl bg-app-surface border border-app-border">
      <div className="flex items-center justify-between gap-2 px-3.5 pt-3 pb-2">
        <h2 id="lectura-grafico" className="inline-flex items-center gap-1 text-strong font-bold text-app-text">
          Qué dice el gráfico
          <InfoTooltip term="lectura_grafico" />
        </h2>
        {lectura?.fecha && <span className="text-label text-app-text-dim">velas diarias · {fechaCorta(lectura.fecha)}</span>}
      </div>

      {error ? (
        <p className="px-3.5 pb-3 text-caption text-app-neg">No se pudo calcular la lectura de este ticker.</p>
      ) : cargando || !lectura ? (
        <div className="px-3.5 pb-3 flex flex-col gap-2" aria-busy="true">
          {[0, 1, 2].map(i => <div key={i} className="h-10 rounded-lg bg-app-surface-2 animate-pulse" />)}
        </div>
      ) : (
        <Contenido lectura={lectura} onActivarFuerzaRelativa={onActivarFuerzaRelativa} />
      )}
    </section>
  )
}

function Contenido({ lectura, onActivarFuerzaRelativa }: { lectura: LecturaTecnicaOut; onActivarFuerzaRelativa?: () => void }) {
  const { tendencia: t, momentum: m, fuerza_relativa: fr, moneda } = lectura
  return (
    <>
      <Fila titulo="Tendencia" estado={t && <Estado tono={TENDENCIA[t.estado].tono}>{TENDENCIA[t.estado].texto}</Estado>}>
        {t ? (
          <>
            El precio está <b className="font-mono">{formatoPct(t.distancia_pct)}</b> contra la SMA {t.periodo_sma}, que{' '}
            {t.pendiente_pct >= 0 ? 'viene subiendo' : 'viene bajando'} (<span className="font-mono">{formatoPct(t.pendiente_pct)}</span> en{' '}
            {t.ruedas_pendiente} ruedas).
            {t.estado === 'mixta' && ' El precio y la media no van para el mismo lado.'}
          </>
        ) : (
          <span className="text-app-text-dim">Hace falta más historia para tener la SMA 50.</span>
        )}
      </Fila>

      <Fila titulo="Momentum" estado={m && <Estado tono={MOMENTUM[m.estado].tono}>{MOMENTUM[m.estado].texto}</Estado>}>
        {m ? (
          <>RSI {m.periodo_rsi} en <b className="font-mono">{formatoValor(m.rsi)}</b>: {MOMENTUM[m.estado].frase}</>
        ) : (
          <span className="text-app-text-dim">Hace falta más historia para el RSI.</span>
        )}
      </Fila>

      <Fila titulo="Niveles cercanos">
        <div className="grid grid-cols-2 gap-3 mt-0.5">
          <Nivel titulo="Soporte" nivel={lectura.soporte} moneda={moneda} tono="text-app-neg" />
          <Nivel titulo="Resistencia" nivel={lectura.resistencia} moneda={moneda} tono="text-app-pos" />
        </div>
      </Fila>

      <Fila
        titulo="Fuerza relativa"
        estado={fr && lectura.benchmark_nombre && (
          <Estado tono={FUERZA[fr.estado].tono}>{FUERZA[fr.estado].texto(lectura.benchmark_nombre)}</Estado>
        )}
      >
        {fr && lectura.benchmark_nombre ? (
          <>
            En {fr.ruedas} ruedas (unos 3 meses) rindió <b className="font-mono">{formatoPct(fr.retorno_pct)}</b> y el{' '}
            {lectura.benchmark_nombre} <span className="font-mono">{formatoPct(fr.retorno_benchmark_pct)}</span>:{' '}
            <span className="font-mono">{formatoValor(Math.abs(fr.diferencia_puntos))}</span> puntos de diferencia.
          </>
        ) : (
          <span className="text-app-text-dim">
            Todavía no está la historia del índice.
            {onActivarFuerzaRelativa && (
              <>
                {' '}
                <button type="button" onClick={onActivarFuerzaRelativa} className="font-semibold text-app-accent">
                  Bajarla con «Fuerza rel.»
                </button>
              </>
            )}
          </span>
        )}
      </Fila>
    </>
  )
}
