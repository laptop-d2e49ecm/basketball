# 实验 2 训练操作手册（Colab / AutoDL）

> 对比组设计与结果表见 `docs/EXP2_MODEL_SELECTION.md`；训练脚本 `scripts/03_train/train_yolo.py`。
> 上传包：项目根目录 `exp2_colab_pkg.tar`（817M，内含数据集 + 训练脚本，解压即用）。

## 方案 A：Google Colab（免费 T4，需翻墙）

1. **传包**：drive.google.com → 把 `exp2_colab_pkg.tar` 上传到"我的云端硬盘"根目录；
2. **开 GPU**：colab.research.google.com → 新建笔记本 → 运行时 → 更改运行时类型 → **T4 GPU**；
3. **单元格 1**（挂载网盘 + 解压 + 装库）：
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   !tar -xf /content/drive/MyDrive/exp2_colab_pkg.tar -C /content/
   !pip install -q ultralytics
   ```
4. **单元格 2**（开训；7 组全跑约 3 小时，浏览器标签别关）：
   ```
   !python /content/scripts/03_train/train_yolo.py --run all --device 0
   ```
   怕中途断线就分批（断线后已训完的组不重跑，脚本自动跳过已有结果）：
   ```
   !python /content/scripts/03_train/train_yolo.py --run A1,A2 --device 0   # 必做，约 40 分钟
   !python /content/scripts/03_train/train_yolo.py --run B2,C1,C2,D1 --device 0
   !python /content/scripts/03_train/train_yolo.py --run B1 --device 0
   ```
5. **回传结果**（训练完立刻执行，否则关机会丢）：
   ```
   !tar -cf /content/drive/MyDrive/exp2_results.tar -C /content models/exp2
   ```
   然后从网盘下载 `exp2_results.tar` 回本机 → 交给汇总的人填 `EXP2_MODEL_SELECTION.md` 结果表。

## 方案 B：AutoDL（国内直连，约 5 元，网络更稳）

1. autodl.com 注册 → 算力市场租 **RTX 3090/4090**（1~2 元/小时，按量计费）；
2. 控制台 → JupyterLab 上传 `exp2_colab_pkg.tar` 到 `/root/autodl-tmp/`（数据盘，空间大）；
3. 终端执行：
   ```bash
   cd /root/autodl-tmp && tar -xf exp2_colab_pkg.tar
   pip install ultralytics
   python scripts/03_train/train_yolo.py --run all --device 0
   ```
4. 训完 `tar -cf exp2_results.tar -C /root/autodl-tmp models/exp2`，JupyterLab 下载回本机；
   用完**及时关机**（否则持续计费）。

## 方案 C：Kaggle（免费 T4×2，数据集只读挂载）

> 队友实际采用的平台（实验报告口径）。数据集作为 Kaggle Dataset 挂载在 `/kaggle/input`（只读），
> 脚本已内置适配：`--data-root` 给出后自动在 `--work-dir` 生成绝对路径清单与 yaml，绕过只读限制。

1. kaggle.com → Datasets → New Dataset → 上传 `exp2_colab_pkg.tar` 解压后的 `data/splits/yolo/`（或直接上传整个 tar 后在 Notebook 里解到 `/kaggle/working`）；
2. Code → New Notebook → Settings → Accelerator 选 **GPU T4 x2**；Add Input 挂载数据集；
3. 单元格执行（与实验报告相同的超参：50 轮、patience=15）：
   ```bash
   !pip install -q ultralytics
   !python scripts/03_train/train_yolo.py --run A1,A2,M1 --epochs 50 --patience 15 --device 0        --data-root /kaggle/input/<数据集名> --work-dir /kaggle/working
   ```
   （脚本和仓库一起放进 Notebook 的 `/kaggle/working`，或只贴 `scripts/03_train/train_yolo.py` 单文件）
4. 训完立刻打包下载，**Kaggle 关机即清空 working**：
   ```bash
   !tar -cf /kaggle/working/exp2_results.tar -C /kaggle/working exp2
   ```
   回本机解压到 `models/` 下，交汇总人填结果表。

## 结果文件说明（回传后填表用）

每组目录 `models/exp2/<组名>/`：
- `weights/best.pt` 最优权重（实验 3 压缩用选出来的那组）；
- `results.csv` 逐 epoch 指标（画训练曲线）；
- `confusion_matrix.png` / `PR_curve.png` / `results.png` 报告插图直接用；
- `args.yaml` 完整超参（报告超参表照抄）。

test 集终评 mAP50/mAP50-95 会在每组训练结束的日志里直接打印（`[A1] test mAP50=...`），记下来或看日志尾部。
