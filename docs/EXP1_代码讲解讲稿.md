# 实验 1 代码讲解讲稿（含全量复现核验）

> 生成：2026-11-09。配套当日全量复跑核验，所有数字均已二次确认（见第 4 节）。
> 讲解模板：每个脚本按「一句话职责 → 输入→核心三步→输出 → 落盘证据 → 答辩点」90 秒讲完。

## 0. 开场（30 秒）

> 实验 1 是整条"篮球 AI 解说员"流水线的地基：一条**五阶段流水线**（获取→清洗→增强→标准化→评估），
> 三条**数据线**各自走完全程——视频线（MultiSports 526 段）、图像线（SportsMOT 30 个序列）、
> 文本线（直播吧解说 4 万余条 + 资讯 122 篇）。
> 三个设计信条贯穿全部代码：**防泄漏**（按序列/场次划分）、**可追溯**（每步指标落盘 JSON）、
> **面向真实环境的健壮性**（断点续传、限速、依赖降级，全是真实踩坑）。

## 1. 全景表（可直接做 PPT 一页）

| 阶段 | 脚本 | 一句话职责 | 关键产出（数字） |
|---|---|---|---|
| 获取 | `download_multisports_hf.py` | 门控仓库 Bearer 直连 + 分段断点续传 | trainval 15.55GB |
| 获取 | `download_sportsmot_hf.py` | 镜像分段下载 + fake-ip 检测钉真实 IP | train+val 共约 13.3GB |
| 获取 | `extract_basketball.py` | 从 tar 只解出篮球序列 | 30 序列 |
| 获取 | `mot_to_yolo.py` | MOT→YOLO 转换、每 5 帧抽样 | 4981 帧 / 45468 框 |
| 获取 | `multisports_to_yolo.py` | mp4 抽帧 + tube 框（补充源） | 7746 帧 / 9094 框 |
| 获取 | `multisports_to_events.py` | GT pkl→事件表 CSV | 6247 个动作实例 |
| 获取 | `crawl_zhibo8_livetext.py` | 接口逆向 + 防死循环 + 合规限速 | 41 场 / 40,923 条 |
| 获取 | `crawl_basketball_news.py` | robots 检查 + 2s 限速资讯爬取 | 122 篇 |
| 清洗 | `clean_multisports.py` | 首中尾帧解码、帧数/分辨率对齐 GT | 526→526（0 剔除） |
| 清洗 | `clean_images.py` | 损坏/EXIF/感知哈希去重/标注校验 | 4981→2521（剔重 49.4%） |
| 清洗 | `clean_livetext.py` | 33 字段→5 字段、去重去碎片、按场次划分 | 40,923→40,376 |
| 清洗 | `clean_texts.py` + `run_dj.py` | 手工 vs Data-Juicer 六算子对比 | 0.29s vs 134s；122→120 |
| 增强 | `augment_images.py` | 框同步几何/色彩增强 | 2521→5042 |
| 标准化 | `standardize_and_split.py` | 统一 640×640、按序列 8:1:1 | 4316/346/380（24/3/3 序列） |
| 评估 | `quality_report.py` | 四维质量评分 | 综合 92.8/100 |
| 封装 | `src/basketball_dataset.py` | PyTorch Dataset + 变长 collate | 训练直接可用 |

## 2. 逐脚本讲稿

### 2.1 两个下载器（一起讲，对比着讲）

**开头**：15GB 级文件，核心是同一套"分段断点续传"骨架——先把远端大小探出来，切成 64MB 分段，
每段 Range 请求写 `.tmp`，**校验字节数后才原子改名**（磁盘上永远只有完整分段），8 线程并发、
失败补漏重跑、最后按偏移拼接再校验总大小。断点续传 = 直接重跑，已完成的分段秒跳过。

**两个脚本的差异全是真实网络对抗**：
- MultiSports 是 **门控仓库**：hf-mirror 不转发 Authorization → 401。对策：带 Bearer token
  **直连官方域名**，token 只走环境变量不落盘（`download_multisports_hf.py:34`）。
