import { useEffect, useState } from 'react'
import type { Deck, DeckSummary, Engine, Health, SessionCredentials } from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  readonly status: number | undefined

  constructor(message: string, status?: number) {
    super(message)
    this.status = status
  }
}

const UNREACHABLE = "Can't reach the Slidepilot API. Is the backend running on port 8000?"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(UNREACHABLE)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : null
    // The dev proxy answers 5xx without a JSON body when the API is down.
    throw new ApiError(detail ?? (response.status >= 500 ? UNREACHABLE : `Request failed (${response.status})`), response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health'),
  decks: () => request<DeckSummary[]>('/api/decks'),
  deck: (id: string) => request<Deck>(`/api/decks/${encodeURIComponent(id)}`),
  createSession: (deckId: string, engine: Engine) =>
    request<SessionCredentials>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ deck_id: deckId, engine }),
    }),
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

type Query<T> =
  | { status: 'loading'; data: undefined; error: undefined }
  | { status: 'ready'; data: T; error: undefined }
  | { status: 'error'; data: undefined; error: string }

/** Loads data once per `key`; enough for this app's read-only GETs. */
export function useQuery<T>(key: string, load: () => Promise<T>): Query<T> {
  const [state, setState] = useState<Query<T> & { key: string }>({
    key,
    status: 'loading',
    data: undefined,
    error: undefined,
  })

  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => !cancelled && setState({ key, status: 'ready', data, error: undefined }),
      (error) => !cancelled && setState({ key, status: 'error', data: undefined, error: errorMessage(error) }),
    )
    return () => {
      cancelled = true
    }
    // `load` is expected to change whenever `key` does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return state.key === key ? state : { status: 'loading', data: undefined, error: undefined }
}
