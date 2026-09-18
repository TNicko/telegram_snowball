import { createContext, useContext } from 'react'
import type { AppStatus } from '../lib/api'

export const AppStatusContext = createContext<AppStatus | null>(null)

export function useAppStatus(): AppStatus | null {
  return useContext(AppStatusContext)
}
