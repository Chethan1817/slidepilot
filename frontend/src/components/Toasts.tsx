import clsx from 'clsx'
import { CircleAlert, Info, Sparkles } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useRef, useState, type ReactNode } from 'react'
import { ToastContext, type Notify, type ToastTone } from '../lib/toast'

interface Toast {
  id: number
  tone: ToastTone
  title: string
  detail?: string
}

const ICONS = { info: Info, agent: Sparkles, error: CircleAlert }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)

  const notify = useCallback<Notify>((tone, title, detail) => {
    const id = ++nextId.current
    setToasts((current) => [...current.slice(-2), { id, tone, title, detail }])
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), tone === 'error' ? 6500 : 3800)
  }, [])

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => {
            const Icon = ICONS[toast.tone]
            return (
              <motion.div
                key={toast.id}
                layout
                initial={{ opacity: 0, y: -12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.98 }}
                transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                className="pointer-events-auto flex max-w-md items-start gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-elevated"
              >
                <span
                  className={clsx(
                    'mt-px flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
                    toast.tone === 'agent' && 'bg-accent-soft text-accent',
                    toast.tone === 'error' && 'bg-live-soft text-live',
                    toast.tone === 'info' && 'bg-hover text-ink-2',
                  )}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 pt-0.5">
                  <div className="text-sm font-semibold text-ink">{toast.title}</div>
                  {toast.detail && <div className="mt-0.5 text-[13px] text-ink-2">{toast.detail}</div>}
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
