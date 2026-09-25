import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  eliminarObjetivoAporte,
  guardarObjetivoAporte,
  type RitmoAportesOut,
} from '../../api'
import { qk } from '../../api/queryClient'
import { formatUSD } from '../../utils'
import Card from '../ui/Card'
import MetricTile from '../ui/MetricTile'
import Segmented from '../ui/Segmented'
import InfoTooltip from '../../help/components/InfoTooltip'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError, type ParsedApiError } from '../../help/errors/apiErrors'
import AportesMensualesChart from '../charts/AportesMensualesChart'
import AportesHeatmap from '../charts/AportesHeatmap'
import NivelHeader from './NivelHeader'
import ObjetivoMesCard from './ObjetivoMesCard'
import ModalObjetivoAporte from './ModalObjetivoAporte'
import RachaCard from './RachaCard'
import MisionCard from './MisionCard'
import LogrosGrid from './LogrosGrid'
import RecordsCard from './RecordsCard'
import ProyeccionRitmoCard from './ProyeccionRitmoCard'
import AportesVsCrecimientoCard from './AportesVsCrecimientoCard'
import { meses } from './comun'

type Ventana = '6' | '12' | '24' | 'all'

const VENTANAS: { value: Ventana; label: string }[] = [
  { value: '6', label: '6 m' },
  { value: '12', label: '12 m' },
  { value: '24', label: '24 m' },
  { value: 'all', label: 'Todo' },
]

/** Pestaña "Progreso": el hábito, no la estadística. Responde "¿estoy siendo constante?",
 *  "¿cuánto me falta para mi objetivo?" y "¿a dónde llego si sigo así?". */
export default function AportesProgreso({
  datos,
  cartera,
}: {
  datos: RitmoAportesOut
  cartera: string | null
}) {
  const qc = useQueryClient()
  const [modalAbierto, setModalAbierto] = useState(false)
  const [ventana, setVentana] = useState<Ventana>('12')
  const [error, setError] = useState<ParsedApiError | null>(null)

  const prog = datos.progreso!
  const est = datos.estadisticas!
  const rachas = datos.rachas!

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: qk.de('aportes-ritmo', cartera) })
    setModalAbierto(false)
    setError(null)
  }
  const alFallar = (err: unknown) => setError(parseApiError(err))

  const guardar = useMutation({
    mutationFn: ({ monto, retroactivo }: { monto: number; retroactivo: boolean }) =>
      guardarObjetivoAporte(cartera, monto, retroactivo),
    onSuccess: invalidar,
    onError: alFallar,
  })
  const eliminar = useMutation({
    mutationFn: () => eliminarObjetivoAporte(cartera),
    onSuccess: invalidar,
    onError: alFallar,
  })

  const serieVisible =
    ventana === 'all' ? datos.serie_mensual : datos.serie_mensual.slice(-Number(ventana))
  const mesesSinAportar = est.meses_historia - est.meses_con_aporte

  return (
    <>
      <ErrorBanner error={error} />

      <NivelHeader nivel={prog.nivel} rachas={rachas} />
      <ObjetivoMesCard objetivo={prog.objetivo} onConfigurar={() => setModalAbierto(true)} />
      {prog.mision && <MisionCard mision={prog.mision} />}
      <RachaCard rachas={rachas} serie={datos.serie_mensual} />

      {/* Calendario del hábito */}
      <h3 className="text-body font-bold text-app-text mb-2">📅 Tu calendario</h3>
      <AportesHeatmap meses={datos.serie_mensual} anios={datos.por_anio} mostrarObjetivo />

      {/* Evolución */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <h3 className="text-body font-bold text-app-text">
          <InfoTooltip term="aportes_promedio_movil" label="📈 Cómo evolucionó" />
        </h3>
        <Segmented options={VENTANAS} value={ventana} onChange={setVentana} />
      </div>
      <Card className="mb-4">
        <AportesMensualesChart serie={serieVisible} promedio12={est.promedio_12_usd} />
        <div className="text-caption text-app-text-dim mt-2 pt-2 border-t border-app-border">
          {prog.evolucion.frase}
        </div>
      </Card>

      {/* Resumen */}
      <h3 className="text-body font-bold text-app-text mb-2">📊 Tus números</h3>
      <div className="grid grid-cols-2 gap-2 mb-4">
        <MetricTile
          label="Total aportado"
          value={formatUSD(est.total_neto_usd)}
          infoTerm="aportes_neto_criterio"
        />
        <MetricTile
          label="Promedio mensual"
          value={formatUSD(est.promedio_usd)}
          infoTerm="aportes_promedio"
          insuficiente={est.promedio_usd == null}
          sub={est.mediana_usd != null ? `Mediana ${formatUSD(est.mediana_usd)}` : undefined}
        />
        <MetricTile
          label="Últimos 3 meses"
          value={formatUSD(est.promedio_3_usd)}
          insuficiente={est.promedio_3_usd == null}
          sub="promedio por mes"
        />
        <MetricTile
          label="Últimos 12 meses"
          value={formatUSD(est.promedio_12_usd)}
          insuficiente={est.promedio_12_usd == null}
          sub="promedio por mes"
        />
        <MetricTile
          label="Meses aportando"
          value={`${est.meses_con_aporte}`}
          tone="pos"
          sub={`de ${meses(est.meses_historia)} cerrados`}
        />
        <MetricTile
          label="Meses sin aportar"
          value={`${mesesSinAportar}`}
          tone={mesesSinAportar > 0 ? 'neg' : 'pos'}
          sub="en todo tu historial"
        />
        <MetricTile
          label="Tu mejor mes"
          value={formatUSD(est.mejor_mes?.neto_usd)}
          insuficiente={est.mejor_mes == null}
        />
        <MetricTile
          label="Tu mes más flojo"
          value={formatUSD(est.peor_mes?.neto_usd)}
          insuficiente={est.peor_mes == null}
        />
      </div>

      <RecordsCard records={prog.records} />
      <LogrosGrid logros={prog.logros} />
      <ProyeccionRitmoCard proyeccion={prog.proyeccion_ritmo} />
      <AportesVsCrecimientoCard cartera={cartera} />

      {/* Montado sólo mientras está abierto: así el formulario se siembra de nuevo cada vez y no
          arrastra el monto de un objetivo que se acaba de borrar. */}
      {modalAbierto && (
        <ModalObjetivoAporte
          objetivo={prog.objetivo}
          guardando={guardar.isPending || eliminar.isPending}
          onGuardar={(monto, retroactivo) => guardar.mutate({ monto, retroactivo })}
          onEliminar={() => eliminar.mutate()}
          onCerrar={() => setModalAbierto(false)}
        />
      )}
    </>
  )
}
