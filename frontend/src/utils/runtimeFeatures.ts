export function isProfileDebugEnabled(isDev: boolean): boolean {
  return isDev
}

export const PROFILE_DEBUG_ENABLED = isProfileDebugEnabled(import.meta.env.DEV)
