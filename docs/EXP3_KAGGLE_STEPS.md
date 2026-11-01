# 实验 3 Kaggle 蒸馏操作手册（P1 用）

> 对应脚本：`exp3/scripts/distill_yolo.py`（ultralytics 8.4.176 内置蒸馏，本地 CPU 冒烟已通过）。
> 实际采用的两个挂载数据集：队友实验 2 的公开数据集 **`exp2data`**（hkd12334，仅 1 个文件：
> `exp2_colab_pkg.tar` 817MB，图片数据全在里面）
> + 自建 `exp3-weights`（56MB，仅 a2_best.pt / m1_best.pt / distill_yolo.py 三个文件）。
> 预计耗时：权重上传 ~2 分钟 + 训练 25-40 分钟 + 回传 2 分钟（图片 915MB 不重复上传）。

## 1. 建数据集（一次性）

图片数据不重复上传：直接挂队友实验 2 已公开的数据集；只需自建一个小数据集传权重：

1. kaggle.com → 顶部 **Datasets** → **New Dataset**；
2. 上传项目根目录的 `exp3_kaggle_weights.tar`（直接传 tar，不解压），命名 `exp3-weights`，保持 Private；
3. 挂载路径：队友数据集 `/kaggle/input/<其数据集名>/`，权重 `/kaggle/input/exp3-weights/`。

## 2. 开 Notebook 并配置（1 分钟）

**Code → New Notebook**，右侧 Settings 面板：
- **Accelerator** → `GPU T4 x2`；
- **Internet** → `On`（装库需要；GPU+Internet 同时开要求账号已手机验证，实验 2 已用过 Kaggle 应无问题）；
- **Add Input** → 挂载两个数据集：队友的图片大包 + 自建的 `exp3-weights`。

## 3. 逐格执行

**单元格 1：装库（~1 分钟，版本必须锁死）**

```bash
!pip install -q ultralytics==8.4.176
```

> 内置蒸馏（`distill_model`/`dis` 参数）依赖 8.4+；且与本地测出的数字（基线 0.419、INT8 0.420）保持同版本才可比。

**单元格 2：解包并摆好目录（~2 分钟，自动定位，直接整格复制运行）**

```python
import glob, os, shutil, tarfile

os.chdir('/kaggle/working')

def count_images(d):
    return sum(1 for _, _, fs in os.walk(d) for f in fs
               if f.lower().endswith(('.jpg', '.jpeg', '.png')))

# 1) 数据源自适应：有 100MB 以上的大 tar 就解它；否则在所有 data.yaml 目录里选图片最多的
tars = [p for p in glob.glob('/kaggle/input/**/*.tar', recursive=True)
        if 'exp3_kaggle_weights' not in p and os.path.getsize(p) > 100 * 2**20]
src_dir = None
if tars:  # 形态 A：tar 包
    big = max(tars, key=os.path.getsize)
    print(f'found tar: {big} ({os.path.getsize(big) // 2**20} MB)')
    tarfile.open(big).extractall('/kaggle/working/_pkg')
    src_dir = os.path.dirname(glob.glob('/kaggle/working/_pkg/**/data.yaml', recursive=True)[0])
else:  # 形态 B：解压好的目录（可能有多个数据集，按图片数挑最全的）
    best = (0, None)
    for y in glob.glob('/kaggle/input/**/data.yaml', recursive=True):
        d = os.path.dirname(y)
        n = count_images(d)
        print(f'candidate: {y} -> {n} images')
        if n > best[0]:
            best = (n, d)
    assert best[1] and best[0] >= 5000, f'数据图片不足（最多 {best[0]} 张，期望 5042）'
    src_dir = best[1]
print('using source:', src_dir)

# 2) 复制到 working（YOLO 要在 labels 旁写 .cache，/kaggle/input 只读）
os.makedirs('/kaggle/working/data/splits', exist_ok=True)
shutil.copytree(src_dir, '/kaggle/working/data/splits/yolo', dirs_exist_ok=True)
n_img = count_images('/kaggle/working/data/splits/yolo/images')
print(f'images copied: {n_img}')  # 应为 5042（4316+346+380）

# 3) 权重与脚本就位（Kaggle 建数据集时会把 tar 自动解压成散文件，两种形态都兼容）
a2 = glob.glob('/kaggle/input/**/a2_best.pt', recursive=True)
m1 = glob.glob('/kaggle/input/**/m1_best.pt', recursive=True)
py = glob.glob('/kaggle/input/**/distill_yolo.py', recursive=True)
if not (a2 and m1 and py):  # 数据集里仍是 tar 形态则解开
    w = glob.glob('/kaggle/input/**/exp3_kaggle_weights.tar', recursive=True)
    assert w, '没找到权重（散文件/tar 都没有）：检查 exp3-weights 数据集是否挂载'
    tarfile.open(w[0]).extractall('/kaggle/working')
    a2, m1, py = ['a2_best.pt'], ['m1_best.pt'], ['distill_yolo.py']
os.makedirs('models/exp2/A2_yolov8n/weights', exist_ok=True)
os.makedirs('models/exp2/A2_yolov8m/weights', exist_ok=True)
shutil.copy2(a2[0], 'models/exp2/A2_yolov8n/weights/best.pt')
shutil.copy2(m1[0], 'models/exp2/A2_yolov8m/weights/best.pt')
shutil.copy2(py[0], 'distill_yolo.py')
print('staged ok')
```