- SportsMOT 走镜像，但本机 **Clash TUN 劫持 DNS**（解析到 198.18 fake-ip）→
  `socket.getaddrinfo` 检测 198.18 网段，命中就用 `curl --resolve` 把域名钉在真实 IP
  （`download_sportsmot_hf.py:48`）。这就是它用 curl 子进程而非 requests 的原因。

**答辩点**：为什么 64MB？——粒度权衡：太小则分段数过多、管理开销大；太大则单段失败重传代价高。

### 2.2 extract_basketball.py

tar 流式遍历，只解出 `splits_txt/basketball.txt` 点名的序列；顺手过滤 macOS `._` 元数据文件；
tar 根前缀导致多嵌一层目录时自动拍平。**讲解点**：不全解压 12GB，只要 30 个篮球序列。

### 2.3 mot_to_yolo.py（图像线主转换）

输入 MOT 格式 `gt.txt`（`frame,id,x,y,w,h,...`）。四步：
1. 每 5 帧抽 1（相邻帧太像）；面积 <400px² 的小框丢弃；可见度列可选过滤；
2. 像素坐标 → YOLO 归一化 `cx,cy,w,h`（除以首帧实测宽高，`mot_to_yolo.py:100`）；
3. **无标注帧直接跳过**——MOT 没框≠没人，放进去会把真球员教成背景（假阴性）；
4. 文件名 `<序列>__f帧号` 防冲突 + **manifest.json 记录每序列帧数/框数**（=后面按序列划分的依据）。

### 2.4 multisports_to_yolo.py（视频线补充源）

mp4 每 12 帧取 1（≈2fps），跳过的帧 `cap.grab()` **不解码**省 CPU；GT tube 离线展开成
`视频→{帧号→[框]}`。关键口径：**只保留被 tube 覆盖的帧**（MultiSports 只标做动作的球员，
无标注帧里的大量球员会被当背景）。所以它自我定位是"补充源"不是替代。

### 2.5 multisports_to_events.py（实验 5 的原料）

每个动作 tube 展成一行 CSV：视频/动作/起止帧秒/起始帧框坐标+归一化中心。内建清洗：
帧号越界、退化框（<2px 或 <400px²）、<2 帧的 tube 丢弃，**丢弃原因 Counter 落盘**。
产出 6247 行 `events.csv`（本次复跑与仓库版**逐字节一致**）。

### 2.6 crawl_zhibo8_livetext.py（最精彩的爬虫）

链路是页面 JS 逆向出来的：比赛页内联配置拿 `saishi_id` → 数据接口
`.../livetext/{id}/0/page_10/{页码}.htm`（页码 10 的倍数、每页 ≤10 条、33 字段）。四个讲解点：
1. **防翻页死循环**（必讲）：接口对超界页码**不返回 404 而是夹取末页** → 对策：每页按
   `live_id` 去重，**整页全已见即判到头** + 200 页硬上限双保险（`crawl_zhibo8_livetext.py:65`）；
2. `ProxyHandler({})` 空代理 opener 直连，绕开拖慢 CDN 的系统代理；
3. 合规：先查 robots、每页 0.5s + 3 并发、UA 带课程标识、`crawl_meta.json` 全量溯源；
4. 断点续爬：jsonl 已存在非空即跳过，中断重跑无害。

### 2.7 crawl_basketball_news.py

robots.txt 自动检查（163.com 返回 403 → 保守视为禁止、整域不爬）；2s 限速；GBK 编码自动探测
（新浪不返回 charset，`resp.apparent_encoding` 兜底）。

### 2.8 清洗四件套（统一约定：不合格进 quarantine/，前后指标落盘 clean_metrics.json）

- `clean_multisports.py`：每段 mp4 首/中/尾三帧**真实解码**（不信容器 header）、帧数 ±2 对齐 GT、
  分辨率/帧率核对。526→526。复跑 49 秒。
