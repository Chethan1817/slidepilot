import clsx from 'clsx'
import { prettyModel, prettyVendor } from '../lib/format'
import type { Health } from '../lib/types'

/** System status from /api/health: whether LiveKit is configured and which LLM runs. */
export function StatusPill({ health, error }: { health?: Health; error?: string }) {
  const ready = health?.livekit_configured
  const label = error ? 'API offline' : !health ? 'Checking…' : ready ? prettyModel(health.models.llm) : 'Setup needed'
  const title = health
    ? `LLM: ${health.models.llm} · Speech-to-text: ${prettyVendor(health.models.stt)} · Voice: ${prettyVendor(health.models.tts)}`
    : error
  return (
    <div
      title={title}
      className="flex h-8 items-center gap-2 rounded-full border border-line bg-white px-3 text-[12.5px] font-medium text-ink-2 shadow-xs"
    >
      <span className={clsx('h-2 w-2 rounded-full', error ? 'bg-live' : !health ? 'bg-ink-3' : ready ? 'bg-ok' : 'bg-warn')} />
      {label}
    </div>
  )
}
