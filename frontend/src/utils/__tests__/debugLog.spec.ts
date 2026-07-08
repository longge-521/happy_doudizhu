import { afterEach, describe, expect, it, vi } from 'vitest'
import { debugLog } from '../debugLog'

describe('debugLog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writes development debug output through console.debug', () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {})

    debugLog('message', { ok: true })

    expect(debugSpy).toHaveBeenCalledWith('message', { ok: true })
  })
})
