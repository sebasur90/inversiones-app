import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import {
  getCiclosCartera,
  getCiclosCatalogo,
  getCiclosComparacion,
  getCiclosCorrelaciones,
  getCiclosDesfases,
  getCiclosInstrumentos,
  getCiclosPanorama,
  getCicloPais,
  refrescarCiclos,
  type CicloAtajo,
  type CicloMoneda,
  type CicloPeriodo,
  type CicloTipo,
  type CiclosPanoramaOut,
} from '../api'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import Segmented from '../components/ui/Segmented'
import TituloSeccion from '../components/ui/TituloSeccion'
import BadgeCuadrante from '../components/ciclos/BadgeCuadrante'
import CambiosLiderazgo from '../components/ciclos/CambiosLiderazgo'
import ComparacionCiclos from '../components/ciclos/ComparacionCiclos'
import ExposicionCiclos from '../components/ciclos/ExposicionCiclos'
import FichaPais from '../components/ciclos/FichaPais'
import GraficoDesfases from '../components/ciclos/GraficoDesfases'
import GraficoRotacion from '../components/ciclos/GraficoRotacion'
import InstrumentosGrupo from '../components/ciclos/InstrumentosGrupo'
import LeyendaCuadrantes from '../components/ciclos/LeyendaCuadrantes'
import MapaCalorCiclos, { type ModoCalor } from '../components/ciclos/MapaCalorCiclos'
import MatrizCiclos from '../components/ciclos/MatrizCiclos'
import PanelGrupo from '../components/ciclos/PanelGrupo'
import PieDatos from '../components/ciclos/PieDatos'
import RegimenMacro from '../components/ciclos/RegimenMacro'
import SelectorGrupos from '../components/ciclos/SelectorGrupos'
import SimuladorRotacion from '../components/ciclos/SimuladorRotacion'
import TarjetaGrupo from '../components/ciclos/TarjetaGrupo'
import { TIPOS_ANALISIS, colorGrupo } from '../components/ciclos/constantes'
import InfoTooltip from '../help/components/InfoTooltip'
import { fechaCorta, fechaHora } from '../utils/fechas'

type Pestana = 'panorama' | 'sectores' | 'regiones' | 'relaciones' | 'cartera'

const PESTANAS: { value: Pestana; label: string }[] = [
  { value: 'panorama', label: 'Panorama' },
  { value: 'sectores', label: 'Sectores y activos' },
  { value: 'regiones', label: 'Regiones' },
  { value: 'relaciones', label: 'Relaciones' },
  { value: 'cartera', label: 'Mi cartera' },
]

const PERIODOS: { value: CicloPeriodo; label: string }[] = [
  { value: '3M', label: '3 meses' },
  { value: '6M', label: '6 meses' },
  { value: '1A', label: '1 año' },
  { value: '3A', label: '3 años' },
]

const TIPOS_SECTORES = TIPOS_ANALISIS.filter(t => ['sector', 'industria', 'commodity', 'activo', 'tema'].includes(t.value))
const TIPOS_REGIONES = TIPOS_ANALISIS.filter(t => ['region', 'pais'].includes(t.value))
const MESES_PAIS: { value: string; label: string }[] = [
  { value: '3', label: '3M' },
  { value: '6', label: '6M' },
  { value: '12', label: '1A' },
  { value: '36', label: '3A' },
]
const PERIODOS_CORR: { value: CicloPeriodo; label: string }[] = PERIODOS

/** Estado de «no hay datos»: la ingesta todavía no corrió o el benchmark no tiene serie. Ofrece pedir la descarga. */
function SinDatos({ motivo }: { motivo: string | null }) {
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: refrescarCiclos,
    onSuccess: () => {
      // La descarga corre en segundo plano y tarda minutos la primera vez: se refresca lo ya cargado al volver.
      window.setTimeout(() => void qc.invalidateQueries({ predicate: q => String(q.queryKey[0]).startsWith('ciclos') }), 4000)
    },
  })
  return (
    <EmptyState
      ilustracion="lupa"
      emoji="🔭"
      title="Todavía no hay datos de mercado"
      description={
        (motivo ? `${motivo}. ` : '') +
        'Las series se bajan solas de lunes a viernes después del cierre. También podés pedir la descarga ahora: la primera vez tarda unos minutos.'
      }
      action={
        m.isSuccess ? (
          <p className="text-caption text-app-text-dim">Descarga iniciada. Volvé a mirar en unos minutos.</p>
        ) : (
          <Button onClick={() => m.mutate()} loading={m.isPending}>
            Descargar datos ahora
          </Button>
        )
      }
    />
  )
}

