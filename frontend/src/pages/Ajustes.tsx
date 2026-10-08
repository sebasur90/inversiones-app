import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { evaluarAlertas, getAlertasEstado, getIolEstado, getRefrescoPrecios, probarAlertas } from '../api'
import { qk } from '../api/queryClient'
import { fechaHora } from '../utils/fechas'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import Button from '../components/ui/Button'
import BarraProgreso from '../components/ui/BarraProgreso'
import ConfigAvisos from '../components/inversiones/ConfigAvisos'
import HistorialAvisos from '../components/inversiones/HistorialAvisos'
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

  const queryClient = useQueryClient()
  const estadoAlertasQuery = useQuery({
    queryKey: qk.de('alertas-estado'),
    queryFn: getAlertasEstado,
  })
  const estadoAlertas = estadoAlertasQuery.data ?? null

  // Consumo del cupo de IOL. El endpoint existía desde el principio y no se mostraba en ninguna
  // pantalla: era la única forma de saber cuánto queda del tope mensual y no había manera de verlo.
  const iolQuery = useQuery({ queryKey: qk.de('iol-estado'), queryFn: getIolEstado })
  const iol = iolQuery.data ?? null
  const pctCupoIol = iol && iol.limite > 0 ? (iol.llamadas / iol.limite) * 100 : 0

  // Frescura de las cotizaciones, distinta de la del sync: el job liviano refresca precios durante
  // la rueda sin leer el Sheet, así que el chip del encabezado (que mira el último sync completo)
  // no la refleja.
  const refrescoQuery = useQuery({ queryKey: qk.de('refresco-precios'), queryFn: getRefrescoPrecios })
  const refresco = refrescoQuery.data ?? null

  // El estado se re-pide después de cada acción: una evaluación puede cambiar el último aviso y
  // la cantidad de pendientes.
  function refrescarEstadoAlertas() {
    void queryClient.invalidateQueries({ queryKey: qk.de('alertas-estado') })
  }

  const pruebaMutation = useMutation({
    mutationFn: probarAlertas,
    onSuccess: res => {
      showToast(res.entregado ? 'Mensaje de prueba enviado.' : `No se pudo enviar: ${res.motivo ?? 'motivo desconocido'}`)
      refrescarEstadoAlertas()
    },
    onError: () => showToast('No se pudo contactar al servidor para mandar la prueba.'),
  })

  const evaluarMutation = useMutation({
    mutationFn: () => evaluarAlertas(true),
    onSuccess: res => {
      showToast(
        res.nuevas === 0 && res.pendientes_de_entrega === 0
          ? `Sin cruces nuevos (${res.niveles_vigilados} niveles vigilados).`
          : res.entregado
            ? `${res.nuevas} cruce(s) nuevo(s); aviso enviado.`
            : `${res.nuevas} cruce(s) nuevo(s), pero el aviso no salió: ${res.motivo ?? 'motivo desconocido'}`,
      )
      refrescarEstadoAlertas()
    },
    onError: () => showToast('No se pudo evaluar las alertas.'),
  })

  const textoEstadoAlertas = !estadoAlertas
    ? 'cargando…'
    : !estadoAlertas.habilitadas
      ? 'desactivados (ALERTAS_ENABLED=false)'
      : !estadoAlertas.configurado
        ? 'falta el token o el chat de Telegram'
        : 'activos por Telegram'

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

      {/* Esto es el umbral del badge *dentro* de la app; los avisos al celular son la sección
          siguiente. Antes las dos se llamaban "Alertas de precio". */}
      <Seccion
        titulo="Aviso de proximidad en la app"
        ayuda="A qué distancia del stop-loss o del precio objetivo una posición empieza a marcarse en Posiciones y en la Watchlist. Los niveles de cada ticker se cargan en el detalle del ticker (o en la pestaña Instrumentos del Sheet); esto sólo cambia cuándo aparece el aviso previo."
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

      <Seccion
        titulo="Avisos al celular"
        ayuda="El servidor te manda un mensaje por Telegram cuando una posición cruza su stop-loss o su precio objetivo, cuando un ticker de la watchlist entra en zona de compra, y cuando dispara una estrategia que habilitaste. Cada aviso dice si es compra o venta, de qué cartera (o de la watchlist) y qué regla lo disparó. Llega con la app cerrada; se configura con TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (ver .env.example)."
      >
        <div className="text-caption text-app-text-dim">
          Estado: <span className="font-semibold text-app-text">{textoEstadoAlertas}</span>
        </div>
        {estadoAlertas && (
          <div className="text-caption text-app-text-dim mt-1">
            {estadoAlertas.niveles_vigilados} nivel{estadoAlertas.niveles_vigilados === 1 ? '' : 'es'} vigilado
            {estadoAlertas.niveles_vigilados === 1 ? '' : 's'}
            {estadoAlertas.estrategias_con_aviso > 0
              ? ` · ${estadoAlertas.estrategias_con_aviso} estrategia${estadoAlertas.estrategias_con_aviso === 1 ? '' : 's'} con aviso`
              : ''}
            {estadoAlertas.ultimo_aviso ? ` · último aviso ${fechaHora(estadoAlertas.ultimo_aviso)}` : ' · todavía sin avisos'}
          </div>
        )}
        {estadoAlertas && estadoAlertas.sin_entregar > 0 && (
          <div className="text-caption text-app-neg mt-1">
            {estadoAlertas.sin_entregar} aviso{estadoAlertas.sin_entregar === 1 ? '' : 's'} sin entregar; se
            reintenta{estadoAlertas.sin_entregar === 1 ? '' : 'n'} en la próxima evaluación.
          </div>
        )}
        <div className="flex flex-col gap-2 mt-3">
          <Button
            variant="outline"
            onClick={() => pruebaMutation.mutate()}
            disabled={pruebaMutation.isPending}
          >
            {pruebaMutation.isPending ? 'Mandando…' : 'Mandar mensaje de prueba'}
          </Button>
          <Button
            variant="outline"
            onClick={() => evaluarMutation.mutate()}
            disabled={evaluarMutation.isPending}
          >
            {evaluarMutation.isPending ? 'Evaluando…' : 'Evaluar los niveles ahora'}
          </Button>
        </div>
        <div className="text-caption text-app-text-dim mt-2">
          La evaluación también corre sola de lunes a viernes después del cierre, si el job
          programado está activado en el servidor (SCHEDULER_ENABLED).
        </div>
      </Seccion>

      <Seccion
        titulo="Qué avisar"
        ayuda="Elegí qué te llega al celular. Las compras y las ventas de cada estrategia se prenden por separado: confiar en sus entradas no obliga a confiar en sus salidas."
      >
        <ConfigAvisos />
      </Seccion>

      <Seccion
        titulo="Últimos avisos"
        ayuda="Los mismos avisos que te llegaron por Telegram, con el contexto con que se mandaron."
      >
        <HistorialAvisos />
      </Seccion>

      <Seccion
        titulo="Cotizaciones"
        ayuda="Los precios los trae el servidor de IOL, con las fuentes públicas como respaldo. Durante la rueda se refrescan solos cada dos horas (si el job está activado); el sync completo del Sheet es aparte, una vez por día."
      >
        <div className="text-caption text-app-text-dim">
          {refresco === null
            ? 'Todavía no corrió ningún refresco automático de precios.'
            : `Último refresco: ${fechaHora(refresco.timestamp)} · ${refresco.precios_actualizados} precio${refresco.precios_actualizados === 1 ? '' : 's'} de cartera, ${refresco.precios_watchlist} de watchlist`}
        </div>
        {refresco?.resultado === 'sin_fuentes' && (
          <div className="text-caption text-app-text-dim mt-1">
            La última corrida no pidió nada: las fuentes externas están apagadas
            (USE_EXTERNAL_APIS).
          </div>
        )}
        <div className="text-caption text-app-text-dim mt-2">
          El indicador de frescura del encabezado se refiere al último sync del Sheet, de donde
          salen los movimientos y los niveles de precio — no a estas cotizaciones.
        </div>
      </Seccion>

      <Seccion
        titulo="Cupo de la API de IOL"
        ayuda="IOL es la fuente primaria de cotizaciones y tiene un tope mensual de llamadas bonificadas. Cuando se agota, la app cae a las fuentes públicas."
      >
        {iol === null ? (
          <div className="text-caption text-app-text-dim">Cargando…</div>
        ) : !iol.habilitada ? (
          <div className="text-caption text-app-text-dim">
            IOL está desactivada (IOL_ENABLED=false): los precios salen de las fuentes públicas.
          </div>
        ) : (
          <>
            <BarraProgreso
              pct={iol.limite > 0 ? (iol.llamadas / iol.limite) * 100 : 0}
              tono={pctCupoIol >= 90 ? 'neg' : pctCupoIol >= 70 ? 'warn' : 'accent'}
            />
            <div className="text-caption text-app-text-dim mt-2">
              {iol.llamadas.toLocaleString('es-AR')} de {iol.limite.toLocaleString('es-AR')} llamadas
              usadas en {iol.periodo} · quedan {iol.restante.toLocaleString('es-AR')}
            </div>
          </>
        )}
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
