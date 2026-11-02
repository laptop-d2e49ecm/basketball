export interface NormalizedBox {
  cx: number
  cy: number
  w: number
  h: number
}

export interface PixelBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export function denormBox(box: NormalizedBox, canvasWidth: number, canvasHeight: number): PixelBox {
  return {
    x1: (box.cx - box.w / 2) * canvasWidth,
    y1: (box.cy - box.h / 2) * canvasHeight,
    x2: (box.cx + box.w / 2) * canvasWidth,
    y2: (box.cy + box.h / 2) * canvasHeight,
  }
}

export function assertValidNorm(box: NormalizedBox): void {
  for (const key of ['cx', 'cy', 'w', 'h'] as const) {
    const value = box[key]
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      throw new Error(`归一化坐标越界：${key}=${value}`)
    }
  }
  if (box.w <= 0 || box.h <= 0) {
    throw new Error('检测框宽高必须大于 0')
  }
}
