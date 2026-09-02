import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import Button from '../components/ui/Button'
import {
  usePreferenciaNumerica,
  guardarPreferencia,
  CLAVE_AUTOSYNC_HORAS,
  CLAVE_ESCALA_TEXTO,
  CLAVE_CARTERA,
  CLAVE_MONEDA,
  CLAVE_UMBRAL_PROXIMIDAD,
  UMBRAL_PROXIMIDAD_DEFAULT,
  AUTOSYNC_HORAS_DEFAULT,
  AUTOSYNC_HORAS_MAX,
  ESCALA_TEXTO_DEFAULT,
  ESCALA_TEXTO_MIN,
  ESCALA_TEXTO_MAX,
} from '../hooks/usePreferencia'
import { aplicarEscalaTexto } from '../utils/escalaTexto'
import { calcularFrescura } from '../utils/frescura'

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

function Seccion({ titulo, ayuda, children }: { titulo: string; ayuda: string; children: ReactNode }) {
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
  const { monedaSeleccionada, setMonedaSeleccionada, umbralProximidadPct, setUmbralProximidadPct, ultimoSync, showToast } =
    useInversionesContext()

  const [autoSyncHoras, setAutoSyncHoras] = usePreferenciaNumerica(
    CLAVE_AUTOSYNC_HORAS, AUTOSYNC_HORAS_DEFAULT, 0, AUTOSYNC_HORAS_MAX,
  )
  const [escalaTexto, setEscalaTexto] = usePreferenciaNumerica(
    CLAVE_ESCALA_TEXTO, ESCALA_TEXTO_DEFAULT, ESCALA_TEXTO_MIN, ESCALA_TEXTO_MAX,
  )

  function cambiarEscala(valor: number) {
    setEscalaTexto(valor)
    aplicarEscalaTexto(valor)
  }

  function restablecer() {
    for (const clave of [CLAVE_AUTOSYNC_HORAS, CLAVE_ESCALA_TEXTO, CLAVE_CARTERA, CLAVE_MONEDA, CLAVE_UMBRAL_PROXIMIDAD]) {
      guardarPreferencia(clave, null)
    }
    setAutoSyncHoras(AUTOSYNC_HORAS_DEFAULT)
    cambiarEscala(ESCALA_TEXTO_DEFAULT)
    setMonedaSeleccionada('USD')
    setUmbralProximidadPct(UMBRAL_PROXIMIDAD_DEFAULT)
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

      <Seccion titulo="Restablecer preferencias" ayuda="Vuelve moneda, cartera, auto-sync y tamaño de texto a los valores iniciales. No toca los datos.">
        <Button variant="danger" onClick={restablecer}>
          Restablecer
        </Button>
      </Seccion>
    </div>
  )
}
