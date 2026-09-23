import { HelpContent } from '../types'
import { GLOSARIO_HELP, type GlosarioKey } from './glosario'
import { SIMULADOR_HELP, type SimuladorHelpKey } from './simulador'
import { SIMULADOR_VIDA_HELP, type SimuladorVidaHelpKey } from './simuladorVida'
import { OBJETIVO_HELP, type ObjetivoHelpKey } from './objetivo'
import { BENCHMARKS_HELP, type BenchmarksHelpKey } from './benchmarks'
import { PATRIMONIO_HELP, type PatrimonioHelpKey } from './patrimonio'
import { CALIDADDATOS_HELP, type CalidadDatosHelpKey } from './calidaddatos'
import { DIAGNOSTICO_HELP, type DiagnosticoHelpKey } from './diagnostico'
import { MOVIMIENTOS_HELP, type MovimientosHelpKey } from './movimientos'
import { POSICIONES_HELP, type PosicionesHelpKey } from './posiciones'
import { EXPOSICION_HELP, type ExposicionHelpKey } from './exposicion'
import { VENCIMIENTOS_HELP, type VencimientosHelpKey } from './vencimientos'
import { PRECIOS_HELP, type PreciosHelpKey } from './precios'
import { INDICADORESMACRO_HELP, type IndicadoresMacroHelpKey } from './indicadoresmacro'
import { COMPARADOR_HELP, type ComparadorHelpKey } from './comparador'
import { PERFORMANCERELATIVA_HELP, type PerformanceRelativaHelpKey } from './performancerelativa'
import { TICKERDETALLE_HELP, type TickerDetalleHelpKey } from './tickerdetalle'
import { COMISIONES_HELP, type ComisionesHelpKey } from './comisiones'
import { REBALANCEO_HELP, type RebalanceoHelpKey } from './rebalanceo'
import { FLUJOCAJA_HELP, type FlujoCajaHelpKey } from './flujocaja'
import { WATCHLIST_HELP, type WatchlistHelpKey } from './watchlist'
import { ANALISISTECNICO_HELP, type AnalisisTecnicoHelpKey } from './analisisTecnico'
import { ESTRATEGIAS_HELP, type EstrategiasHelpKey } from './estrategias'
import { APORTES_HELP, type AportesHelpKey } from './aportes'
import { SALUD_HELP, type SaludHelpKey } from './salud'
import { EXPLICACIONRESULTADO_HELP, type ExplicacionResultadoHelpKey } from './explicacionResultado'
import { DESCOMPOSICION_HELP, type DescomposicionHelpKey } from './descomposicion'
import { COSTOOPORTUNIDAD_HELP, type CostoOportunidadHelpKey } from './costooportunidad'
import { MATRIZCORRELACIONES_HELP, type MatrizCorrelacionesHelpKey } from './matrizcorrelaciones'

export type HelpKey = GlosarioKey | SimuladorHelpKey | SimuladorVidaHelpKey | ObjetivoHelpKey | BenchmarksHelpKey | PatrimonioHelpKey | CalidadDatosHelpKey | DiagnosticoHelpKey | MovimientosHelpKey | PosicionesHelpKey | ExposicionHelpKey | VencimientosHelpKey | PreciosHelpKey | IndicadoresMacroHelpKey | ComparadorHelpKey | PerformanceRelativaHelpKey | TickerDetalleHelpKey | ComisionesHelpKey | RebalanceoHelpKey | FlujoCajaHelpKey | WatchlistHelpKey | AnalisisTecnicoHelpKey | EstrategiasHelpKey | AportesHelpKey | SaludHelpKey | ExplicacionResultadoHelpKey | DescomposicionHelpKey | CostoOportunidadHelpKey | MatrizCorrelacionesHelpKey

export const HELP: Record<HelpKey, HelpContent> = {
  ...GLOSARIO_HELP,
  ...SIMULADOR_HELP,
  ...SIMULADOR_VIDA_HELP,
  ...OBJETIVO_HELP,
  ...BENCHMARKS_HELP,
  ...PATRIMONIO_HELP,
  ...CALIDADDATOS_HELP,
  ...DIAGNOSTICO_HELP,
  ...MOVIMIENTOS_HELP,
  ...POSICIONES_HELP,
  ...EXPOSICION_HELP,
  ...VENCIMIENTOS_HELP,
  ...PRECIOS_HELP,
  ...INDICADORESMACRO_HELP,
  ...COMPARADOR_HELP,
  ...PERFORMANCERELATIVA_HELP,
  ...TICKERDETALLE_HELP,
  ...COMISIONES_HELP,
  ...REBALANCEO_HELP,
  ...FLUJOCAJA_HELP,
  ...WATCHLIST_HELP,
  ...ANALISISTECNICO_HELP,
  ...ESTRATEGIAS_HELP,
  ...APORTES_HELP,
  ...SALUD_HELP,
  ...EXPLICACIONRESULTADO_HELP,
  ...DESCOMPOSICION_HELP,
  ...COSTOOPORTUNIDAD_HELP,
  ...MATRIZCORRELACIONES_HELP,
}

export {
  GLOSARIO_HELP,
  SIMULADOR_HELP,
  SIMULADOR_VIDA_HELP,
  OBJETIVO_HELP,
  BENCHMARKS_HELP,
  PATRIMONIO_HELP,
  CALIDADDATOS_HELP,
  DIAGNOSTICO_HELP,
  MOVIMIENTOS_HELP,
  POSICIONES_HELP,
  EXPOSICION_HELP,
  VENCIMIENTOS_HELP,
  PRECIOS_HELP,
  INDICADORESMACRO_HELP,
  COMPARADOR_HELP,
  PERFORMANCERELATIVA_HELP,
  TICKERDETALLE_HELP,
  COMISIONES_HELP,
  REBALANCEO_HELP,
  FLUJOCAJA_HELP,
  WATCHLIST_HELP,
  ANALISISTECNICO_HELP,
  ESTRATEGIAS_HELP,
  APORTES_HELP,
  SALUD_HELP,
  EXPLICACIONRESULTADO_HELP,
  DESCOMPOSICION_HELP,
  COSTOOPORTUNIDAD_HELP,
  MATRIZCORRELACIONES_HELP,
}
