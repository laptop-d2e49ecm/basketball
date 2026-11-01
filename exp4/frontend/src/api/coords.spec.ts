import { describe, expect, it } from 'vitest'
import { assertValidNorm, denormBox, renormBox } from './coords'

// 实验 1 教训的回归测试：归一化↔像素往返必须闭合，非法框必须被拒绝
describe('coords 契约', () => {
  it('denorm -> renorm 往返误差 < 1e-6', () => {
    const box = { cx: 0.5, cy: 0.61, w: 0.03, h: 0.12 }
    const px = denormBox(box, 1280, 720)
    const back = renormBox(px, 1280, 720)
    for (const k of ['cx', 'cy', 'w', 'h']) {
      expect(Math.abs(back[k] - box[k])).toBeLessThan(1e-6)
    }
  })

  it('合法框通过断言，压扁/越界框被拒绝', () => {
    expect(() => assertValidNorm({ cx: 0.5, cy: 0.5, w: 0.1, h: 0.1 })).not.toThrow()
    expect(() => assertValidNorm({ cx: 0.5, cy: 0.5, w: 0, h: 0.1 })).toThrow(/压成一点/)
    expect(() => assertValidNorm({ cx: 1.2, cy: 0.5, w: 0.1, h: 0.1 })).toThrow(/越界/)
  })
})
