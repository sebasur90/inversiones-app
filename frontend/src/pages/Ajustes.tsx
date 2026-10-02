import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import Button from '../components/ui/Button'
import {
  usePreferenciaNumerica,
  usePreferenciaBooleana,
  guardarPreferencia,
  limpiarGuiasColapsadas,
  CLAVE_AUTOSYNC_HORAS,
  CLAVE_ESCALA_TEXTO,
  CLAVE_CARTERA,
  CLAVE_MONEDA,
  CLAVE_UMBRAL_PROXIMIDAD,
  CLAVE_MODO_GUIADO,
  CLAVE_MONTOS_OCULTOS,
  UMBRAL_PROXIMIDAD_DEFAULT,
  AUTOSYNC_HORAS_DEFAULT,
  AUTOSYNC_HORAS_MAX,
  ESCALA_TEXTO_DEFAULT,
  ESCALA_TEXTO_MIN,
  ESCALA_TEXTO_MAX,
} from '../hooks/usePreferencia'
import { aplicarEscalaTexto } from '../utils/escalaTexto'
import { calcularFrescura } from '../utils/frescura'
import { setMontosOcultos, useMontosOcultos } from '../utils/privacidad'
import { purgarCacheApi } from '../utils/purgarCacheApi'
import InfoTooltip from '../help/components/InfoTooltip'

const OPCIONES_AUTOSYNC: { value: string; label: string }[] = [
  { value: '0', label: 'Nunca' },
  { value: '6', label: '6 h' },
  { value: '12', label: '12 h' },
  { value: '24', label: '24 h' },
]

const OPCIONES_PROXIMIDAD: { value: string; label: string }[] = [
  { value: '0', label: 'Desactivado' },
  { value: '3', label: '3 %' },
  { value: '5', label: '5 %' },
  { value: '10', label: '10 %' },
]

const OPCIONES_ESCALA: { value: string; label: string }[] = [
  { value: '1', label: 'Normal' },
  { value: '1.15', label: 'Grande' },
  { value: '1.3', label: 'Muy grande' },
]

const OPCIONES_MODO_GUIADO: { value: string; label: string }[] = [
  { value: '1', label: 'Activado' },
  { value: '0', label: 'Desactivado' },
]

const OPCIONES_PRIVACIDAD: { value: string; label: string }[] = [
  { value: '1', label: 'Activado' },
  { value: '0', label: 'Desactivado' },
]

function Seccion({ titulo, ayuda, children }: { titulo: ReactNode; ayuda: string; children: ReactNode }) {
  return (
    <Card className="mb-3">
      <div className="text-body font-semibold text-app-text mb-0.5">{titulo}</div>
      <div className="text-caption text-app-text-dim mb-2.5">{ayuda}</div>
      {children}
    </Card>
  )
}

