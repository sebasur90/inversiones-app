import { HelpContent } from '../types'

export type SimuladorVidaHelpKey =
  | 'vida_patrimonio_inicial'
  | 'vida_aporte_mensual'
  | 'vida_crecimiento_anual'
  | 'vida_inflacion'
  | 'vida_horizonte'
  | 'vida_moneda'
  | 'vida_escenario_continuar'
  | 'vida_escenario_aumentar'
  | 'vida_escenario_disminuir'
  | 'vida_escenario_dejar'
  | 'vida_escenario_aporte_extra'
  | 'vida_escenario_retiro_extra'
  | 'vida_escenario_crecimiento_anual_aportes'
  | 'vida_aportes_periodo'
  | 'vida_crecimiento_estimado'
  | 'vida_diferencia_vs_base'
  | 'vida_poder_compra'

export const SIMULADOR_VIDA_HELP: Record<SimuladorVidaHelpKey, HelpContent> = {
  vida_patrimonio_inicial: {
    title: 'Patrimonio inicial',
    shortDescription: 'Cuánto tenés invertido hoy, en la moneda que elijas para esta simulación.',
    whyItMatters: 'Es el punto de partida de todos los escenarios: se precarga con el valor actual de tu cartera, pero podés cambiarlo.',
    example: 'Si hoy tenés 10.000 y aportás 100 por mes, el escenario arranca de esos 10.000.',
  },
  vida_aporte_mensual: {
    title: 'Aporte mensual',
    shortDescription: 'Cuánto planeás aportar cada mes en el escenario "Continuar igual".',
    whyItMatters: 'Es la base sobre la que se calculan los demás escenarios (aumentar, disminuir, dejar de aportar).',
    example: 'Se precarga con tu promedio real de los últimos meses; podés editarlo para probar otro monto.',
  },
  vida_crecimiento_anual: {
    title: 'Crecimiento esperado anual',
    shortDescription: 'El retorno anual que suponés para tu inversión, en la moneda elegida.',
    whyItMatters: 'No es un dato de mercado ni una predicción: es un supuesto que vos elegís para ver "qué pasaría si".',
    example: '8 significa que suponés que tu cartera crece un 8% por año.',
    limitations: 'Si elegís ARS, este número debería ser un crecimiento nominal en pesos, no en dólares.',
  },
  vida_inflacion: {
    title: 'Inflación esperada anual',
    shortDescription: 'Opcional: cuánto suponés que va a subir el costo de vida por año, en la misma moneda del resto de los supuestos.',
    whyItMatters: 'Con este dato podés ver el resultado "en plata de hoy" (poder de compra), no sólo el número nominal.',
    example: 'Si elegís USD, un valor típico ronda el 2-3% anual; si elegís ARS, tiene que ser la inflación en pesos.',
    limitations: 'Si no la cargás, todos los montos se muestran nominales, sin descontar la pérdida de poder de compra.',
  },
  vida_horizonte: {
    title: 'Horizonte',
    shortDescription: 'Cuántos años hacia adelante querés proyectar.',
    whyItMatters: 'Define hasta dónde llega el gráfico y la tabla; los escenarios se comparan siempre en el mismo horizonte.',
  },
  vida_moneda: {
    title: 'Moneda',
    shortDescription: 'La unidad en la que vas a cargar todos los montos de esta simulación.',
    whyItMatters: 'No convierte nada: es sólo una etiqueta. Si elegís ARS, todos los supuestos (patrimonio, aporte, crecimiento, inflación) tienen que estar en pesos.',
    limitations: 'No usa el dólar MEP ni ningún tipo de cambio: mezclar montos en USD con "moneda: ARS" (o viceversa) da un resultado sin sentido.',
  },
  vida_escenario_continuar: {
    title: 'Continuar igual',
    shortDescription: 'El escenario base: seguís aportando lo mismo, sin cambios. Todos los demás escenarios se comparan contra este.',
  },
  vida_escenario_aumentar: {
    title: 'Aumentar aporte mensual',
    shortDescription: 'Simula qué pasa si, desde el mes 1, aportás más por mes que en el escenario base.',
    example: '"¿Qué pasa si aporto USD 100 por mes?": cargás 100 como el nuevo aporte mensual.',
  },
  vida_escenario_disminuir: {
    title: 'Disminuir aporte mensual',
    shortDescription: 'Simula qué pasa si, desde el mes 1, aportás menos por mes que en el escenario base.',
  },
  vida_escenario_dejar: {
    title: 'Dejar de aportar',
    shortDescription: 'Simula qué pasa si dejás de aportar desde el mes 1: el patrimonio inicial sigue creciendo solo, sin aportes nuevos.',
  },
  vida_escenario_aporte_extra: {
    title: 'Aporte extraordinario',
    shortDescription: 'Un aporte único, de una sola vez, en el mes que elijas (por ejemplo un aguinaldo o un bono).',
    whyItMatters: 'A diferencia de los otros escenarios, éste no cambia tu aporte mensual: es un ingreso puntual.',
  },
  vida_escenario_retiro_extra: {
    title: 'Retiro extraordinario',
    shortDescription: 'Un retiro único, de una sola vez, en el mes que elijas (por ejemplo para un gasto grande).',
    limitations: 'Si pedís retirar más de lo que hay disponible ese mes, el sistema retira lo que hay y te avisa: el patrimonio nunca queda negativo.',
  },
  vida_escenario_crecimiento_anual_aportes: {
    title: 'Aumentar aportes anualmente',
    shortDescription: 'Simula qué pasa si tu aporte mensual sube un porcentaje fijo cada 12 meses (por ejemplo, por un aumento de sueldo).',
    example: '"¿Qué pasa si aumento mis aportes 10% por año?": cargás 10 como el porcentaje.',
    limitations: 'El primer aumento se aplica recién en el mes 13, no en el mes 2: los aumentos son anuales, no mensuales.',
  },
  vida_aportes_periodo: {
    title: 'Aportes netos del período',
    shortDescription: 'La suma de todo lo que entró y salió de la cartera durante la simulación, sin contar el patrimonio inicial.',
    whyItMatters: 'Con un retiro extraordinario grande, este número puede dar negativo: significa que retiraste más de lo que aportaste.',
  },
  vida_crecimiento_estimado: {
    title: 'Crecimiento estimado',
    shortDescription: 'Cuánto del patrimonio final corresponde al crecimiento supuesto, sin contar el patrimonio inicial ni los aportes.',
    howItIsCalculated: 'Patrimonio final menos patrimonio inicial menos aportes netos del período.',
  },
  vida_diferencia_vs_base: {
    title: 'Diferencia vs. "Continuar igual"',
    shortDescription: 'Cuánto más (o menos) patrimonio final da este escenario, comparado con seguir aportando igual que hoy.',
  },
  vida_poder_compra: {
    title: 'En plata de hoy',
    shortDescription: 'El patrimonio final descontando la inflación que cargaste, para ver su poder de compra en moneda de hoy.',
    limitations: 'Sólo aparece si cargaste una inflación esperada; si no, los montos se muestran nominales.',
  },
}