- `clean_images.py`：单次遍历四步——损坏检测（强制解码）、**EXIF 重写抹除**（隐私）、
  **phash 感知哈希去重**（汉明距离 ≤6 隔离；imagehash 缺失降级自实现 dhash）、
  标注校验（5 列 / 坐标 ∈[0,1]）。4981→2521，剔重 49.4%——篮球相邻帧实在太像。
- `clean_livetext.py`：33 字段→5 字段；去空/纯表情（正则查不到汉字字母数字）/长度 <4/
  `(场次,文本,时间)` 三元组去重；**按场次 8:1:1 划分在这里就做了**（同场不跨集合）。
- `clean_texts.py` + `run_dj.py` + `configs/data_juicer_text.yaml`：任务书要求的
  **自动化 vs 手工效率对比**。手工 0.29s（纯规则：HTML 实体/URL 邮箱/不可见字符/全角转半角/
  空白规范化）；DJ 六算子 134s（clean_html、whitespace、中文语言识别、长度、邮箱、
  MinHash 字符级去重）。结论：小语料手工快两个数量级，DJ 价值在算子可组合、流程可复现。
  `run_dj.py` 是个 DLL 兼容包装器：Anaconda 旧版 msvcp140.dll 抢先加载导致 torch
  WinError 1114 → ctypes 在任何扩展导入前预加载 `vendor/` 新版运行库。

### 2.9 augment_images.py（含全项目最大的一次事故，建议主动讲）

检测增强的难点是**框必须跟着图一起变**。实现：torchvision transforms v2，
框装进 `tv_tensors.BoundingBoxes` 和 PIL 图像**过同一个 transform**（翻转 p=0.5 +
RandomAffine ±5%/±10% + ColorJitter）；YOLO 归一化坐标**先乘宽高进、变换完再除回**
（少这步框会塌缩到原点）；变换后 <0.2% 边长或出画的框丢弃并计数；副本命名 `_aug0`
落原图旁——为下一步"按序列划分"的防泄漏埋伏笔。

**事故故事（加分项，体现数据为中心的严谨）**：torchvision 0.29 下 numpy 图像传入 v2
变换会出现"**框被变换、图像原样返回**"（复现像素差 0.00）——当年 2521 张 `_aug0` 副本
全是"原图+错位标注"，潜伏到实验 3 复核才暴露（模型在这批图上 mAP50 仅 0.095），
连带勘误实验 2"增强 +4.7pp"的结论（训练与评测同源污染伪影）。修复 = 第 73 行注释：
**必须传 PIL**。2026-11-08 已用修复版重新生成 `_aug0`（三层验收：像素差>0 / IoU 中位
0.960 / 合成单测 0.93+），坏副本归档 `data/archive/exp1_aug0_broken/`。

### 2.10 standardize_and_split.py（防泄漏是全场主旨）

1. 统一 640×640（LANCZOS）；归一化框坐标不随缩放变 → 标签原样复制；
2. **shuffle 的是 30 个序列而不是 5000 张图**（`standardize_and_split.py:55`）：从文件名
   `__` 前缀还原序列名，同序列全部帧（含 `_aug0` 副本）落同一侧——相邻帧几乎一样，
   按帧随机切会让 train/test 近乎重复，验证指标虚高；
3. 输出标准 YOLO 目录 + `split_summary.json`。seed=42 完全可复现（本次已验证）。

### 2.11 basketball_dataset.py + quality_report.py

- Dataset：`images/<split>/` 上两级找 `labels/<split>/`；返回 dict（image/boxes/classes）；
  每图球员数不同 → 自定义 `collate_fn` 把变长框按**列表**堆叠。跑通即验证数据格式。
- quality_report：汇总各阶段 metrics 打四维分——完整性 100、一致性 100、
  代表性 **81.2**（30 序列帧数分布**基尼系数 0.188**，(1-基尼)×100）、时效性 90 → **92.8**。
  启发式规则写明在报告里。

