import { useMultibandTrackVolume, useTrackVolume, type AgentState, type TrackReference } from '@livekit/components-react'
import clsx from 'clsx'
import { AgentOrb } from '../AgentOrb'

/** The orb, driven by the agent's live audio track. */
export function LiveAgentOrb({ state, track, size }: { state: AgentState; track?: TrackReference; size?: number }) {
  const level = useTrackVolume(track)
  return <AgentOrb state={state} level={level} size={size} />
}

/** Small five-band level meter for the agent's voice. */
export function VoiceBars({ track, active }: { track?: TrackReference; active: boolean }) {
  const bands = useMultibandTrackVolume(track, { bands: 5, loPass: 100, hiPass: 200 })
  return (
    <div className="flex h-4 items-center gap-[3px]" aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={clsx('w-[3px] rounded-full transition-[height] duration-75', active ? 'bg-accent' : 'bg-line-strong')}
          style={{ height: `${active ? Math.max(20, Math.min(100, (bands[i] ?? 0) * 260)) : 20}%` }}
        />
      ))}
    </div>
  )
}
