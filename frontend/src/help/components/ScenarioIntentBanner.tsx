import Card from '../../components/ui/Card'

interface ScenarioIntentBannerProps {
  variant: 'antes' | 'despues'
  children?: React.ReactNode
}

export default function ScenarioIntentBanner({ variant, children }: ScenarioIntentBannerProps) {
  const isBefore = variant === 'antes'
  const icon = isBefore ? '🧪' : '✓'
  const title = isBefore ? '¿Qué estás haciendo?' : '¿Qué vas a obtener?'
  const bgClass = isBefore ? 'bg-app-sky/10 border-app-sky/30' : 'bg-app-teal/10 border-app-teal/30'
  const textColor = isBefore ? 'text-app-sky' : 'text-app-teal'

  const defaultContent = isBefore
    ? 'Esto es una simulación de escenario. No es una predicción y no modifica tus inversiones reales.'
    : 'Comparación de cómo terminaría tu portafolio bajo diferentes escenarios de mercado.'

  return (
    <Card className={`border ${bgClass} p-4`}>
      <div className={`text-sm font-semibold ${textColor} flex items-center gap-2 mb-2`}>
        <span className="text-base">{icon}</span>
        {title}
      </div>
      <div className="text-xs text-app-text-dim leading-relaxed">{children || defaultContent}</div>
    </Card>
  )
}
