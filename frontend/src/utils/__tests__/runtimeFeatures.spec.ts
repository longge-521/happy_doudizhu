import { describe, expect, it } from 'vitest'
import { isProfileDebugEnabled } from '../runtimeFeatures'

describe('runtimeFeatures', () => {
  it('enables profile debug mutations only in development builds', () => {
    expect(isProfileDebugEnabled(true)).toBe(true)
    expect(isProfileDebugEnabled(false)).toBe(false)
  })
})