> 为什么要挪：YOLO 要在 labels 目录旁写 `.cache`，`/kaggle/input` 只读（实验 2 踩过的同一坑）；
> 挪到 `/kaggle/working` 后 `distill_yolo.py` 里的相对路径（`data/splits/yolo/`、`models/exp2/...`）原样生效，脚本零修改。

**单元格 3：蒸馏训练（T4 约 25-40 分钟）**

```bash
%cd /kaggle/working
!python distill_yolo.py --device 0 --epochs 12
```

预期日志：进度条含 **dis_loss** 列（正常应缓慢下降）；每个 epoch 结束在 val 346 张上自动验证；
结束自动 fuse 剥离蒸馏包装，产出**纯学生权重**。
注意产物路径：ultralytics 对相对 `project`（脚本里 `project="exp3/runs"`）会拼到默认 `runs_dir` 的
`detect/` 子目录下，实际落盘为 `/kaggle/working/runs/detect/exp3/runs/a2_distill/weights/best.pt`
（本地冒烟同路径 `runs/detect/exp3/runs/a2_distill_smoke/` 可证）。
浏览器标签别关；会话若断，从单元格 2 重来（很快），训练本身不会续跑。

**单元格 4：打包回传（训完立刻执行）**

```bash
!tar -cf /kaggle/working/distill_results.tar -C /kaggle/working runs/detect/exp3
!tar -tf /kaggle/working/distill_results.tar | head
```

## 4. 下载结果

- 交互会话：右侧文件面板直接下载 `distill_results.tar`；
- 或右上 **Save Version → Save & Run All**，跑完后在该 Notebook 的 **Output** 标签页下载。
- **Kaggle 关机即清空 working**，务必先打包再关。

## 5. 本机收尾（对照达标线）

```bash
tar -xf distill_results.tar -C .                        # → runs/detect/exp3/runs/a2_distill/
cp runs/detect/exp3/runs/a2_distill/weights/best.pt exp3/models/a2_distilled.pt
.venv/Scripts/yolo.exe val model=exp3/models/a2_distilled.pt data=data/splits/yolo/data.yaml split=test imgsz=640
```

达标线：test mAP50 **≥ 0.418**（打平 A2 即合格），理想逼近 v8m 的 0.424。

