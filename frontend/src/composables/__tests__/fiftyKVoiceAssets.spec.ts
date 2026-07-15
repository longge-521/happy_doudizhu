import { readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const assetRoots = [
  resolve(process.cwd(), 'public/static/audio/fifty_k'),
  resolve(process.cwd(), '../backend/static/audio/fifty_k'),
]

const assetPaths = ['female', 'male'].flatMap(gender => [
  `${gender}/510k.mp3`,
  `${gender}/true_510k.mp3`,
  `${gender}/club_three_first.mp3`,
])

describe('510K voice assets', () => {
  it.each(
    assetRoots.flatMap(root => assetPaths.map(relativePath => [root, relativePath] as const)),
  )('%s/%s is a non-empty MP3 file', (assetRoot, relativePath) => {
    const absolutePath = resolve(assetRoot, relativePath)
    const contents = readFileSync(absolutePath)

    expect(statSync(absolutePath).size).toBeGreaterThan(100)
    // MP3 帧同步头 (0xFF 0xFB/0xF3/0xF2) 或 ID3 标签头
    const isMP3Frame = contents[0] === 0xFF && (contents[1]! & 0xE0) === 0xE0
    const isID3 = contents.subarray(0, 3).toString('ascii') === 'ID3'
    expect(isMP3Frame || isID3).toBe(true)
  })
})
