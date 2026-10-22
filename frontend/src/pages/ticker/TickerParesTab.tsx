import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { actualizarClasificacion, getValuacionTicker, type FilaValuacion, type ValuacionTicker } from '../../api'
import { qk } from '../../api/queryClient'
import Card from '../../components/ui/Card'
import Button from '../../components/ui/Button'
import Segmented from '../../components/ui/Segmented'
import QueryBoundary from '../../components/ui/QueryBoundary'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../../components/icons/Icons'
import FuerzaRelativaChart from '../../components/charts/FuerzaRelativaChart'
import EditorClasificacion from '../../components/valuacion/EditorClasificacion'
import EditorPares from '../../components/valuacion/EditorPares'
import DiagnosticoCard from '../../components/valuacion/DiagnosticoCard'
import ComparadorAlternativas from '../../components/valuacion/ComparadorAlternativas'
import ValorRazonable from '../../components/valuacion/ValorRazonable'
import ImpactoCartera from '../../components/valuacion/ImpactoCartera'
import HistorialDiagnostico from '../../components/valuacion/HistorialDiagnostico'
import {
  FuenteBadge, LecturaBadge, NOMBRE_GRUPO, OrigenTag, TONO_FRASE, formatMetrica, formatTamano,
} from '../../components/valuacion/comun'

const GRUPOS = ['valuacion', 'calidad', 'crecimiento', 'momentum'] as const

function textoBanda(f: FilaValuacion): string | null {
  if (f.banda == null) return null
  if (f.grupo === 'valuacion') {
    return f.banda === 'mejor' ? 'más barata' : f.banda === 'peor' ? 'más cara' : 'en el medio'
  }
  return f.banda === 'mejor' ? 'mejor' : f.banda === 'peor' ? 'peor' : 'en el medio'
}

/** Dónde cae el emisor dentro de su grupo: 0 = el peor, 100 = el mejor (en valuación, el más
 *  barato). La palabra al lado dice lo mismo que la posición: el color sólo acompaña. */
