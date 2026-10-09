import { useNavigate } from 'react-router-dom'
import type { ValuacionAvisos } from '../../api'
import { Icon } from '../icons/Icons'

/**
 * Pie de las pantallas que muestran un total o pesos de la cartera (Exposición, Rebalanceo,
 * Descomposición). El total de esas pantallas es el mismo que el de la pantalla principal:
 * cuando una posición no tiene cotización se valúa al costo de compra, y acá se dice cuál es.
 * Lo único que puede quedar fuera del total es lo que no se pudo valuar de ninguna forma.
 */
export default function AvisosValuacion({ avisos, moneda }: { avisos?: ValuacionAvisos; moneda?: 'ARS' | 'USD' }) {
  const navigate = useNavigate()
  if (!avisos) return null

  const sinValorMoneda = moneda === 'ARS' ? avisos.sin_valor_ars : avisos.sin_valor_usd
  const lineas: string[] = []

  if (avisos.sin_valuar.length > 0) {
    lineas.push(
      `${avisos.sin_valuar.length} posición${avisos.sin_valuar.length !== 1 ? 'es' : ''} sin precio ni costo cargado, ` +
      `no incluida${avisos.sin_valuar.length !== 1 ? 's' : ''} en el total (${avisos.sin_valuar.join(', ')}).`
    )
  }
  if (avisos.aproximadas.length > 0) {
    lineas.push(
      `${avisos.aproximadas.join(', ')} sin cotización: valuada${avisos.aproximadas.length !== 1 ? 's' : ''} ` +
      'al costo de compra, igual que en la pantalla principal.'
    )
  }
  if (sinValorMoneda && sinValorMoneda.length > 0) {
    lineas.push(
      `${sinValorMoneda.join(', ')} no se puede expresar en ${moneda === 'ARS' ? 'pesos' : 'dólares'} ` +
      '(falta el MEP del día): cuenta 0 en este total.'
    )
  }
  if (avisos.sin_ficha.length > 0) {
    lineas.push(
      `${avisos.sin_ficha.join(', ')} sin ficha en la hoja Instrumentos: ` +
      'cuenta en el total, agrupada como "Sin clasificar".'
    )
  }

  if (lineas.length === 0) return null

  return (
    <div className="mt-4 flex items-start gap-1.5 text-label text-app-text-faint">
      <Icon name="alert" className="w-3.5 h-3.5 shrink-0 mt-0.5" />
      <div className="flex flex-col gap-0.5">
        {lineas.map(linea => <span key={linea}>{linea}</span>)}
        <button onClick={() => navigate('/calidad-datos')} className="self-start font-semibold text-app-accent">
          Ver calidad de datos
        </button>
      </div>
    </div>
  )
}