## 3. 现场演示方案（已全部实测通过的命令）

**结论：不需要每一部分都现场跑。** 演示原则——跑「快、无网络、可视化强」的 5 个，
重环节放落盘指标和日志，下载/爬取讲代码+溯源文档（绝不当场爬网站）。

先激活环境：`.venv\Scripts\activate`，在仓库根目录执行。**所有命令都带 `--out-dir` 指向临时目录**，
不会覆盖 `data/processed/` 下的正式产物（耗时为 2026-11-09 本机实测）：

| # | 现场演示 | 命令 | 实测耗时 | 预期输出 |
|---|---|---|---|---|
| 1 | 事件表转换 | `python scripts/01_acquire/multisports_to_events.py --out-dir .report_build/demo/ev` | 0.9s | `6247 行 / 原始 6247 个 tube，丢弃 0`；split `{'val': 1715, 'train': 4532}` |
| 2 | 解说清洗+划分 | `python scripts/02_clean/clean_livetext.py --out-dir .report_build/demo/lt` | 2.5s | `40923 -> 40376 条（41 场）`；train 33 场/val 4/test 4 |
| 3 | 增强框同步 | `python scripts/03_augment/augment_images.py --vision-dir .report_build/exp1_demo/aug_demo --times 1` 后接 `python .report_build/exp1_demo/draw_aug_compare.py` | 13.6s（多为加载 torch） | 生成 `aug_sync_demo.png`：增强后框仍套住同一名球员 |
| 4 | Dataset 加载 | `python src/basketball_dataset.py` | 8.2s | `数据集规模: 4316`；`图像张量: (3, 640, 640)，框数: 10` |
| 5 | 视频清洗 | `python scripts/02_clean/clean_multisports.py --out-dir .report_build/demo/ms` | 49s | `526 段 -> 保留 526，剔除 0` |

另有一个**清洗隔离演示**素材：`.report_build/exp1_demo/clean_demo/`（3 张合成图：1 张正常、
1 张近重复、1 张坐标越界标注）——跑 `clean_images.py --vision-dir` 后近重复和坏标注两张被移进
`quarantine/`，指标 `near_duplicates 1 / bad_labels 1 / kept 1`。已经跑过一次，想重演就把
`quarantine/` 里的文件移回 `images/`、`labels/`。

⚠️ `standardize_and_split.py` 与 `quality_report.py` **没有输出目录参数**，直接运行会覆盖
`data/splits/` 和 `docs/quality_report.md`。演示 quality_report 请用重定向写法：

```bash
python -c "import sys; sys.path.insert(0,'scripts/05_evaluate'); import quality_report as q; from pathlib import Path; q.OUT=Path('.report_build/demo/qr.md'); q.main()"
```

**不现场跑、用证据讲**：两个下载器（22GB、要 token/网络）→ 讲代码 + tar 字节数对账
（train.tar 6,703,191,552 字节与脚本内远端记录一致）；两个爬虫（别对真实网站现场爬）→
讲代码 + `crawl_meta.json` / 195 个 jsonl（41 场 40,923 条）；Data-Juicer（3 分钟+）
→ 讲配置 yaml + 两次输出对比一致。

## 4. 2026-11-09 全量复现核验结果（你可对照自己跑的数字）

