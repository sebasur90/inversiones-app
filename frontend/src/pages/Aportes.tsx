import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getRitmoAportes } from '../api'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import SkeletonPantalla from '../components/ui/Skeleton'
import QueryBoundary from '../components/ui/QueryBoundary'
import InfoTooltip from '../help/components/InfoTooltip'
import AportesProgreso from '../components/aportes/AportesProgreso'
import AportesAnalisis from '../components/aportes/AportesAnalisis'

type Tab = 'progreso' | 'analisis'

const TABS: { value: Tab; label: string }[] = [
  { value: 'progreso', label: 'Progreso' },
  { value: 'analisis', label: 'Análisis' },
]

export default function Aportes() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  // monedaSeleccionada se ignora a propósito: la pantalla es sólo USD (ver término aportes_moneda).
  const [tab, setTab] = useState<Tab>('progreso')

  const query = useQuery({
    queryKey: qk.de('aportes-ritmo', carteraSeleccionada),
    queryFn: () => getRitmoAportes(carteraSeleccionada),
  })
  const datos = query.data ?? null

  if (query.isLoading || query.error) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ritmo de aportes" onBack={() => navigate(-1)} />
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<SkeletonPantalla />}>
          {null}
        </QueryBoundary>
      </div>
    )
  }

  if (!datos || datos.estado === 'sin_datos' || !datos.este_mes || !datos.progreso) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ritmo de aportes" onBack={() => navigate(-1)} />
        <EmptyState
          title="Sin aportes registrados"
          description="Cuando registres compras o ventas, acá vas a ver tu constancia mes a mes, tu racha, tus logros y a cuánto llegarías si mantenés el ritmo."
        />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Ritmo de aportes" onBack={() => navigate(-1)} />

      <div className="mb-3">
        <Segmented options={TABS} value={tab} onChange={setTab} />
      </div>

      <div className="text-label text-app-text-dim mb-3 flex items-center gap-1">
        Todo en USD (dólar MEP del día de cada movimiento)
        <InfoTooltip term="aportes_moneda" label="" />
        {datos.movimientos_omitidos_sin_mep > 0 && (
          <span className="text-app-text-faint">
            · {datos.movimientos_omitidos_sin_mep} mov. sin tipo de cambio no se cuentan
          </span>
        )}
      </div>

      {tab === 'progreso' ? (
        <AportesProgreso datos={datos} cartera={carteraSeleccionada} />
      ) : (
        <AportesAnalisis datos={datos} cartera={carteraSeleccionada} />
      )}
    </div>
  )
}
