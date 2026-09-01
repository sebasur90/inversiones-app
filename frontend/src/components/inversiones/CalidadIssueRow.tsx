import type { SyncIssueOut } from '../../api'
import SeverityBadge, { type Severidad } from './SeverityBadge'

export default function CalidadIssueRow({ issue }: { issue: SyncIssueOut }) {
  return (
    <div className="bg-app-surface border border-app-border rounded-lg p-3 mb-2">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="text-caption font-mono text-app-text-dim">
          <span className="font-semibold">{issue.tab}</span>
          {issue.fila && <> / fila {issue.fila}</>}
        </div>
        <SeverityBadge severidad={issue.severidad as Severidad} />
      </div>
      <div className="text-body text-app-text font-medium mb-1">{issue.mensaje}</div>
      {issue.campo && <div className="text-label text-app-text-dim mb-0.5">Campo: {issue.campo}</div>}
      <div className="text-label text-app-text-dim">Impacto: {issue.impacto}</div>
    </div>
  )
}
