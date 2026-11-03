# 视频主线基线实测

实测日期：2026-11-03（Asia/Shanghai）

## 输入视频

- 文件：samples/demo_video.mp4（来自 share_exp4_handoff/samples/18f2064977d665f5dd41a9c19c7e1635.mp4）
- 文件大小：7,288,953 字节
- OpenCV 读取：25 FPS、901 帧、36.04 秒

## 运行配置

- 任务模式：本地 FastAPI + 独立 Worker
- 抽帧间隔：2（每隔 2 帧处理 1 帧）
- 检测模型：backend/weights/best.pt
- 实际推理设备：CPU
- 环境：PyTorch 2.14.1+cpu，torch.cuda.is_available() 为 false。系统虽识别到 NVIDIA GeForce MX450（2 GiB 显存），本次 PyTorch 环境没有 CUDA 支持，因此未使用 GPU。

## 结果

| 指标 | 实测 |
|---|---:|
| 任务状态 | ready，无错误 |
| 原视频帧数 | 901 |
| Worker 处理帧数 | 450 / 450 |
| 平均单帧推理耗时 | 25.09 ms |
| Worker 处理耗时 | 17.285 s |
| 已处理采样帧吞吐 | 26.03 帧/秒 |
| 按原视频帧数折算吞吐 | 52.13 帧/秒 |
| 视频处理速度 / 播放速度 | 2.09 倍 |

Worker 处理耗时由任务计时字段 total_seconds 记录，包含检测与事件生成，不含模型启动和视频上传耗时。预览生成由 API 后台单独处理，不计入该 Worker 计时。此次得到的是这台机器的 CPU 基线，性能会随设备、驱动、视频内容和负载变化。
