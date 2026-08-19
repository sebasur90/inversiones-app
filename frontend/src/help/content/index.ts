import { HelpContent } from '../types'
import { GLOSARIO_HELP, type GlosarioKey } from './glosario'
import { SIMULADOR_HELP, type SimuladorHelpKey } from './simulador'
import { OBJETIVO_HELP, type ObjetivoHelpKey } from './objetivo'
import { BENCHMARKS_HELP, type BenchmarksHelpKey } from './benchmarks'
import { PATRIMONIO_HELP, type PatrimonioHelpKey } from './patrimonio'
import { CALIDADDATOS_HELP, type CalidadDatosHelpKey } from './calidaddatos'
import { DIAGNOSTICO_HELP, type DiagnosticoHelpKey } from './diagnostico'
import { MOVIMIENTOS_HELP, type MovimientosHelpKey } from './movimientos'
import { POSICIONES_HELP, type PosicionesHelpKey } from './posiciones'

export type HelpKey = GlosarioKey | SimuladorHelpKey | ObjetivoHelpKey | BenchmarksHelpKey | PatrimonioHelpKey | CalidadDatosHelpKey | DiagnosticoHelpKey | MovimientosHelpKey | PosicionesHelpKey

export const HELP: Record<HelpKey, HelpContent> = {
  ...GLOSARIO_HELP,
  ...SIMULADOR_HELP,
  ...OBJETIVO_HELP,
  ...BENCHMARKS_HELP,
  ...PATRIMONIO_HELP,
  ...CALIDADDATOS_HELP,
  ...DIAGNOSTICO_HELP,
  ...MOVIMIENTOS_HELP,
  ...POSICIONES_HELP,
}

export {
  GLOSARIO_HELP,
  SIMULADOR_HELP,
  OBJETIVO_HELP,
  BENCHMARKS_HELP,
  PATRIMONIO_HELP,
  CALIDADDATOS_HELP,
  DIAGNOSTICO_HELP,
  MOVIMIENTOS_HELP,
  POSICIONES_HELP,
}
