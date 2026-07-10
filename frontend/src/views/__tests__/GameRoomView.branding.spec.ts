import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(
  resolve(process.cwd(), 'src/views/GameRoomView.vue'),
  'utf-8',
)

describe('GameRoomView 玩法标识', () => {
  it('为 510K 对局展示专属场次名称', () => {
    expect(viewSource).toContain("<div v-if=\"gameStore.playMode === 'fifty_k'\" class=\"watermark-main\">510K各自为战</div>")
    expect(viewSource).toContain("<span v-else-if=\"gameStore.playMode === 'fifty_k'\">510K新手场</span>")
  })
})
