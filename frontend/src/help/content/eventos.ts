import { HelpContent } from '../types'

export type EventosHelpKey =
  | 'eventos_que_es'
  | 'eventos_importancia'
  | 'eventos_relevancia'
  | 'eventos_confianza'
  | 'eventos_verificacion'
  | 'eventos_rueda_referencia'
  | 'eventos_comportamiento'
  | 'eventos_benchmark'
  | 'eventos_superpuestos'
  | 'eventos_bandeja'
  | 'eventos_fuentes'
  | 'eventos_patron'

export const EVENTOS_HELP: Record<EventosHelpKey, HelpContent> = {
  eventos_que_es: {
    title: 'Calendario de eventos',
    shortDescription: 'Acontecimientos pasados y futuros (elecciones, decisiones de tasas, balances, guerras, aranceles, quiebras) con su fuente, su relación con tus instrumentos y lo que hizo el precio alrededor de cada uno.',
    whyItMatters: 'Ayuda a responder qué estaba pasando cuando un activo se movió fuerte, qué fechas se vienen para lo que tenés y cómo reaccionó un activo en eventos parecidos.',
    howToInterpret: 'Es una herramienta de investigación, no una agenda de noticias ni una recomendación: que un evento esté cerca de una suba o una baja no dice que la haya causado.',
    limitations: 'Los eventos salen de varias fuentes con distinta calidad: la verificación y la confianza de cada uno lo dicen. Las noticias automáticas dependen de las claves configuradas en el servidor.',
  },
  eventos_importancia: {
    title: 'Importancia',
    shortDescription: 'Cuánto puede mover al mercado en general ese tipo de acontecimiento: baja, media o alta.',
    howItIsCalculated: 'En los importados sale de reglas escritas (una decisión de la Reserva Federal o del BCRA es alta; el balance de una empresa que seguís es media). En los tuyos la elegís vos.',
    limitations: 'No dice para dónde se mueve el precio ni cuánto: sólo qué tan grande suele ser este tipo de evento.',
  },
  eventos_relevancia: {
    title: 'Relevancia para el instrumento',
    shortDescription: 'Qué tan relacionado está el evento con un ticker en particular: directo (el balance de la empresa), por sector, por país o como índice de referencia.',
    howItIsCalculated: 'Directo vale 1; sector 0,5; país 0,35. Cada vínculo automático guarda su motivo escrito. Los que propone la app aparecen como "propuesta" hasta que los confirmes o descartes.',
    howToInterpret: 'Si decís que un evento no tiene que ver con un ticker, la app no vuelve a vincularlo aunque vuelva a importar el evento.',
  },
  eventos_confianza: {
    title: 'Confianza de los datos',
    shortDescription: 'Qué tan firme es la evidencia del evento y de su fecha: alta, media o baja.',
    howItIsCalculated: 'Sube con una fuente oficial, con varias fuentes independientes o con tu verificación, y con una fecha exacta. Baja con una fecha aproximada, sólo el mes o el año, o si es un rumor.',
    limitations: 'Es distinta de la importancia: un evento puede ser muy importante y tener una fecha todavía estimada.',
  },
  eventos_verificacion: {
    title: 'Estado de verificación',
    shortDescription: 'De dónde sale la seguridad de que el evento ocurrió (u ocurrirá) así: sin verificar, fuente oficial, varias fuentes, verificado por vos, catálogo a revisar o rumor.',
    howToInterpret: '"Catálogo a revisar" son eventos históricos que la app trae cargados con su fuente para que el análisis tenga con qué empezar; podés confirmarlos, corregirlos o descartarlos. Una clasificación automática nunca es una validación oficial.',
  },
  eventos_rueda_referencia: {
    title: 'Rueda de referencia',
    shortDescription: 'La primera rueda en la que el mercado pudo reaccionar al evento.',
    howItIsCalculated: 'Si fue antes del cierre (16 h en Nueva York, 17 h en BYMA) es la rueda de ese día; si fue después del cierre o en un día sin rueda (fin de semana, feriado), la siguiente. Para una noticia cuenta la hora de publicación. Sin hora conocida se toma la rueda del día y se avisa.',
    example: 'Una decisión anunciada un domingo se mide desde el lunes. Un balance publicado a las 16:30 de Nueva York, desde la rueda siguiente.',
  },
  eventos_comportamiento: {
    title: 'Comportamiento observado',
    shortDescription: 'Cuánto se movió el precio antes, en la rueda del evento y después, en ventanas de 1, 5 y 20 ruedas (y 60 si hay datos).',
    howItIsCalculated: 'Previo: de N ruedas antes hasta la rueda anterior al evento. Rueda: el cierre del día del evento contra el anterior. Posterior: de la rueda del evento a N ruedas después. Acumulado: toda la ventana. Se muestran las fechas exactas usadas.',
    limitations: 'No demuestra que el evento haya causado el movimiento: el mercado entero también se mueve y pueden haber pasado otras cosas en la misma ventana. Si la serie no alcanza, el dato queda vacío: nunca se completa con el precio de hoy.',
  },
  eventos_benchmark: {
    title: 'Contra el índice',
    shortDescription: 'El mismo cálculo sobre un índice (S&P 500, Nasdaq 100 o Merval) en las mismas fechas, y la diferencia en puntos.',
    whyItMatters: 'Una suba del 3 % dice poco si ese día todo el mercado subió 3 %. La diferencia es lo que el activo hizo de distinto.',
    limitations: 'Es una resta simple, no un modelo: no ajusta por cuánto se mueve en general el activo respecto del índice.',
  },
  eventos_superpuestos: {
    title: 'Otros eventos en la ventana',
    shortDescription: 'Los demás eventos relevantes que cayeron cerca, con su distancia en ruedas.',
    whyItMatters: 'Si en la misma semana hubo una decisión de tasas y un balance, no se le puede atribuir todo el movimiento a uno solo.',
  },
  eventos_bandeja: {
    title: 'Para revisar',
    shortDescription: 'Noticias que la app trajo pero no convirtió sola en evento, porque no cumplieron las reglas: categoría poco clara, importancia baja o sin mención fuerte de algo que seguís.',
    howToInterpret: 'Desde acá podés crear un evento con la noticia, sumarla a un evento existente o descartarla. Los resultados de GDELT siempre pasan por acá.',
  },
  eventos_fuentes: {
    title: 'Fuentes de datos',
    shortDescription: 'De dónde salen los eventos automáticos: noticias financieras (Marketaux), fechas de balances (Yahoo Finance), acontecimientos globales recientes (GDELT) y archivos de calendarios oficiales.',
    howToInterpret: 'Cada fuente muestra si está configurada, cuándo corrió por última vez y qué pasó. Si una falla, la pantalla sigue mostrando lo que ya estaba guardado.',
    limitations: 'Las claves se configuran en el servidor, nunca en la app. El plan gratuito de Marketaux trae pocas noticias por consulta, y GDELT sólo cubre los últimos 3 meses.',
  },
  eventos_patron: {
    title: 'En eventos parecidos',
    shortDescription: 'Cómo se comportó el activo después de todos los eventos de una misma categoría, contra cómo se comporta en general en la misma cantidad de ruedas.',
    howToInterpret: 'Si después de las decisiones de tasas sube en promedio un 1 % en 5 ruedas pero en cualquier semana sube 1 %, no hay nada especial en esos eventos.',
    limitations: 'Con pocos casos no se muestran estadísticas, sólo la lista: un promedio de tres eventos no significa nada.',
  },
}