function Encabezado({ data }: { data: CiclosPanoramaOut }) {
  const m = data.meta
  return (
    <p className="text-label text-app-text-faint">
      Datos al {m.ultima_fecha_datos ? fechaCorta(m.ultima_fecha_datos) : '—'}
      {m.ultima_actualizacion ? ` · descargados ${fechaHora(m.ultima_actualizacion)}` : ''}
      {m.benchmark ? ` · referencia: ${m.benchmark.nombre}` : ''}
    </p>
  )
}

export default function CiclosMercado() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const pestana = (PESTANAS.some(p => p.value === params.get('tab')) ? params.get('tab') : 'panorama') as Pestana
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()
  const moneda: CicloMoneda = monedaSeleccionada

  const [periodo, setPeriodo] = useState<CicloPeriodo>('6M')
  const [benchmark, setBenchmark] = useState<string | null>(null)
  const [tipoPanorama, setTipoPanorama] = useState<CicloTipo>('sector')
  const [tipoSectores, setTipoSectores] = useState<CicloTipo>('sector')
  const [tipoRegiones, setTipoRegiones] = useState<CicloTipo>('region')
  const [ocultos, setOcultos] = useState<Set<string>>(new Set())
  const [modoCalor, setModoCalor] = useState<ModoCalor>('absoluto')
  const [seleccionado, setSeleccionado] = useState<string | null>(null)

  const tipoActivo: CicloTipo = pestana === 'sectores' ? tipoSectores : pestana === 'regiones' ? tipoRegiones : tipoPanorama
  const usaPanorama = pestana === 'panorama' || pestana === 'sectores' || pestana === 'regiones'

  const catalogo = useQuery({ queryKey: qk.de('ciclos-catalogo'), queryFn: getCiclosCatalogo })
  const panorama = useQuery({
    queryKey: qk.de('ciclos-panorama', tipoActivo, periodo, moneda, benchmark),
    queryFn: () => getCiclosPanorama({ tipo: tipoActivo, periodo, moneda, benchmark }),
    enabled: usaPanorama,
  })
  const data = panorama.data
  const grupos = data?.grupos ?? []
  const nombres = useMemo(() => new Map((catalogo.data?.grupos ?? []).map(g => [g.id, g.nombre])), [catalogo.data])
  const colores = useMemo(() => Object.fromEntries(grupos.map((g, i) => [g.id, colorGrupo(i)])), [grupos])
  const visibles = useMemo(() => grupos.filter(g => !ocultos.has(g.id)), [grupos, ocultos])
  const grupoSel = grupos.find(g => g.id === seleccionado) ?? null

  const irADetalle = (id: string) => navigate(`/ciclos/grupo/${id}`)
  const cambiarTab = (t: Pestana) => setParams(t === 'panorama' ? {} : { tab: t }, { replace: true })
  const alternar = (id: string) =>
    setOcultos(prev => {
      const n = new Set(prev)
      if (!n.delete(id)) n.add(id)
      return n
    })

  const filtros = data && (
    <div className="flex flex-col gap-2 mb-4">
      <Segmented options={PERIODOS} value={periodo} onChange={setPeriodo} />
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-label font-bold uppercase text-app-text-faint mr-1">
          <InfoTooltip term="ciclos_benchmark" label="Referencia" />
        </span>
        {data.opciones.benchmarks.map(b => (
          <button
            key={b.id}
            type="button"
            onClick={() => setBenchmark(b.id)}
            className={`px-2.5 py-1.5 rounded-lg text-caption font-semibold whitespace-nowrap active:scale-95 ${
              data.filtros.benchmark === b.id ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface border border-app-border text-app-text-dim'
            }`}
          >
            {b.nombre}
          </button>
        ))}
        <span className="ml-auto text-label text-app-text-faint">
          Moneda: {moneda} <InfoTooltip term="ciclos_moneda" />
        </span>
      </div>
    </div>
  )

  const listaDeGrupos = (
    <ul className="flex flex-col gap-2">
      {[...grupos]
        .sort((a, b) => (a.padre ?? '').localeCompare(b.padre ?? '') || a.nombre.localeCompare(b.nombre, 'es-AR'))
        .map(g => (
          <li key={g.id}>
            <TarjetaGrupo g={g} padre={g.padre ? nombres.get(g.padre) : null} onClick={() => irADetalle(g.id)} />
          </li>
        ))}
    </ul>
  )

  return (
    <div className="pb-4">
      <ScreenHeader title="Ciclos de mercado" />
      <div className="mb-3">
        <Segmented options={PESTANAS} value={pestana} onChange={cambiarTab} />
      </div>

      {usaPanorama && (
        <QueryBoundary isLoading={panorama.isLoading} error={panorama.error} onRetry={() => void panorama.refetch()}>
          {!data ? null : data.motivo || data.cobertura.total === 0 ? (
            <SinDatos motivo={data.motivo} />
          ) : (
            <>
              {pestana === 'panorama' && (
                <div className="flex flex-col gap-5">
                  <Card>
                    <div className="flex items-start gap-2">
                      <div className="text-caption text-app-text-dim">
                        <span className="font-semibold text-app-text">Esto describe lo que ya pasó.</span> Muestra qué grupos vienen rindiendo mejor o peor que su
                        referencia y si esa diferencia crece o se achica. No es una recomendación de comprar ni de vender.
                      </div>
                    </div>
                  </Card>
                  <Segmented options={TIPOS_ANALISIS} value={tipoPanorama} onChange={t => { setTipoPanorama(t); setOcultos(new Set()) }} />
                  {filtros}
                  <Encabezado data={data} />
                  <RegimenMacro regimen={data.regimen} />

                  <section>
                    <TituloSeccion icono="swap" tono="accent">
                      <InfoTooltip term="ciclos_rotacion" label="Mapa de rotación relativa" />
                    </TituloSeccion>
                    <Card className="!p-2">
                      <GraficoRotacion grupos={grupos} ocultos={ocultos} seleccionado={seleccionado} onSeleccionar={setSeleccionado} colores={colores} />
                    </Card>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {grupos.map(g => (
                        <button
                          key={g.id}
                          type="button"
                          onClick={() => alternar(g.id)}
                          aria-pressed={!ocultos.has(g.id)}
                          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border text-label font-semibold active:scale-95 ${
                            ocultos.has(g.id) ? 'border-app-border text-app-text-faint opacity-60' : 'border-app-border-strong text-app-text'
                          }`}
                        >
                          <span aria-hidden="true" className="w-2 h-2 rounded-full" style={{ backgroundColor: colores[g.id] }} />
                          {g.proxy ?? g.nombre}
                        </button>
                      ))}
                      <button type="button" onClick={() => setOcultos(new Set())} className="px-2 py-1 text-label font-semibold text-app-accent">Mostrar todos</button>
                      <button type="button" onClick={() => setOcultos(new Set(grupos.map(g => g.id)))} className="px-2 py-1 text-label font-semibold text-app-text-dim">Ocultar todos</button>
                    </div>
                    <p className="text-label text-app-text-faint mt-1">
                      Tocá un punto para ver el detalle. La cola muestra las últimas {data.filtros.periodo === '3M' ? '13' : data.filtros.periodo === '6M' ? '26' : data.filtros.periodo === '1A' ? '52' : '156'} semanas (<InfoTooltip term="ciclos_trayectoria" label="trayectoria" />).
                      {visibles.length === 0 ? ' Todos los grupos están ocultos.' : ''}
                    </p>
                    <div className="mt-3">
                      <LeyendaCuadrantes />
                    </div>
                  </section>

                  <section>
                    <TituloSeccion icono="trend" tono="warn">
                      <InfoTooltip term="ciclos_cambio_confirmado" label="Cambios de liderazgo" />
                    </TituloSeccion>
                    <CambiosLiderazgo cambios={data.cambios_liderazgo} onSeleccionar={setSeleccionado} />
                  </section>

                  <section>
                    <TituloSeccion icono="grid" tono="cyan">
                      Mapa de calor de rendimientos
                    </TituloSeccion>
                    <Card>
                      <MapaCalorCiclos grupos={visibles} horizontes={data.horizontes} modo={modoCalor} onModo={setModoCalor} onSeleccionar={setSeleccionado} />
                    </Card>
                  </section>

                  {(data.cobertura.sin_datos.length > 0 || data.cobertura.insuficientes.length > 0 || data.cobertura.desactualizados.length > 0) && (
                    <Card>
                      <div className="text-label font-bold uppercase text-app-text-faint mb-1">Grupos que no se pudieron ubicar en el mapa</div>
                      <ul className="flex flex-col gap-1 text-caption text-app-text-dim">
                        {[...data.cobertura.sin_datos, ...data.cobertura.insuficientes, ...data.cobertura.desactualizados].map(c => (
                          <li key={c.id}>
                            <b className="text-app-text">{c.nombre}:</b> {c.motivo}
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}
                  <PieDatos meta={data.meta} />
                </div>
              )}

              {pestana === 'sectores' && (
                <div className="flex flex-col gap-4">
                  <Segmented options={TIPOS_SECTORES} value={tipoSectores} onChange={setTipoSectores} />
                  {filtros}
                  <Encabezado data={data} />
                  {tipoSectores === 'tema' && (
                    <Card>
                      <p className="text-caption text-app-text-dim">
                        No hay una clasificación temática de fuente externa: cada tema se mide con un ETF y se vincula a tu cartera con una regla más una{' '}
                        <InfoTooltip term="ciclos_lista_curada" label="lista curada" />.
                      </p>
                    </Card>
                  )}
                  {listaDeGrupos}
                  <PieDatos meta={data.meta} />
                </div>
              )}

              {pestana === 'regiones' && (
                <RegionesTab
                  data={data}
                  tipo={tipoRegiones}
                  onTipo={setTipoRegiones}
                  moneda={moneda}
                  benchmark={benchmark}
                  filtros={filtros}
                  lista={listaDeGrupos}
                  atajos={catalogo.data?.comparaciones ?? []}
                  grupos={grupos.map(g => g.id)}
                  nombres={nombres}
                  onDetalle={irADetalle}
                />
              )}
            </>
          )}
        </QueryBoundary>
      )}

      {pestana === 'relaciones' && <RelacionesTab moneda={moneda} />}
      {pestana === 'cartera' && <CarteraTab cartera={carteraSeleccionada} benchmark={benchmark} onDetalle={irADetalle} />}

      <PanelGrupo grupo={grupoSel} benchmarkNombre={data?.meta.benchmark?.nombre ?? null} onClose={() => setSeleccionado(null)} onVerDetalle={irADetalle} />
    </div>
  )
}

// ── Regiones ───────────────────────────────────────────────────────────────────────────────

function RegionesTab({
  data, tipo, onTipo, moneda, benchmark, filtros, lista, atajos, grupos, nombres, onDetalle,
}: {
  data: CiclosPanoramaOut
  tipo: CicloTipo
  onTipo: (t: CicloTipo) => void
  moneda: CicloMoneda
  benchmark: string | null
  filtros: ReactNode
  lista: ReactNode
  atajos: CicloAtajo[]
  grupos: string[]
  nombres: Map<string, string>
  onDetalle: (id: string) => void
}) {
  const [paisId, setPaisId] = useState('')
  const [meses, setMeses] = useState('12')
  const [atajo, setAtajo] = useState<CicloAtajo | null>(null)
  const pais = useQuery({
    queryKey: qk.de('ciclos-pais', paisId, meses, moneda, benchmark),
    queryFn: () => getCicloPais(paisId, { meses: Number(meses), moneda, benchmark }),
    enabled: paisId !== '',
  })
  const comp = useQuery({
    queryKey: qk.de('ciclos-comparacion', (atajo?.grupos ?? []).join(','), moneda, benchmark),
    queryFn: () => getCiclosComparacion({ ids: atajo?.grupos ?? [], moneda, benchmark: null }),
    enabled: atajo !== null,
  })
  return (
    <div className="flex flex-col gap-4">
      <Segmented options={TIPOS_REGIONES} value={tipo} onChange={onTipo} />
      {filtros}
      <Encabezado data={data} />

      <section>
        <TituloSeccion icono="swap" tono="accent">Comparaciones habituales</TituloSeccion>
        <div className="flex flex-wrap gap-1.5">
          {atajos.map(a => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAtajo(atajo?.id === a.id ? null : a)}
              className={`px-2.5 py-1.5 rounded-lg text-caption font-semibold active:scale-95 ${atajo?.id === a.id ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface border border-app-border text-app-text-dim'}`}
            >
              {a.nombre}
            </button>
          ))}
        </div>
        {atajo && (
          <Card className="mt-2">
            <QueryBoundary isLoading={comp.isLoading} error={comp.error} onRetry={() => void comp.refetch()}>
              {comp.data && (comp.data.estado === 'ok' ? <ComparacionCiclos data={comp.data} /> : <p className="text-caption text-app-text-dim">{comp.data.motivo}</p>)}
            </QueryBoundary>
            {comp.data && <div className="mt-2"><PieDatos meta={comp.data.meta} /></div>}
          </Card>
        )}
      </section>

      <section>
        <TituloSeccion icono="pie" tono="cyan">{tipo === 'pais' ? 'Países' : 'Regiones'}</TituloSeccion>
        <div className="flex flex-col gap-2">{lista}</div>
        <div className="mt-3 flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-label font-bold uppercase text-app-text-faint">
            Ver la ficha de un país o región
            <select
              value={paisId}
              onChange={e => setPaisId(e.target.value)}
              className="h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text normal-case font-normal"
            >
              <option value="">Elegí uno…</option>
              {grupos.map(id => (
                <option key={id} value={id}>{nombres.get(id) ?? id}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {paisId !== '' && (
        <section>
          <TituloSeccion icono="info" tono="violet">Ficha: {nombres.get(paisId) ?? paisId}</TituloSeccion>
          <Segmented options={MESES_PAIS} value={meses} onChange={setMeses} />
          <Card className="mt-2">
            <QueryBoundary isLoading={pais.isLoading} error={pais.error} onRetry={() => void pais.refetch()}>
              {pais.data &&
                (pais.data.estado === 'sin_datos' ? (
                  <p className="text-caption text-app-text-dim">{pais.data.motivo}</p>
                ) : (
                  <FichaPais data={pais.data} onComparar={setAtajo} />
                ))}
            </QueryBoundary>
          </Card>
          {pais.data && <div className="mt-2"><PieDatos meta={pais.data.meta} /></div>}
          <button type="button" onClick={() => onDetalle(paisId)} className="mt-2 text-caption font-semibold text-app-accent">Ver la ficha completa del grupo ›</button>
        </section>
      )}
    </div>
  )
}

// ── Relaciones ─────────────────────────────────────────────────────────────────────────────

function RelacionesTab({ moneda }: { moneda: CicloMoneda }) {
  const catalogo = useQuery({ queryKey: qk.de('ciclos-catalogo'), queryFn: getCiclosCatalogo })
  const grupos = catalogo.data?.grupos ?? []
  const [periodo, setPeriodo] = useState<CicloPeriodo>('1A')
  const [ids, setIds] = useState<string[]>([])
  const [compIds, setCompIds] = useState<string[]>([])
  const [periodoId, setPeriodoId] = useState('')
  const [par, setPar] = useState('')

  const etiquetas = useMemo(() => Object.fromEntries(grupos.map(g => [g.id, g.proxy ?? g.nombre])), [grupos])
  const corr = useQuery({
    queryKey: qk.de('ciclos-correlaciones', ids.join(','), periodo),
    queryFn: () => getCiclosCorrelaciones({ ids, periodo }),
    enabled: ids.length === 0 || ids.length >= 2,
  })
  const comp = useQuery({
    queryKey: qk.de('ciclos-comparacion-rel', compIds.join(','), moneda, periodoId),
    queryFn: () => getCiclosComparacion({ ids: compIds, moneda, periodo_id: periodoId || null }),
    enabled: compIds.length >= 2,
  })
  const pares = catalogo.data?.pares_desfase ?? []
  const parSel = pares.find(p => p.id === par)
  const desf = useQuery({
    queryKey: qk.de('ciclos-desfases', parSel?.grupos.join(',') ?? ''),
    queryFn: () => getCiclosDesfases({ a: parSel!.grupos[0], b: parSel!.grupos[1] }),
    enabled: !!parSel,
  })

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <p className="text-caption text-app-text-dim">
          <span className="font-semibold text-app-text">Relaciones, no causas.</span> Acá se ve qué grupos se movieron juntos o distinto. Que dos series se parezcan no
          explica por qué, ni asegura que vuelvan a hacerlo.
        </p>
      </Card>

      <section>
        <TituloSeccion icono="grid" tono="accent"><InfoTooltip term="ciclos_correlacion" label="Matriz de correlaciones" /></TituloSeccion>
        <div className="flex flex-col gap-2">
          <Segmented options={PERIODOS_CORR} value={periodo} onChange={setPeriodo} />
          <SelectorGrupos grupos={grupos} seleccion={ids} onChange={setIds} max={15} placeholder="Elegir grupos (vacío = selección habitual)…" />
          {ids.length === 1 && <p className="text-label text-app-warn">Elegí al menos 2 grupos.</p>}
          <QueryBoundary isLoading={corr.isLoading} error={corr.error} onRetry={() => void corr.refetch()}>
            {corr.data &&
              (corr.data.estado === 'ok' ? (
                <>
                  <MatrizCiclos data={corr.data} etiquetas={etiquetas} />
                  <PieDatos meta={corr.data.meta} />
                </>
              ) : (
                <EmptyState ilustracion="lupa" emoji="🔭" title="Sin datos suficientes" description={corr.data.motivo ?? 'No hay series para calcular correlaciones.'} />
              ))}
          </QueryBoundary>
        </div>
      </section>

      <section>
        <TituloSeccion icono="trend" tono="cyan">Comparación histórica</TituloSeccion>
        <div className="flex flex-col gap-2">
          <SelectorGrupos grupos={grupos} seleccion={compIds} onChange={setCompIds} max={6} placeholder="Elegir 2 a 6 grupos…" />
          <select
            aria-label="Período histórico"
            value={periodoId}
            onChange={e => setPeriodoId(e.target.value)}
            className="h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text"
          >
            <option value="">Últimos 3 años</option>
            {(catalogo.data?.periodos ?? []).map(p => (
              <option key={p.id} value={p.id}>{p.nombre} ({fechaCorta(p.desde)} → {p.hasta ? fechaCorta(p.hasta) : 'hoy'})</option>
            ))}
          </select>
          {compIds.length < 2 ? (
            <p className="text-caption text-app-text-faint">Elegí al menos dos grupos para comparar su rendimiento, volatilidad, caídas y recuperación en el mismo período.</p>
          ) : (
            <QueryBoundary isLoading={comp.isLoading} error={comp.error} onRetry={() => void comp.refetch()}>
              {comp.data &&
                (comp.data.estado === 'ok' ? (
                  <>
                    <Card><ComparacionCiclos data={comp.data} /></Card>
                    <PieDatos meta={comp.data.meta} />
                  </>
                ) : (
                  <p className="text-caption text-app-text-dim">{comp.data.motivo}</p>
                ))}
            </QueryBoundary>
          )}
        </div>
      </section>

      <section>
        <TituloSeccion icono="swap" tono="warn"><InfoTooltip term="ciclos_desfase" label="Adelantos y rezagos" /></TituloSeccion>
        <div className="flex flex-col gap-2">
          <select
            aria-label="Par a investigar"
            value={par}
            onChange={e => setPar(e.target.value)}
            className="h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text"
          >
            <option value="">Elegí un par para investigar…</option>
            {pares.map(p => (
              <option key={p.id} value={p.id}>{p.nombre}</option>
            ))}
          </select>
          {parSel?.nota && <p className="text-label text-app-text-faint">{parSel.nota}</p>}
          {parSel && (
            <QueryBoundary isLoading={desf.isLoading} error={desf.error} onRetry={() => void desf.refetch()}>
              {desf.data &&
                (desf.data.estado === 'ok' ? (
                  <>
                    <Card><GraficoDesfases data={desf.data} /></Card>
                    <PieDatos meta={desf.data.meta} />
                  </>
                ) : (
                  <p className="text-caption text-app-text-dim">{desf.data.motivo}</p>
                ))}
            </QueryBoundary>
          )}
          <p className="text-label text-app-text-faint">«Tasas de interés y sectores sensibles al crédito» no está disponible: la app no tiene series de tasas.</p>
        </div>
      </section>
    </div>
  )
}

// ── Mi cartera ─────────────────────────────────────────────────────────────────────────────

function CarteraTab({ cartera, benchmark, onDetalle }: { cartera: string | null; benchmark: string | null; onDetalle: (id: string) => void }) {
  const catalogo = useQuery({ queryKey: qk.de('ciclos-catalogo'), queryFn: getCiclosCatalogo })
  const exp = useQuery({ queryKey: qk.de('ciclos-cartera', cartera, benchmark), queryFn: () => getCiclosCartera(cartera, benchmark) })
  const [grupo, setGrupo] = useState<string | null>(null)
  const inst = useQuery({
    queryKey: qk.de('ciclos-instrumentos', cartera, grupo, benchmark),
    queryFn: () => getCiclosInstrumentos(cartera, grupo!, benchmark),
    enabled: grupo !== null,
  })
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <p className="text-caption text-app-text-dim">
          <span className="font-semibold text-app-text">Dónde está tu capital hoy.</span> Cruza tus posiciones con el estado actual de cada grupo. Es una descripción, no una
          recomendación: un grupo en Weakening o Lagging no significa que convenga reducirlo.
        </p>
      </Card>
      <QueryBoundary isLoading={exp.isLoading} error={exp.error} onRetry={() => void exp.refetch()}>
        {exp.data && exp.data.total_usd <= 0 ? (
          <EmptyState ilustracion="planta" emoji="🌱" title="Sin posiciones valuadas" description="Esta cartera todavía no tiene posiciones para cruzar con los ciclos." />
        ) : (
          exp.data && (
            <>
              <section>
                <TituloSeccion icono="pie" tono="accent">Capital por estado del ciclo</TituloSeccion>
                <ExposicionCiclos data={exp.data} onSeleccionarGrupo={setGrupo} />
              </section>

              {grupo && (
                <section>
                  <TituloSeccion icono="wallet" tono="pos">
                    {catalogo.data?.grupos.find(g => g.id === grupo)?.nombre ?? grupo}
                  </TituloSeccion>
                  <Card>
                    <QueryBoundary isLoading={inst.isLoading} error={inst.error} onRetry={() => void inst.refetch()}>
                      {inst.data && <InstrumentosGrupo data={inst.data} />}
                    </QueryBoundary>
                    <div className="flex gap-3 mt-3">
                      <button type="button" onClick={() => onDetalle(grupo)} className="text-caption font-semibold text-app-accent">Ver la ficha del grupo ›</button>
                      <button type="button" onClick={() => setGrupo(null)} className="text-caption font-semibold text-app-text-dim">Cerrar</button>
                    </div>
                  </Card>
                </section>
              )}

              <section>
                <TituloSeccion icono="swap" tono="warn">Simulador de rotación</TituloSeccion>
                <Card>
                  <SimuladorRotacion cartera={cartera} exposicion={exp.data} grupos={catalogo.data?.grupos ?? []} benchmark={benchmark} inicial={{ origen: grupo ?? undefined }} />
                </Card>
              </section>
            </>
          )
        )}
      </QueryBoundary>
    </div>
  )
}