| 环节 | 文档记录 | 本次复跑 | 结论 |
|---|---|---|---|
| mot_to_yolo | 30 序列 / 4981 帧 / 45468 框 | 30 / 4981 / 45468 | ✅ 完全一致 |
| clean_images | 4981→2521，剔重 2460 | 4981→2521，2460 | ✅ 完全一致 |
| augment_images | 2521→2521，丢框 51 | 2521→2521，丢框 **71** | ⚠️ 副本数恒定；丢框数随机（见下注） |
| standardize 划分 | 24/3/3 序列，4316/346/380 | 同左，序列分配推算验证完全一致 | ✅ 完全一致 |
| multisports_to_events | 6247 tube→6247，丢弃 0 | 同左，`events.csv` **逐字节一致** | ✅ 完全一致 |
| clean_livetext | 40923→40376（386/159/1/1），33/4/4 场 | 同左，`commentary.jsonl` **逐字节一致** | ✅ 完全一致 |
| clean_multisports | 526→526，0 剔除 | 526→526（49s） | ✅ 完全一致 |
| clean_texts | 122→122，0.29s | 122→122，0.29s | ✅ 完全一致 |
| Data-Juicer | 122→120，任务 134s | 122→120，任务 171s，输出与上次一致 | ✅ 结果一致（耗时含预热差异） |
| multisports_to_yolo | 379 视频 / 16597 采样 / 7746 保留 / 9094 框 | 仅用 GT pkl 解析法推算（不解码视频）：同四数字 | ✅ 完全一致 |
| quality_report | 92.8/100 | 复算一致（除生成时间行） | ✅ 完全一致 |
| 下载产物 | — | train/val.tar 字节数与远端记录一致；526 mp4 在位 | ✅ 完整 |

> **注（augment 丢框 51→71 的原因）**：`augment_images.py` 只固定了 python/numpy 随机种子，
> 而 torchvision v2 的翻转/仿射采样走 **torch 自己的 RNG**，脚本未调 `torch.manual_seed`，
> 因此两次运行采到的平移/缩放不同、出画丢框数不同（51 vs 71）。副本数量恒为 2521，
> 划分结果不受影响。若要逐位可复现，可在脚本里加一行 `torch.manual_seed(args.seed)`——
> 这本身就是一个可以现场讲的"可复现性"细节。

> **注（README"val 含 3104 框"）**：那是 v1 历史 val（346 帧 = 173 原始 + 173 错位副本）的
> 框总数：原始帧 1557 + 副本 1547 = 3104。现在干净口径 val 只有 173 原始帧、1557 框
> （注意：标签文件末行无换行符，`wc -l` 会少计，要用按行解析统计）。

**全链路复现耗时参考**：检测数据四步链（转换→清洗→增强→划分）约 15 分钟、约 2.7GB 临时产物。

## 5. 高频答辩问题与答法

1. **"你们怎么保证没有数据泄漏？"** —— 图像按**序列**划分、解说按**场次**划分，同一比赛
   内容绝不跨 train/val/test；增强副本 `_aug0` 跟随原帧同侧；划分 seed=42 可复现，
   本次复跑验证序列分配与仓库现网完全一致。
2. **"清洗剔了一半图像，不心疼吗？"** —— 剔的 49.4% 是感知哈希近重复（汉明距离 ≤6），
   留着只会让模型过拟合到重复帧、虚高指标；quality_report 一致性 100 分正来自"保留集内重复 0"。
3. **"增强带来了多少收益？"** —— 诚实回答：初测 +4.7pp 后来发现是 `_aug0` 错位标注的
   同源污染伪影，干净口径下增强收益为负——这正是任务书提示要避免的"无效增强"案例，
   我们把它做成了数据质量教学案例（实验 3 勘误节）。
4. **"爬数据合规吗？"** —— robots.txt 检查（163.com 403 整域放弃）、限速 0.5–2s、
   课程 UA、来源落盘 `crawl_meta.json`、语料仅课程内部使用不再分发。
5. **"为什么文本不做同义替换增强？"** —— 解说语义敏感，替换会失真；文本线的价值在
   实验 5 的"事件—解说"指令对与 RAG。
6. **"这 92.8 分怎么算的？"** —— 四维启发式：完整性（每 1% 缺失扣 10 分）、一致性
   （尺寸统一+集内重复 0）、代表性（序列帧数基尼 0.188→81.2）、时效性（近年数据集+采集时间记录）；
   规则全部写明，可复核。
