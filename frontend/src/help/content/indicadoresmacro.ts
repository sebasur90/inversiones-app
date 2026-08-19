import { HelpContent } from '../types'

export type IndicadoresMacroHelpKey =
  | 'indicadoresmacro_indice'
  | 'indicadoresmacro_variacion'

export const INDICADORESMACRO_HELP: Record<IndicadoresMacroHelpKey, HelpContent> = {
  indicadoresmacro_indice: {
    title: 'Índice / tipo de cambio (Sheet)',
    shortDescription: 'Fuente de datos de los indicadores cargados desde tu Sheet. CER es un índice de inflación que publica el Banco Central; MEP es el tipo de cambio implícito que resulta de operaciones de compraventa en el mercado de valores.',
    whyItMatters: 'El Sheet permite hacer seguimiento manual o automático de estos dos indicadores clave. La fuente oficial de CER es el Banco Central; el MEP se calcula del mercado en tiempo real. Ver su evolución te ayuda a estimar el impacto del dólar y la inflación en tu cartera.',
    relatedTerms: ['cer', 'mep'],
  },
  indicadoresmacro_variacion: {
    title: 'Variación %',
    shortDescription: 'El cambio porcentual del indicador desde el registro anterior (día a día). Un valor positivo significa que subió; uno negativo, que bajó.',
    howToInterpret: 'Una variación del +2% en CER en un día significa que la inflación acumulada subió 2% ese día (lo cual es raro; típicamente son decimales). Una variación del +1% en MEP significa que el dólar se aprenció 1% contra el peso en esa jornada.',
    example: 'Si CER ayer era 3.5 y hoy es 3.57, la variación es +2%. Si MEP ayer era 1250 y hoy es 1255, la variación es +0.4%.',
  },
}