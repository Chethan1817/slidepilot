import { createContext, useContext } from 'react'

export type ToastTone = 'info' | 'agent' | 'error'

export type Notify = (tone: ToastTone, title: string, detail?: string) => void

export const ToastContext = createContext<Notify>(() => {})

export const useToast = () => useContext(ToastContext)
