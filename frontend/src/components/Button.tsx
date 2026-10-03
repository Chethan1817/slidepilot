import clsx from 'clsx'
import type { ButtonHTMLAttributes } from 'react'
import { buttonClass, type Size, type Variant } from './button-class'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

export function Button({ variant, size, className, type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, size, className)} {...props} />
}

export function IconButton({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { 'aria-label': string }) {
  return (
    <button
      type="button"
      className={clsx(
        'inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-hover hover:text-ink',
        'focus-visible:outline-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-35',
        className,
      )}
      {...props}
    />
  )
}
