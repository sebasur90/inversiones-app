import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import { Icon } from '../components/icons/Icons'
import { HELP, type HelpKey } from '../help/content/index'
import { ContenidoTermino, InfoTooltipLink } from '../help/components/InfoTooltip'
import { TUTORIALES } from '../help/content/tutoriales'
import { FAQ } from '../help/content/faq'
import { normalizarTexto } from '../utils/texto'

type Vista = 'tutoriales' | 'glosario' | 'faq' | 'tour'

const OPCIONES_VISTA: { value: Vista; label: string }[] = [
  { value: 'tutoriales', label: 'Tutoriales' },
  { value: 'glosario', label: 'Glosario' },
  { value: 'faq', label: 'Preguntas' },
  { value: 'tour', label: 'Tour' },
]

const MAX_RESULTADOS_GLOSARIO = 30

function SeccionTutoriales() {
  const navigate = useNavigate()
  const [abiertoId, setAbiertoId] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-2.5">
      {TUTORIALES.map(tutorial => {
        const abierto = abiertoId === tutorial.id
        return (
          <Card key={tutorial.id} className="!p-0 overflow-hidden">
            <button
              type="button"
              onClick={() => setAbiertoId(abierto ? null : tutorial.id)}
              aria-expanded={abierto}
              className="w-full flex items-center gap-3 text-left px-3.5 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="text-body font-semibold text-app-text">{tutorial.titulo}</div>
                <div className="text-caption text-app-text-dim">{tutorial.resumen}</div>
              </div>
              <Icon
                name="chevron"
                className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierto ? 'rotate-0' : '-rotate-90'}`}
              />
            </button>

            {abierto && (
              <div className="px-3.5 pb-3.5 flex flex-col gap-3 border-t border-app-border pt-3">
                {tutorial.pasos.map((paso, i) => (
                  <div key={i} className="flex gap-2.5">
                    <div className="w-5 h-5 rounded-full bg-app-accent-soft text-app-accent text-label font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {i + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-caption font-semibold text-app-text">{paso.titulo}</div>
                      <div className="text-caption text-app-text-dim mt-0.5 leading-relaxed">{paso.detalle}</div>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {paso.ruta && (
                          <button
                            onClick={() => navigate(paso.ruta as string)}
                            className="text-xs px-2 py-1 rounded-md bg-app-accent-soft text-app-accent font-semibold"
                          >
                            Ir ahí →
                          </button>
                        )}
                        {paso.termino && HELP[paso.termino] && (
                          <InfoTooltipLink term={paso.termino} title={HELP[paso.termino].title} />
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}

function SeccionGlosario() {
  const [consulta, setConsulta] = useState('')
  const [terminoAbierto, setTerminoAbierto] = useState<HelpKey | null>(null)

  const q = normalizarTexto(consulta.trim())
  const todasLasClaves = useMemo(() => Object.keys(HELP) as HelpKey[], [])

  const resultados = useMemo(() => {
    const claves = q
      ? todasLasClaves.filter(
          k => normalizarTexto(HELP[k].title).includes(q) || normalizarTexto(HELP[k].shortDescription).includes(q),
        )
      : [...todasLasClaves].sort((a, b) => HELP[a].title.localeCompare(HELP[b].title))
    return claves.slice(0, MAX_RESULTADOS_GLOSARIO)
  }, [q, todasLasClaves])

  return (
    <div>
      <div className="flex items-center gap-2 bg-app-surface border border-app-border rounded-xl h-10 px-3 mb-3">
        <Icon name="search" className="w-4 h-4 text-app-text-faint" />
        <input
          value={consulta}
          onChange={e => setConsulta(e.target.value)}
          placeholder={`Buscar en ${todasLasClaves.length} términos…`}
          aria-label="Buscar en el glosario"
          className="flex-1 bg-transparent outline-none text-caption text-app-text placeholder:text-app-text-faint"
        />
      </div>

      {resultados.length === 0 ? (
        <EmptyState title="Nada coincide" description="Probá con otra palabra." />
      ) : (
        <div className="flex flex-col gap-1">
          {resultados.map(k => (
            <button
              key={k}
              onClick={() => setTerminoAbierto(k)}
              className="flex items-center gap-3 text-left px-3 py-2.5 rounded-xl bg-app-surface-2 border border-app-border"
            >
              <div className="min-w-0 flex-1">
                <div className="text-body font-semibold text-app-text truncate">{HELP[k].title}</div>
                <div className="text-caption text-app-text-dim truncate">{HELP[k].shortDescription}</div>
              </div>
              <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />
            </button>
          ))}
          {q === '' && todasLasClaves.length > MAX_RESULTADOS_GLOSARIO && (
            <div className="text-label text-app-text-faint text-center py-2">
              Mostrando los primeros {MAX_RESULTADOS_GLOSARIO}. Buscá por nombre para encontrar el resto.
            </div>
          )}
        </div>
      )}

      {terminoAbierto && (
        <Modal open onClose={() => setTerminoAbierto(null)} title={HELP[terminoAbierto].title}>
          <ContenidoTermino entry={HELP[terminoAbierto]} />
        </Modal>
      )}
    </div>
  )
}

function SeccionFaq() {
  const [abiertaIdx, setAbiertaIdx] = useState<number | null>(null)

  return (
    <div className="flex flex-col gap-2">
      {FAQ.map((item, i) => {
        const abierta = abiertaIdx === i
        return (
          <Card key={i} className="!p-0 overflow-hidden">
            <button
              type="button"
              onClick={() => setAbiertaIdx(abierta ? null : i)}
              aria-expanded={abierta}
              className="w-full flex items-center gap-3 text-left px-3.5 py-3"
            >
              <div className="flex-1 text-caption font-semibold text-app-text">{item.pregunta}</div>
              <Icon
                name="chevron"
                className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`}
              />
            </button>
            {abierta && (
              <div className="px-3.5 pb-3.5 border-t border-app-border pt-2.5">
                <p className="text-caption text-app-text-dim leading-relaxed">{item.respuesta}</p>
                {item.termino && HELP[item.termino] && (
                  <div className="mt-2">
                    <InfoTooltipLink term={item.termino} title={HELP[item.termino].title} />
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}

function SeccionTour() {
  const { abrirTour } = useInversionesContext()
  return (
    <Card className="text-center py-8">
      <div className="text-metric-lg mb-2" aria-hidden="true">🎓</div>
      <div className="text-body font-semibold text-app-text mb-1">Tour de bienvenida</div>
      <p className="text-caption text-app-text-dim mb-4 max-w-[260px] mx-auto">
        Un repaso de 30 segundos: qué es la app, dónde está cada cosa y cómo pedir ayuda cuando algo no se entiende.
      </p>
      <Button onClick={abrirTour} className="mx-auto">Ver el tour otra vez</Button>
    </Card>
  )
}

export default function Ayuda() {
  const navigate = useNavigate()
  const [vista, setVista] = useState<Vista>('tutoriales')

  return (
    <div className="pb-4">
      <ScreenHeader title="Centro de ayuda" onBack={() => navigate(-1)} />

      <div className="mb-3.5">
        <Segmented options={OPCIONES_VISTA} value={vista} onChange={setVista} />
      </div>

      {vista === 'tutoriales' && <SeccionTutoriales />}
      {vista === 'glosario' && <SeccionGlosario />}
      {vista === 'faq' && <SeccionFaq />}
      {vista === 'tour' && <SeccionTour />}
    </div>
  )
}