**实测结果（2026-10-26，已回填）**：test 380 mAP50 **0.418** / mAP50-95 0.245 —— 与未蒸馏 A2（0.419）
持平（差距在测量噪声内），距教师 0.424 仅 -0.6pp，任务书"蒸馏精度损失 ≤1%"达标；
体积 6.3MB（教师 50MB，-87%）。val 346 上 0.420。结果在 `exp3/results/a2_distilled.json`，
对比图 `exp3/results/figures/fig5_distill.png`，训练曲线与可视化在 `runs/detect/exp3/runs/a2_distill/`。

**可选叠加（已完成，2026-10-26）：蒸馏 + INT8（E1 同口径 val346 校准）**

```bash
.venv/Scripts/yolo.exe export model=exp3/models/a2_distilled.pt format=onnx imgsz=640 dynamic=True
.venv/Scripts/python.exe exp3/scripts/export_quant.py --src exp3/models/a2_distilled.onnx --out exp3/models/a2_distilled_int8.onnx
.venv/Scripts/yolo.exe val model=exp3/models/a2_distilled_int8.onnx data=data/splits/yolo/data.yaml split=test imgsz=640
```

实测：test 380 mAP50 **0.412** / mAP50-95 0.240，体积 3.5MB。**发现**：蒸馏后量化掉 0.6pp
（原版 A2 量化几乎无损 0.419→0.420）——蒸馏学生拟合教师特征分布后对 INT8 舍入更敏感，
"蒸馏+量化"叠加非无损叠加（报告误差分析节的素材）。任务书量化达标线（≤2%）仍满足；
**实验 4 部署推荐仍为 `a2_int8_val346.onnx`（0.420）**。结果见 `exp3/results/a2_distilled_int8.json`。

## 6. 消融（已完成，2026-10-26）

同一 Notebook 连跑三组 `--dis`（各约 17 分钟）：

```bash
!python distill_yolo.py --device 0 --epochs 12 --dis 3  --name a2_distill_dis3
!python distill_yolo.py --device 0 --epochs 12 --dis 9  --name a2_distill_dis9
```

**结果（test 380，与主跑 dis=6 同口径）**：

| dis | 3 | 6（主跑） | 9 | 未蒸馏 A2 | 教师 M1 |
|---|---|---|---|---|---|
| mAP50 | 0.420 | 0.418 | **0.422** | 0.419 | 0.424 |
| mAP50-95 | 0.246 | 0.245 | **0.247** | 0.245 | — |

结论：单类检测下 logit-KL 信息弱，特征蒸馏项可以承载更大权重——**dis=9 最优**，
学生严格超过未蒸馏基线（+0.3pp），距教师仅 -0.2pp，任务书"损失≤1% 且优于同量级
未蒸馏模型"双达标。报告最终蒸馏配置推荐 dis=9（`exp3/models/a2_distill_dis9.pt`）。
结果 JSON：`a2_distill_dis3.json` / `a2_distill_dis9.json`，对比图 `fig5_distill.png`。

## 7. 常见坑

| 症状 | 处置 |
|---|---|
| `pip` 装不上库 | Settings 里 Internet 没开 |
| `distill_model` 参数不识别 | ultralytics 版本不是 8.4.176，重跑单元格 1 |
| CUDA OOM（基本不会，batch16 约占 6-8GB，T4 15GB 富余） | `--batch 8` 重跑 |
| labels 目录写 `.cache` 报错只读 | 单元格 2 的 mv 没执行，数据还在 /kaggle/input 下 |

## 8. 顺手给 P2：TensorRT 导出（可选）

蒸馏训完后同一 Notebook 里追加（产物交给 P2 测速）：

```bash
!pip install -q tensorrt
!yolo export model=runs/detect/exp3/runs/a2_distill/weights/best.pt format=engine half=True device=0 dynamic=True
!tar -rf /kaggle/working/distill_results.tar -C /kaggle/working runs/detect/exp3
```

装 tensorrt 失败就放弃（阶段 2 选做，P2 有 ONNX Runtime GPU 兜底），不影响主线。
