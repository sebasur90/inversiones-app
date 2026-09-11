import type { ParsedApiError } from '../errors/apiErrors'
import Card from '../../components/ui/Card'

export default function ErrorBanner({ error }: { error: ParsedApiError | null }) {
  if (!error) return null

  return (
    <Card className="bg-app-neg/10 border border-app-neg/30 p-3">
      <div className="text-sm text-app-neg font-medium">{error.message}</div>
      {error.fieldErrors && error.fieldErrors.length > 0 && (
        <div className="mt-2 text-xs text-app-text-dim space-y-1">
          {error.fieldErrors.map((fe, idx) => (
            <div key={idx}>
              <span className="font-medium">{fe.friendlyName}:</span> {fe.message}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
