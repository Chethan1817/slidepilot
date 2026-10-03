import { useCallback, useEffect, useRef, useState } from 'react'
import { DisconnectReason, Room, RoomEvent } from 'livekit-client'
import { api, errorMessage } from './api'
import type { Engine, PresenterState } from './types'

export type Phase = 'idle' | 'connecting' | 'live' | 'ended' | 'error'

export const STATE_ATTRIBUTE = 'slidepilot.state'
export const LATENCY_ATTRIBUTE = 'slidepilot.latency_ms'
export const ERROR_ATTRIBUTE = 'slidepilot.error'
const AGENT_JOIN_TIMEOUT_MS = 20_000

/** Owns the LiveKit room for one presentation: connect, microphone, disconnect. */
export function useLiveSession(deckId: string) {
  const [room] = useState(
    () =>
      new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }),
  )
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [endedAt, setEndedAt] = useState<number | null>(null)
  const [micBlocked, setMicBlocked] = useState(false)
  const leaving = useRef(false)

  useEffect(() => {
    const onDisconnected = (reason?: DisconnectReason) => {
      setEndedAt(Date.now())
      setPhase((current) => (current === 'error' ? current : 'ended'))
      if (!leaving.current && reason !== DisconnectReason.CLIENT_INITIATED) {
        setError('The connection to the presenter was lost.')
      }
    }
    room.on(RoomEvent.Disconnected, onDisconnected)
    return () => {
      room.off(RoomEvent.Disconnected, onDisconnected)
      void room.disconnect()
    }
  }, [room])

  const start = useCallback(async (engine: Engine) => {
    leaving.current = false
    setError(null)
    setMicBlocked(false)
    setPhase('connecting')
    try {
      const credentials = await api.createSession(deckId, engine)
      await room.connect(credentials.server_url, credentials.participant_token)
      try {
        // preConnectBuffer keeps what you say while the agent is still joining.
        await room.localParticipant.setMicrophoneEnabled(true, undefined, { preConnectBuffer: true })
      } catch {
        setMicBlocked(true)
      }
      await room.startAudio().catch(() => {})
      setStartedAt(Date.now())
      setEndedAt(null)
      setPhase('live')
    } catch (e) {
      leaving.current = true
      await room.disconnect()
      setError(errorMessage(e))
      setPhase('error')
    }
  }, [room, deckId])

  const end = useCallback(async () => {
    leaving.current = true
    await room.disconnect()
  }, [room])

  const fail = useCallback(
    async (message: string) => {
      leaving.current = true
      setError(message)
      setPhase('error')
      await room.disconnect()
    },
    [room],
  )

  return { room, phase, error, startedAt, endedAt, micBlocked, start, end, fail }
}

/** Ends the session with a helpful message if no agent shows up in time. */
export function useAgentJoinTimeout(phase: Phase, agentJoined: boolean, fail: (message: string) => void) {
  useEffect(() => {
    if (phase !== 'live' || agentJoined) return
    const id = window.setTimeout(
      () =>
        fail(
          "Nova didn't join the room. Make sure the agent worker is running: cd backend && uv run python -m app.agent dev",
        ),
      AGENT_JOIN_TIMEOUT_MS,
    )
    return () => window.clearTimeout(id)
  }, [phase, agentJoined, fail])
}

export function parsePresenterState(raw: string | undefined): PresenterState | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as PresenterState
  } catch {
    return null
  }
}

const ENGINE_KEY = 'slidepilot.engine'

/** The engine picked last time (a per-browser convenience; storage may be unavailable). */
export function savedEngine(): Engine {
  try {
    return localStorage.getItem(ENGINE_KEY) === 'langgraph_pipeline' ? 'langgraph_pipeline' : 'livekit'
  } catch {
    return 'livekit'
  }
}

export function saveEngine(engine: Engine) {
  try {
    localStorage.setItem(ENGINE_KEY, engine)
  } catch {
    // Private windows and blocked storage: the choice just isn't remembered.
  }
}
