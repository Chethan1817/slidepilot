import clsx from 'clsx'

export type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white shadow-xs hover:bg-accent-hover',
  secondary: 'border border-line-strong bg-white text-ink shadow-xs hover:bg-subtle',
  ghost: 'text-ink-2 hover:bg-hover hover:text-ink',
  danger: 'border border-live/25 bg-white text-live shadow-xs hover:bg-live-soft',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-[13px]',
  md: 'h-9 gap-2 rounded-lg px-3.5 text-sm',
  lg: 'h-11 gap-2 rounded-xl px-5 text-[15px]',
}

export function buttonClass(variant: Variant = 'secondary', size: Size = 'md', className?: string) {
  return clsx(
    'inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
    'disabled:pointer-events-none disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
    className,
  )
}
