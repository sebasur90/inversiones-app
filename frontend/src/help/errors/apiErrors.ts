import { ESCENARIO_PARAM_LIMITS } from './escenarioLimits'

export interface ParsedApiError {
  message: string
  fieldErrors?: { field: string; friendlyName: string; message: string }[]
}

interface ValidationErrorItem {
  loc: (string | number)[]
  msg: string
  type: string
  ctx?: Record<string, unknown>
}

type ApiErrorResponse = string | ValidationErrorItem[] | unknown

export function parseApiError(err: unknown, fieldLabels?: Record<string, string>): ParsedApiError {
  // Sin respuesta (error de red)
  if (!err || typeof err !== 'object' || !('response' in err)) {
    return {
      message: 'No pudimos conectar con el servidor. Probá de nuevo.',
    }
  }

  const response = (err as any).response
  if (!response || !response.data || !response.data.detail) {
    return {
      message: 'Ocurrió un error. Probá de nuevo.',
    }
  }

  const detail: ApiErrorResponse = response.data.detail

  // String legible (error del router, mano escrito)
  if (typeof detail === 'string') {
    return {
      message: detail,
    }
  }

  // Array de validación (Pydantic)
  if (Array.isArray(detail)) {
    const fieldErrors: ParsedApiError['fieldErrors'] = []

    for (const err of detail) {
      if (!err.loc || !Array.isArray(err.loc)) continue

      const fieldKey = err.loc[err.loc.length - 1]?.toString() || 'unknown'
      const friendlyName = fieldLabels?.[fieldKey] || ESCENARIO_PARAM_LIMITS[fieldKey]?.label || fieldKey

      let message = err.msg || 'Error de validación'

      // Traducir tipos comunes de Pydantic
      if (err.type === 'less_than_equal' && err.ctx?.le !== undefined) {
        const unit = ESCENARIO_PARAM_LIMITS[fieldKey]?.unit || ''
        message = `${friendlyName} debe ser menor o igual a ${err.ctx.le}${unit ? ' ' + unit : ''}`
      } else if (err.type === 'greater_than_equal' && err.ctx?.ge !== undefined) {
        const unit = ESCENARIO_PARAM_LIMITS[fieldKey]?.unit || ''
        message = `${friendlyName} debe ser mayor o igual a ${err.ctx.ge}${unit ? ' ' + unit : ''}`
      } else if (err.type === 'greater_than' && err.ctx?.gt !== undefined) {
        const unit = ESCENARIO_PARAM_LIMITS[fieldKey]?.unit || ''
        message = `${friendlyName} debe ser mayor a ${err.ctx.gt}${unit ? ' ' + unit : ''}`
      } else if (err.type === 'less_than' && err.ctx?.lt !== undefined) {
        const unit = ESCENARIO_PARAM_LIMITS[fieldKey]?.unit || ''
        message = `${friendlyName} debe ser menor a ${err.ctx.lt}${unit ? ' ' + unit : ''}`
      } else if (err.type === 'missing') {
        message = `${friendlyName} es obligatorio`
      } else if (err.type === 'value_error') {
        message = `${friendlyName}: ${err.msg}`
      }

      fieldErrors.push({
        field: fieldKey,
        friendlyName,
        message,
      })
    }

    if (fieldErrors.length === 0) {
      return {
        message: 'Ocurrió un error de validación. Por favor revisá los datos.',
      }
    }

    return {
      message:
        fieldErrors.length === 1
          ? fieldErrors[0].message
          : `Encontramos ${fieldErrors.length} problemas en tu entrada: ${fieldErrors.map(f => f.message).join('; ')}.`,
      fieldErrors,
    }
  }

  // Formato desconocido
  return {
    message: 'Ocurrió un error. Probá de nuevo.',
  }
}