export default function Ajustes() {
  const navigate = useNavigate()
  const { monedaSeleccionada, setMonedaSeleccionada, umbralProximidadPct, setUmbralProximidadPct, ultimoSync, showToast, abrirTour } =
    useInversionesContext()

  const [autoSyncHoras, setAutoSyncHoras] = usePreferenciaNumerica(
    CLAVE_AUTOSYNC_HORAS, AUTOSYNC_HORAS_DEFAULT, 0, AUTOSYNC_HORAS_MAX,
  )
  const [escalaTexto, setEscalaTexto] = usePreferenciaNumerica(
    CLAVE_ESCALA_TEXTO, ESCALA_TEXTO_DEFAULT, ESCALA_TEXTO_MIN, ESCALA_TEXTO_MAX,
  )
  const [modoGuiado, setModoGuiado] = usePreferenciaBooleana(CLAVE_MODO_GUIADO, true)
  // El modo privacidad no usa `usePreferenciaBooleana`: vive en un store propio para que el ojo
  // del encabezado y este interruptor queden siempre sincronizados. Ver `utils/privacidad.ts`.
  const montosOcultos = useMontosOcultos()

  function cambiarEscala(valor: number) {
    setEscalaTexto(valor)
    aplicarEscalaTexto(valor)
  }

  // Deliberadamente fuera de `restablecer()`: borrar datos del dispositivo es destructivo de otra
  // forma que volver las preferencias a su valor original.
  async function borrarCacheOffline() {
    const borrados = await purgarCacheApi()
    showToast(
      borrados === null
        ? 'Este navegador no guarda datos para uso offline.'
        : borrados === 0
          ? 'No había datos guardados en este dispositivo.'
          : 'Se borraron los datos guardados en este dispositivo.',
    )
  }

  function restablecer() {
    for (const clave of [CLAVE_AUTOSYNC_HORAS, CLAVE_ESCALA_TEXTO, CLAVE_CARTERA, CLAVE_MONEDA, CLAVE_UMBRAL_PROXIMIDAD, CLAVE_MODO_GUIADO, CLAVE_MONTOS_OCULTOS]) {
      guardarPreferencia(clave, null)
    }
    limpiarGuiasColapsadas()
    setAutoSyncHoras(AUTOSYNC_HORAS_DEFAULT)
    cambiarEscala(ESCALA_TEXTO_DEFAULT)
    setMonedaSeleccionada('USD')
    setUmbralProximidadPct(UMBRAL_PROXIMIDAD_DEFAULT)
    setModoGuiado(true)
    // Además de borrar la clave: el store guarda el flag en memoria, y sin esto los importes
    // seguirían tapados hasta recargar la app.
    setMontosOcultos(false)
    showToast('Preferencias restablecidas.')
  }

  const frescura = calcularFrescura(ultimoSync)

  return (
    <div className="pb-4">
      <ScreenHeader title="Ajustes" onBack={() => navigate('/mas')} />

      <Seccion titulo="Moneda" ayuda="En qué moneda se muestran los importes en toda la app.">
        <Segmented
          options={[
            { value: 'USD', label: 'USD' },
            { value: 'ARS', label: 'ARS' },
          ]}
          value={monedaSeleccionada}
          onChange={v => setMonedaSeleccionada(v as 'USD' | 'ARS')}
        />
      </Seccion>

      <Seccion
        titulo={<InfoTooltip term="modoPrivacidad" label="Privacidad" />}
        ayuda="Con el modo privacidad los importes de tu cartera se reemplazan por ••••. Los rendimientos en %, las cantidades de nominales y las cotizaciones de mercado siguen a la vista."
      >
        <Segmented
          options={OPCIONES_PRIVACIDAD}
          value={montosOcultos ? '1' : '0'}
          onChange={v => setMontosOcultos(v === '1')}
        />
        <div className="text-caption text-app-text-dim mt-2">
          También lo activás con el ojo del encabezado, desde cualquier pantalla. No alcanza para
          una captura de pantalla ni para un CSV exportado.
        </div>
        <div className="text-caption text-app-text-dim mt-3 mb-2">
          La app guarda las últimas respuestas del servidor en este dispositivo para poder abrir sin
          conexión. Si lo borrás, la próxima vez que abras sin red no vas a ver datos hasta
          sincronizar.
        </div>
        <Button variant="outline" onClick={borrarCacheOffline}>
          Borrar datos guardados para uso offline
        </Button>
      </Seccion>

      <Seccion
        titulo="Sincronización automática"
        ayuda="Al abrir la app, si los datos son más viejos que este umbral se sincroniza con el Sheet."
      >
        <Segmented
          options={OPCIONES_AUTOSYNC}
          value={String(autoSyncHoras)}
          onChange={v => setAutoSyncHoras(Number(v))}
        />
        <div className="text-caption text-app-text-dim mt-2">
          Último sync: {frescura.etiqueta}.
        </div>
      </Seccion>

      <Seccion
        titulo="Alertas de precio"
        ayuda="A qué distancia del stop-loss o del precio objetivo una posición empieza a avisar. Los niveles de cada ticker se cargan desde la pestaña Instrumentos del Sheet; esto sólo cambia cuándo aparece el aviso previo."
      >
        <Segmented
          options={OPCIONES_PROXIMIDAD}
          value={String(umbralProximidadPct)}
          onChange={v => setUmbralProximidadPct(Number(v))}
        />
        <div className="text-caption text-app-text-dim mt-2">
          {umbralProximidadPct === 0
            ? 'Sólo se avisa cuando el precio ya cruzó el nivel.'
            : `Se avisa desde ${umbralProximidadPct}% antes de cruzar el nivel, y siempre al cruzarlo.`}
        </div>
      </Seccion>

      <Seccion titulo="Tamaño de texto" ayuda="Escala toda la tipografía de la app.">
        <Segmented
          options={OPCIONES_ESCALA}
          value={String(escalaTexto)}
          onChange={v => cambiarEscala(Number(v))}
        />
      </Seccion>

      <Seccion
        titulo="Modo guiado"
        ayuda='Con el modo guiado activado, la franja "💡 Cómo leer esta pantalla" aparece abierta en cada pantalla. Apagarlo no borra el contenido: sólo lo colapsa por defecto.'
      >
        <Segmented options={OPCIONES_MODO_GUIADO} value={modoGuiado ? '1' : '0'} onChange={v => setModoGuiado(v === '1')} />
        <div className="flex flex-col gap-2 mt-3">
          <Button
            variant="outline"
            onClick={() => {
              limpiarGuiasColapsadas()
              showToast('Se volvieron a mostrar todas las guías.')
            }}
          >
            Volver a mostrar todas las guías
          </Button>
          <Button variant="outline" onClick={abrirTour}>
            Ver el tour de bienvenida
          </Button>
          <Button variant="outline" onClick={() => navigate('/ayuda')}>
            Ir al Centro de ayuda
          </Button>
        </div>
      </Seccion>

      <Seccion titulo="Restablecer preferencias" ayuda="Vuelve moneda, cartera, auto-sync, privacidad, tamaño de texto y modo guiado a los valores iniciales. No toca los datos ni lo guardado en el dispositivo.">
        <Button variant="danger" onClick={restablecer}>
          Restablecer
        </Button>
      </Seccion>
    </div>
  )
}
