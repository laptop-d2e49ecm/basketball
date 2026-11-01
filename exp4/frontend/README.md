# 实验 4 本侧前端（三核心页，Vue 3 + Ant Design Vue）

球员检测页 `/detect`、解说文本分类页 `/text`、图文匹配页 `/match`。
本工程自带临时外壳（App.vue/NavBar）用于联调；**合并进视频主线骨架时**，
只需带走 `src/views/`、`src/api/` 与 `src/router` 中三条路由（其内已注释标明），
App.vue 换成队友骨架的外壳（含 /video 页）。

## 快速启动（后端先起在 8000）

```bash
npm install            # 国内可加 --registry=https://registry.npmmirror.com
npm run dev            # http://localhost:5173（/api 代理到 8000，/ws 代理见 vite.config.js）
npm run test           # vitest：coords 坐标契约往返测试（实验 1 教训回归防线）
npm run build          # 产物 dist/（可拷给后端 STATIC_DIR 托管）
```

## 关键实现点

- **坐标契约**：`src/api/coords.ts` 是归一化↔画布像素唯一换算点，画框前过
  `assertValidNorm` 断言（实验 1 增强时"框压成一点"教训的制度化防线）；
  canvas 内部分辨率 = 显示尺寸 × devicePixelRatio；
- **异常处理**：`src/api/client.js` 拦截器解包信封，code≠0 或网络错误统一
  AntD message 弹友好提示（如"图像格式错误，请上传 PNG/JPG"）；
- **响应式**：AntD Grid（xs=24 / md 断点），移动端上传区与结果区上下堆叠。
