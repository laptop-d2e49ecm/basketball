/**
 * 坐标换算的唯一实现（实验 1 教训的制度化落地，与后端 app/core/coords.py 同款逻辑）。
 *
 * 契约：API 返回归一化 cx,cy,w,h ∈[0,1]；画框只允许经由本模块换算，
 * 禁止在组件里手写乘法（实验 1 曾因像素/归一化混用把框压成一个点）。
 */

/** 归一化框 -> 画布像素 xyxy。canvasW/H 为 canvas 内部分辨率（=显示尺寸×dpr）。 */
export function denormBox(box, canvasW, canvasH) {
  const x1 = (box.cx - box.w / 2) * canvasW
  const y1 = (box.cy - box.h / 2) * canvasH
  const x2 = (box.cx + box.w / 2) * canvasW
  const y2 = (box.cy + box.h / 2) * canvasH
  return { x1, y1, x2, y2 }
}

/** 画布像素 xyxy -> 归一化框（测试/调试用）。 */
export function renormBox({ x1, y1, x2, y2 }, canvasW, canvasH) {
  return {
    cx: ((x1 + x2) / 2) / canvasW,
    cy: ((y1 + y2) / 2) / canvasH,
    w: (x2 - x1) / canvasW,
    h: (y2 - y1) / canvasH,
  }
}

/** 合法性断言：防"压成一点"与越界回归。 */
export function assertValidNorm(box) {
  for (const k of ['cx', 'cy', 'w', 'h']) {
    const v = box[k]
    if (!(v >= 0 && v <= 1)) throw new Error(`归一化坐标越界: ${k}=${v}`)
  }
  if (box.w <= 0 || box.h <= 0) throw new Error('框宽高必须 > 0（压成一点）')
}
