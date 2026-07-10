import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(
  resolve(process.cwd(), 'src/views/LobbyView.vue'),
  'utf-8',
)

describe('LobbyView 510K 场次标识', () => {
  it('在准备页和匹配提示中使用 510K 专属名称', () => {
    expect(viewSource).toContain('<div v-if="playMode === \'fifty_k\'" class="ready-logo">510K各自为战</div>')
    expect(viewSource).toContain("playMode === 'fifty_k' ? '510K' :")
    expect(viewSource).toContain("v-else-if=\"playMode === 'fifty_k'\">匹配场次：510K")
  })
})
