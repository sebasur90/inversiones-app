import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Icon } from '../../components/icons/Icons'
import { InfoTooltipLink } from './InfoTooltip'
import { HELP, type HelpKey } from '../content/index'
import { claveRutaGuia, resolverGuia } from '../content/guias'
import { usePreferenciaBooleana, CLAVE_MODO_GUIADO, PREFIJO_GUIA_COLAPSADA } from '../../hooks/usePreferencia'

/**
 * Banner "💡 Cómo leer esta pantalla" bajo el header. Se resuelve por ruta (`resolverGuia`), así
 * que vive una sola vez en `ScreenHeader` y no hay que tocar las 28 pantallas para tenerlo.
 *
 * Estado de apertura: `colapsadaGuardada` persiste por ruta (para siempre, hasta que se reabra a
 * mano). El interruptor global "Modo guiado" (Ajustes) sólo cambia el *default* — con el modo
 * apagado la guía arranca colapsada en todos lados — pero tocar la barra igual la abre para esa
 * visita (`abiertaSesion`, sin persistir) para no dejar a nadie sin poder consultarla.
 */
export default function GuiaPantalla() {
  const location = useLocation()
  const guia = resolverGuia(location.pathname)
  const clave = `${PREFIJO_GUIA_COLAPSADA}${claveRutaGuia(location.pathname)}`

  const [modoGuiado] = usePreferenciaBooleana(CLAVE_MODO_GUIADO, true)
  const [colapsadaGuardada, setColapsadaGuardada] = usePreferenciaBooleana(clave, false)
  const [abiertaSesion, setAbiertaSesion] = useState<boolean | null>(null)

  if (!guia) return null

  const abiertaPorDefecto = modoGuiado && !colapsadaGuardada
  const abierta = abiertaSesion ?? abiertaPorDefecto

  function toggle() {
    const nuevaAbierta = !abierta
    setAbiertaSesion(nuevaAbierta)
    // Sólo se persiste con el modo guiado prendido: si está apagado, abrir una guía puntual no
    // debe "filtrarse" y quedar abierta después cuando alguien vuelva a prenderlo.
    if (modoGuiado) setColapsadaGuardada(!nuevaAbierta)
  }

  const terminos = (guia.terminos ?? []).filter((t): t is HelpKey => t in HELP)

  return (
    <div className="mb-3.5 bg-app-accent-soft/40 border border-app-accent/20 rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={abierta}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left"
      >
        <span className="text-body shrink-0" aria-hidden="true">💡</span>
        <span className="flex-1 text-caption font-semibold text-app-text">Cómo leer esta pantalla</span>
        <Icon
          name="chevron"
          className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`}
        />
      </button>

      {abierta && (
        <div className="px-3.5 pb-3.5 text-caption text-app-text-dim leading-relaxed">
          <p className="text-app-text font-medium mb-2">{guia.queEs}</p>

          <ul className="list-disc pl-4 space-y-1 mb-2">
            {guia.comoLeerla.map((linea, i) => (
              <li key={i}>{linea}</li>
            ))}
          </ul>

          {guia.queHacer && guia.queHacer.length > 0 && (
            <ul className="list-disc pl-4 space-y-1 mb-2 marker:text-app-pos">
              {guia.queHacer.map((linea, i) => (
                <li key={i} className="text-app-text">{linea}</li>
              ))}
            </ul>
          )}

          {guia.ojo && (
            <div className="flex items-start gap-1.5 mt-2 p-2.5 bg-app-surface rounded-[9px] border border-app-border">
              <Icon name="alert" className="w-3.5 h-3.5 text-app-accent shrink-0 mt-0.5" />
              <p>{guia.ojo}</p>
            </div>
          )}

          {terminos.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {terminos.map(term => (
                <InfoTooltipLink key={term} term={term} title={HELP[term].title} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
