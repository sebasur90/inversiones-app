export default function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex bg-app-surface border border-app-border rounded-[11px] p-[3px] gap-0.5 overflow-x-auto no-scrollbar">
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`font-semibold text-caption px-2.5 py-1.5 rounded-lg whitespace-nowrap transition-colors ${
            opt.value === value ? 'bg-app-gold-soft text-app-gold' : 'text-app-text-dim'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