function BarraPercentil({ fila, par }: { fila: FilaValuacion; par: string | null }) {
  if (fila.metodo === 'directo' && fila.diferencia != null) {
    // Un solo par: no hay posición dentro de un grupo, sólo la diferencia contra ese par.
    const pct = Math.abs(fila.diferencia * 100)
    const lado = fila.diferencia < 0 ? 'por debajo de' : 'por encima de'
    const color = fila.banda === 'mejor' ? 'text-app-pos' : fila.banda === 'peor' ? 'text-app-neg' : 'text-app-text-dim'
    return (
      <span className="text-label">
        <span className="text-app-text-dim">{pct < 1 ? 'igual a' : `${pct.toFixed(0)}% ${lado}`} {par ?? 'su par'}</span>
        {' · '}<span className={`font-semibold ${color}`}>{textoBanda(fila)}</span>
      </span>
    )
  }
  if (fila.percentil == null) {
    return <span className="text-label text-app-text-faint">{fila.valor == null ? 'sin dato' : `pocos pares (${fila.n})`}</span>
  }
  const color = fila.banda === 'mejor' ? 'bg-app-pos' : fila.banda === 'peor' ? 'bg-app-neg' : 'bg-app-text-dim'
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="relative flex-1 h-1.5 rounded-full bg-app-surface-2 min-w-[60px]" aria-hidden="true">
        <div className="absolute inset-y-0 left-1/4 right-1/4 bg-white/5" />
        <div className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full ring-2 ring-app-surface ${color}`} style={{ left: `${fila.percentil}%` }} />
      </div>
      <span className="text-label font-semibold text-app-text-dim whitespace-nowrap">{textoBanda(fila)}</span>
    </div>
  )
}

function VistaPorMetrica({ v }: { v: ValuacionTicker }) {
  const parUnico = v.pares.items.filter(p => p.tiene_datos).length === 1
    ? v.pares.items.find(p => p.tiene_datos)!.ticker_base
    : null
  return (
    <div className="flex flex-col gap-4">
      {GRUPOS.map(grupo => {
        const filas = v.tabla.filas.filter(f => f.grupo === grupo)
        if (filas.length === 0) return null
        return (
          <div key={grupo}>
            <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">{NOMBRE_GRUPO[grupo]}</div>
            <div className="flex flex-col">
              {filas.map(f => (
                <div key={f.clave} className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 py-2 border-b border-app-border-soft last:border-b-0">
                  <div className="text-caption text-app-text flex items-center gap-1.5 min-w-0">
                    <span className="truncate">{f.nombre}</span>
                    {f.origen !== 'observado' && <OrigenTag origen={f.origen} />}
                  </div>
                  <div className="text-caption font-mono text-app-text text-right">
                    {formatMetrica(f.valor, f.formato)}
                    <span className="text-app-text-faint"> · {f.metodo === 'directo' && parUnico ? parUnico : 'mediana'} {formatMetrica(f.mediana_pares, f.formato)}</span>
                  </div>
                  <div className="col-span-2"><BarraPercentil fila={f} par={parUnico} /></div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function VistaTabla({ v }: { v: ValuacionTicker }) {
  return (
    <div className="overflow-x-auto -mx-4 px-4">
      <table className="text-caption border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 bg-app-surface text-left font-semibold text-app-text-dim pr-3 py-1.5">Métrica</th>
            {v.tabla.columnas.map((c, i) => (
              <th key={c} className={`text-right font-mono font-bold px-2 py-1.5 whitespace-nowrap ${i === 0 ? 'text-app-accent' : 'text-app-text-dim'}`}>{c}</th>
            ))}
            <th className="text-right font-semibold text-app-text-dim px-2 py-1.5">Mediana</th>
          </tr>
        </thead>
        <tbody>
          {v.tabla.filas.map(f => (
            <tr key={f.clave}>
              <td className="sticky left-0 bg-app-surface text-app-text pr-3 py-1.5 border-t border-app-border-soft whitespace-nowrap">{f.nombre}{f.origen === 'estimado' ? ' (est.)' : ''}</td>
              {v.tabla.columnas.map((c, i) => (
                <td key={c} className={`text-right font-mono px-2 py-1.5 border-t border-app-border-soft whitespace-nowrap ${i === 0 ? 'text-app-text font-bold' : 'text-app-text-dim'}`}>
                  {formatMetrica(f.valores[c], f.formato)}
                </td>
              ))}
              <td className="text-right font-mono px-2 py-1.5 border-t border-app-border-soft text-app-text-dim whitespace-nowrap">{formatMetrica(f.mediana_pares, f.formato)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function TickerParesTab({ ticker }: { ticker: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [vista, setVista] = useState<'metrica' | 'tabla'>('metrica')
  const [editorClasif, setEditorClasif] = useState(false)
  const [editorPares, setEditorPares] = useState(false)

  const query = useQuery({
    queryKey: qk.de('valuacion-ticker', ticker),
    queryFn: () => getValuacionTicker(ticker),
  })
  const actualizar = useMutation({
    mutationFn: () => actualizarClasificacion([ticker]),
    onSuccess: () => void queryClient.invalidateQueries(),
  })

  const v = query.data
  const c = v?.clasificacion

  return (
    <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
      {v && c && (
        <div className="flex flex-col gap-3">
          <Card>
            <div className="flex items-start justify-between gap-2 mb-2">
              <LecturaBadge lectura={v.lectura} texto={v.lectura_texto} />
              <InfoTooltip term="valuacion_que_es" label="" />
            </div>
            {v.frases.length > 0 ? (
              <div className="flex flex-col gap-2">
                {v.frases.map((f, i) => (
                  <div key={i} className={`border-l-2 pl-2.5 ${TONO_FRASE[f.tono]}`}>
                    <div className="text-body text-app-text">{f.texto}</div>
                    <div className="text-label text-app-text-faint">Regla: {f.regla}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-caption text-app-text-dim">
                {v.estado_datos === 'ok'
                  ? 'No hay suficientes pares con datos para comparar todavía.'
                  : v.estado_datos === 'no_encontrado'
                    ? `Yahoo no tiene datos de ${v.simbolo_yahoo ?? ticker}. Si el símbolo es otro, corregilo desde Clasificación.`
                    : v.estado_datos === 'no_apto'
                      ? 'Bonos, ONs, letras y FCI todavía no se comparan contra pares.'
                      : 'Todavía no hay fundamentales de este emisor. La app los baja sola de a poco; podés pedirlos ya con "Actualizar datos".'}
              </p>
            )}
            <div className="text-label text-app-text-faint mt-2">Lectura: {v.regla_lectura}</div>
            {v.advertencias.map(a => (
              <div key={a} className="flex gap-1.5 items-start text-caption text-app-warn mt-2">
                <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {a}
              </div>
            ))}
          </Card>

          {v.diagnostico.confianza !== 'sin_datos' && <DiagnosticoCard diagnostico={v.diagnostico} fechaDato={v.fecha_dato} />}

          {v.estado_datos !== 'no_apto' && (
            <Button variant="outline" icon={<Icon name="compass" className="w-4 h-4" />}
                    onClick={() => navigate(`/decisiones/analisis/${encodeURIComponent(ticker)}`)}>
              Analizar decisión
            </Button>
          )}

          <Card>
            <div className="flex items-center justify-between mb-2">
              <div className="text-strong font-bold text-app-text">Clasificación</div>
              <button onClick={() => setEditorClasif(true)} className="text-caption font-bold text-app-accent transition-[color,transform] duration-150 hover:text-blue-300 active:scale-95">Corregir</button>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-caption">
              {([['Tipo', 'tipo'], ['Región', 'region'], ['País', 'pais'], ['Sector', 'sector'], ['Industria', 'industria']] as const).map(([label, campo]) => (
                <div key={campo} className="contents">
                  <dt className="text-app-text-dim">{label}</dt>
                  <dd className="text-app-text flex items-center gap-1.5 min-w-0 flex-wrap">
                    <span className="truncate">{c[campo] ?? '—'}</span>
                    <FuenteBadge fuente={c.fuentes[campo]} />
                  </dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-1">
              <div className="text-strong font-bold text-app-text">Pares</div>
              <button onClick={() => setEditorPares(true)} className="text-caption font-bold text-app-accent transition-[color,transform] duration-150 hover:text-blue-300 active:scale-95">Editar</button>
            </div>
            <div className="text-label text-app-text-faint mb-2 flex items-center gap-1">
              Criterio: {v.pares.criterio || 'sin pares'} <InfoTooltip term="valuacion_pares_criterio" label="" />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {v.pares.items.map(p => (
                <button
                  key={p.ticker_base}
                  onClick={() => navigate(`/ticker/${encodeURIComponent(p.ticker_base)}`)}
                  className="text-left bg-app-surface-2 border border-app-border rounded-[9px] px-2.5 py-1.5 transition-[border-color,transform] duration-150 hover:border-app-accent/50 active:scale-95"
                  title={p.nombre ?? undefined}
                >
                  <div className="text-label font-bold font-mono text-app-text">{p.ticker_base}{p.agregado ? ' ·' : ''}</div>
                  <div className="text-label text-app-text-faint">{p.tiene_datos ? formatTamano(p.tamano_usd) : 'pendiente'}</div>
                </button>
              ))}
            </div>
          </Card>

          <ComparadorAlternativas ticker={ticker} />
          <ValorRazonable ticker={ticker} />
          <ImpactoCartera ticker={ticker} />
          <HistorialDiagnostico ticker={ticker} />

          {v.tabla.filas.length > 0 && (
            <Card>
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="text-strong font-bold text-app-text flex items-center gap-1">
                  Contra sus pares <InfoTooltip term="valuacion_percentil" label="" />
                </div>
                <Segmented
                  options={[{ value: 'metrica', label: 'Por métrica' }, { value: 'tabla', label: 'Tabla' }]}
                  value={vista}
                  onChange={setVista}
                />
              </div>
              {vista === 'metrica' ? <VistaPorMetrica v={v} /> : <VistaTabla v={v} />}
            </Card>
          )}

          {v.fuerza_relativa.length > 1 && (
            <Card>
              <div className="text-strong font-bold text-app-text mb-2">Precio vs. sus pares</div>
              <FuerzaRelativaChart
                key={v.pares.items.map(p => p.ticker_base).join(',')}
                puntos={v.fuerza_relativa}
                ticker={v.ticker_base}
                pares={v.pares.items.map(p => p.ticker_base)}
              />
            </Card>
          )}

          <Button
            variant="outline"
            icon={<Icon name="sync" className="w-4 h-4" />}
            loading={actualizar.isPending}
            onClick={() => actualizar.mutate()}
          >
            Actualizar datos
          </Button>
          {actualizar.data && actualizar.data.resultado !== 'ok' && (
            <p className="text-caption text-app-text-dim text-center">
              {actualizar.data.resultado === 'sin_fuentes' ? 'Las fuentes externas están apagadas en este servidor.'
                : actualizar.data.resultado === 'en_curso' ? 'Ya hay una actualización en curso; probá en un rato.'
                : actualizar.data.resultado === 'rate_limited' ? 'Yahoo está limitando los pedidos; se reintenta solo más tarde.'
                : 'No se pudo actualizar ahora; se reintenta en la próxima corrida.'}
            </p>
          )}
          <p className="text-label text-app-text-faint text-center">
            {v.fecha_dato ? `Datos de Yahoo del ${v.fecha_dato.split('-').reverse().join('/')}. ` : ''}
            Sirve para encontrar candidatos para mirar, no es una recomendación de compra o venta.
          </p>

          <EditorClasificacion ticker={ticker} open={editorClasif} onClose={() => setEditorClasif(false)} />
          <EditorPares valuacion={v} open={editorPares} onClose={() => setEditorPares(false)} />
        </div>
      )}
    </QueryBoundary>
  )
}
