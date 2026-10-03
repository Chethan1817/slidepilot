import type { AgentState } from '@livekit/components-react'
import clsx from 'clsx'

interface AgentOrbProps {
  state: AgentState
  /** Voice level, 0-1, while speaking. */
  level?: number
  size?: number
}

/** Nova's avatar: breathes while listening, orbits while thinking, pulses with its voice. */
export function AgentOrb({ state, level = 0, size = 56 }: AgentOrbProps) {
  const speaking = state === 'speaking'
  const offline = state === 'disconnected' || state === 'connecting' || state === 'failed'
  const scale = speaking ? 1 + Math.min(level * 2.2, 0.26) : 1

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-hidden>
      <div
        className={clsx('absolute inset-[6%] rounded-full blur-[8px]', offline ? 'opacity-0' : 'opacity-45')}
        style={{
          background: 'conic-gradient(from 210deg, #818cf8, #22d3ee, #6366f1, #818cf8)',
          transform: `scale(${scale * 1.06})`,
          transition: 'transform 90ms linear, opacity 500ms',
        }}
      />
      <div className="absolute inset-0 rounded-full bg-white shadow-card ring-1 ring-line" />
      <div
        className={clsx(
          'absolute inset-[13%] rounded-full',
          state === 'listening' && 'animate-breathe',
          (state === 'thinking' || state === 'initializing') && 'animate-orbit',
        )}
        style={{
          background: offline
            ? 'radial-gradient(circle at 35% 30%, #e4e7ec, #cbd2dc 75%)'
            : 'conic-gradient(from 0deg at 50% 50%, #a5b4fc, #4f46e5, #0891b2, #22d3ee, #a5b4fc)',
          transform: speaking ? `scale(${scale})` : undefined,
          transition: 'transform 90ms linear',
        }}
      >
        <div className="absolute inset-[18%] rounded-full bg-[radial-gradient(circle_at_40%_35%,rgba(255,255,255,0.7),rgba(255,255,255,0)_62%)]" />
      </div>
    </div>
  )
}
