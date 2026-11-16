# Kaggle 训练上传说明（动作识别线，2026-11-15）

> 本包内容：`action_clips/`（7424 clip 数据集）+ `train_action.py` / `export_onnx.py` / `action_classes.py`
> + `kaggle_action_train.ipynb`（一键训练 Notebook）。上传后全程约 1 小时挂机。

## 步骤（全程网页操作，无需命令行）

1. **传数据集**：kaggle.com → Datasets → **New Dataset** → 上传 `action_clips_kaggle.zip`
   → 标题填 `basketball-action-clips`（Private）。Kaggle 会自动解压，挂载路径为
   `/kaggle/input/basketball-action-clips/action_clips/`。
2. **建 Notebook**：Notebooks → **Import Notebook** → 上传 `kaggle_action_train.ipynb`
   （本 zip 解压后即有，或从仓库 `scripts/06_action/` 取）。
   右侧 **Add Input** 挂载上一步的数据集；Settings：**Accelerator = GPU T4**、**Internet = On**。
3. **Run All**（约 1 小时）：mc3_18 ≈15 分钟 + r2plus1d_18 ≈45 分钟 + 导出 ≈5 分钟。
   逐 epoch 打印 loss / dev acc / macro recall；末尾打印两档官方 val 的 acc / macro recall。
4. **回传**：右侧 Output 下载 **`action_train_return.zip`**（约 350MB，含双档 best.pt / onnx /
   train_summary / results.csv / export_meta / 部署 meta）。
5. **部署**：按仓库 `docs/实验5_动作识别执行计划.md` §3——
   `action_mc3_18.onnx` + `action_clf_meta.json` 覆盖 `backend/weights/`，
   `.env` 加 `BASKETBALL_ACTION=on`，重启 Worker，跑 demo 视频验收截图。

## 校验

zip 的 SHA256 见 `action_clips_kaggle.zip.sha256.txt`（与 zip 同目录）；
正式训练产物的 clip 口径（见 `train_summary.json`）：train 4704 / dev 659 / test 2061
（按视频级 9:1 再切 + 官方 val 全量）。

## 离线训练补丁（2026-11-16 实测，Internet=Off 也能跑）

1. **pip 格报错可跳过**：训练只需预装的 torch/torchvision，pip 失败不影响；
2. **数据集路径**：新版挂载可能是深路径 `/kaggle/input/datasets/<owner>/<slug>/`，
   用 `Path('/kaggle/input').rglob('meta.json')` 递归找 `action_clips` 目录，别硬编码浅路径；
3. **预训练权重**：离线下 torchvision 下不了 Kinetics 权重——从本机
   `~/.cache/torch/hub/checkpoints/` 下载 `.pth` 上传，拷进 Notebook 同路径并按
   `weights.url` 文件名重命名（torchvision 0.29：`mc3_18-a90a0ba3.pth`、`r2plus1d_18-91a641e6.pth`）；
4. **路径纪律**：`--work-dir /kaggle/working/models/exp5_action`（回传打包按此找产物）；
   `/kaggle/working/scripts` 由查找格创建，训练格之前必须先跑它。
   实测 T4、batch 16、各 20 epoch：mc3_18 ≈139s/epoch（best=18），r2plus1d_18 ≈258s/epoch（best=12）。

## 提醒

- 上传完成后本地 `action_clips_kaggle.zip` 可删除（本地解压目录已加入 .gitignore）；
  数据集可随时由 `scripts/06_action/build_clips.py --jobs 4 --force` 重建。
- ~~回传前占位权重不要对外演示~~ → 2026-11-16 正式权重已部署并验收，
  见 `docs/实验5_动作识别执行计划.md` §0/§3。
