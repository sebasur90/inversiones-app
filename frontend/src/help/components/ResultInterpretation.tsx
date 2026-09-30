import Card from '../../components/ui/Card'

interface ResultInterpretationProps {
  title?: string
  icon?: string
  children: React.ReactNode
}

export default function ResultInterpretation({ title = '🔎 Interpretación', icon, children }: ResultInterpretationProps) {
  return (
    <Card className="bg-app-surface border border-app-border/50 p-4">
      <div className="text-strong font-semibold text-app-text mb-2 flex items-center gap-2">
        {icon && <span className="text-title">{icon}</span>}
        {title}
      </div>
      <div className="text-caption text-app-text-dim leading-relaxed space-y-2">{children}</div>
    </Card>
  )
}
