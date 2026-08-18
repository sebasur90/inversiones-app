import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Group,
  Badge,
} from '@mantine/core'
import type { ComparacionBenchmarkOut } from '../../api'
import { formatPctRatio } from '../../utils'

interface BenchmarkComparisonTableProps {
  filas: ComparacionBenchmarkOut[]
}

export default function BenchmarkComparisonTable({ filas }: BenchmarkComparisonTableProps) {
  const getEstadoBadge = (estado: string) => {
    switch (estado) {
      case 'ok':
        return <Badge color="green">OK</Badge>
      case 'datos_insuficientes':
        return <Badge color="yellow">Datos insuficientes</Badge>
      case 'sin_benchmark':
        return <Badge color="gray">Sin benchmark</Badge>
      default:
        return <Badge>{estado}</Badge>
    }
  }

  const formatValue = (value: number | null) => {
    if (value === null) return '—'
    return formatPctRatio(value)
  }

  return (
    <Table striped highlightOnHover>
      <TableHead>
        <TableRow>
          <TableCell>Fuente</TableCell>
          <TableCell>Tipo</TableCell>
          <TableCell>Estado</TableCell>
          <TableCell style={{ textAlign: 'right' }}>Rendimiento</TableCell>
          <TableCell style={{ textAlign: 'right' }}>Δ pp</TableCell>
          <TableCell style={{ textAlign: 'right' }}>Ranking</TableCell>
          <TableCell style={{ textAlign: 'center' }}>Meses</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {filas.map((fila) => (
          <TableRow key={fila.fuente}>
            <TableCell fw={500}>{fila.fuente}</TableCell>
            <TableCell size="sm">{fila.tipo}</TableCell>
            <TableCell>{getEstadoBadge(fila.estado)}</TableCell>
            <TableCell style={{ textAlign: 'right' }}>
              {fila.estado === 'ok' ? formatValue(fila.retorno_pct) : '—'}
            </TableCell>
            <TableCell style={{ textAlign: 'right' }}>
              {fila.estado === 'ok' && fila.delta_pp !== null ? (
                <span style={{ color: fila.delta_pp > 0 ? '#40c057' : '#fa5252' }}>
                  {fila.delta_pp > 0 ? '+' : ''}{fila.delta_pp.toFixed(2)}pp
                </span>
              ) : (
                '—'
              )}
            </TableCell>
            <TableCell style={{ textAlign: 'right' }}>
              {fila.ranking ? `${fila.ranking}°` : '—'}
            </TableCell>
            <TableCell style={{ textAlign: 'center' }}>
              {fila.n_meses_historia}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
