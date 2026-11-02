import { describe, expect, it } from 'vitest'
import { assertValidNorm, denormBox, type NormalizedBox } from './coords'

describe('normalized detection box coordinates', () => {
  it('maps normalized center/size coordinates to a pixel rectangle', () => {
    expect(denormBox({ cx: 0.5, cy: 0.5, w: 0.4, h: 0.6 }, 200, 100)).toEqual({
      x1: 60,
      y1: 20,
      x2: 140,
      y2: 80,
    })
  })

  it('accepts boxes on image edges and rejects invalid ranges', () => {
    expect(() => assertValidNorm({ cx: 0, cy: 1, w: 1, h: 1 })).not.toThrow()
    for (const box of [
      { cx: -0.01, cy: 0.5, w: 0.2, h: 0.2 },
      { cx: 0.5, cy: 1.01, w: 0.2, h: 0.2 },
      { cx: Number.NaN, cy: 0.5, w: 0.2, h: 0.2 },
    ] satisfies NormalizedBox[]) {
      expect(() => assertValidNorm(box)).toThrow('归一化坐标越界')
    }
  })

  it('rejects zero width and height', () => {
    expect(() => assertValidNorm({ cx: 0.5, cy: 0.5, w: 0, h: 0.2 })).toThrow('检测框宽高必须大于 0')
    expect(() => assertValidNorm({ cx: 0.5, cy: 0.5, w: 0.2, h: 0 })).toThrow('检测框宽高必须大于 0')
  })
})
