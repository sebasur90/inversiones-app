import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeftRight,
  ArrowUpRight,
  CalendarCheck,
  CalendarDays,
  Check,
  ChevronDown,
  Compass,
  ChevronLeft,
  DollarSign,
  Download,
  Eye,
  EyeOff,
  Home,
  Info,
  LayoutDashboard,
  LayoutGrid,
  List,
  Lock,
  Pencil,
  PieChart,
  Plus,
  RefreshCw,
  Scale,
  Search,
  ShieldCheck,
  Target,
  Trash2,
  Trophy,
  TrendingUp,
  Wallet,
  X,
  type LucideIcon,
} from 'lucide-react'

// Íconos de la barra de herramientas del gráfico técnico: no tienen equivalente en Lucide, así
// que siguen en un sprite propio (ver `IconSprite`).
type IconoPropio = 'bands' | 'marks' | 'levels' | 'curve' | 'relative'

// Los nombres de la app se mantienen: cambiar de biblioteca no obliga a tocar ninguna pantalla.
const LUCIDE = {
  home: Home,
  pie: PieChart,
  list: List,
  target: Target,
  sync: RefreshCw,
  search: Search,
  chevron: ChevronDown,
  up: ArrowUpRight,
  down: ArrowDownRight,
  close: X,
  back: ChevronLeft,
  edit: Pencil,
  trash: Trash2,
  plus: Plus,
  lock: Lock,
  check: Check,
  alert: AlertTriangle,
  download: Download,
  trend: TrendingUp,
  info: Info,
  scale: Scale,
  grid: LayoutDashboard,
  more: LayoutGrid,
  eye: Eye,
  eyeOff: EyeOff,
  wallet: Wallet,
  swap: ArrowLeftRight,
  shield: ShieldCheck,
  calendar: CalendarCheck,
  calendarDays: CalendarDays,
  dollar: DollarSign,
  trophy: Trophy,
  compass: Compass,
} satisfies Record<string, LucideIcon>

export type IconName = keyof typeof LUCIDE | IconoPropio

const PROPIOS: ReadonlySet<string> = new Set<IconoPropio>(['bands', 'marks', 'levels', 'curve', 'relative'])

export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <defs>
        {/* Barra de herramientas del gráfico técnico. */}
        <symbol id="i-bands" viewBox="0 0 24 24">
          <rect x="3" y="5.5" width="18" height="5" rx="1" />
          <rect x="3" y="13.5" width="18" height="5" rx="1" />
        </symbol>
        <symbol id="i-marks" viewBox="0 0 24 24">
          <path d="M7 4l4.5 7h-9z" />
          <path d="M17 20l-4.5-7h9z" />
        </symbol>
        <symbol id="i-levels" viewBox="0 0 24 24">
          <path d="M3 7h18" strokeDasharray="2 3" />
          <path d="M3 17h18" strokeDasharray="2 3" />
          <path d="M6 14l4-4 3 2 5-5" />
        </symbol>
        <symbol id="i-curve" viewBox="0 0 24 24">
          <path d="M4 20c5 0 7-3 9-7s4-9 7-9" />
          <path d="M4 4v16h16" />
        </symbol>
        <symbol id="i-relative" viewBox="0 0 24 24">
          <path d="M3 17l5-5 4 3 8-8" />
          <path d="M3 19l5-3 4 1 8-4" strokeDasharray="2 2.5" />
        </symbol>
      </defs>
    </svg>
  )
}

export function Icon({ name, className = 'w-[18px] h-[18px]' }: { name: IconName; className?: string }) {
  if (PROPIOS.has(name)) {
    return (
      <svg
        className={`${className} stroke-current fill-none shrink-0`}
        strokeWidth={1.7}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <use href={`#i-${name}`} />
      </svg>
    )
  }
  const Componente: LucideIcon = LUCIDE[name as keyof typeof LUCIDE]
  return <Componente className={`${className} shrink-0`} strokeWidth={1.8} aria-hidden={true} />
}
