# 数据溯源（Data Provenance）

> 记录数据从原始到最终数据集的完整处理链路（每步的操作、参数、工具版本），
> 满足任务书"数据溯源"要求。运行各脚本后在下表追加一行。

## 处理链路

| # | 时间 | 步骤 | 脚本/工具 | 关键参数 | 输入→输出 | 操作人 |
|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | SportsMOT 下载（hf-mirror 镜像，官方 HF 仓库 `MCG-NJU/SportsMOT`，CC BY-NC 4.0） | scripts/01_acquire/download_sportsmot_hf.py | --parts train,val --workers 8 --chunk-mb 64 | hf-mirror → raw/sportsmot_hf/{train,val}.tar（6703191552 / 6592876544 字节，校验一致） | 【】 |
| 1b | 2026-09-30 | 篮球子集提取 | scripts/01_acquire/extract_basketball.py | splits_txt/basketball.txt | raw/sportsmot_hf/*.tar → raw/sportsmot/basketball/（30 个含 gt 序列；过滤 macOS `._*` 垃圾文件） | 【】 |
| 2 | 2026-09-30 | MOT→YOLO 转换+帧抽样 | scripts/01_acquire/mot_to_yolo.py | --every-n 5 --min-area 400 --sport basketball | raw/sportsmot → processed/vision（30 序列 / 4981 帧 / 45468 框，见 manifest.json） | 【】 |
| 3 | 2026-10-04 | 结构化 CSV 获取 | kagglehub（免账号下载 Kaggle 公开数据集） | dataset nathanlauga/nba-games | kaggle.com → raw/stats/（games/games_details/players/ranking/teams 共 5 表，113 MB；该线产物已于 10-13 清理删除，见 CLEANUP_LOG #1-#8） | 【】 |
| 4 | 2026-10-04 | 文本爬取 | scripts/01_acquire/crawl_basketball_news.py | --delay 2 --urls-file crawl_urls.txt | 新浪体育（历史 28 篇）+ 直播吧（当日 100 篇）→ raw/texts/（.txt + all_pages.jsonl + crawl_meta.json） | 【】 |
| 5 | 2026-10-04 | 结构化清洗 | scripts/02_clean/clean_structured.py | --iqr-k 3.0 | raw/stats 5 表 → processed/structured/*_clean.csv（缺失全部填充；IQR 截断异常值 324073 个；games_details 去重删 8944 行；见 clean_metrics_*.json） | 【】 |
| 6 | 2026-10-04 | 图像清洗 | scripts/02_clean/clean_images.py | --hash-th 6 | processed/vision：4981 帧，损坏 0、EXIF 清除 0、近重复隔离 2460、标注越界 0、保留 2521（见 clean_metrics.json） | 【】 |
| 7 | 2026-10-04 | 文本清洗 | scripts/02_clean/clean_texts.py | --min-chars 50 | raw/texts 122 篇 → processed/texts 122 篇（56454→56450 字符，耗时 0.29s，见 clean_metrics.json） | 【】 |
| 8 | 2026-10-04 | 自动化策展 | scripts/02_clean/run_dj.py（dj-process 1.6.0，6 算子） | np=4, executor_type=default | raw/texts/all_pages.jsonl → dj_workspace/<job>/dj_output.jsonl（122→120 篇，MinHash 去重 2 篇，总耗时 134s） | 【】 |
| 9 | 2026-10-04 | 结构化增强 | scripts/03_augment/augment_structured.py | 衍生特征+MinMax | games_details_clean → augmented（新增 three_point_pct/free_throw_pct/rebounds_total，归一化 22 列；其余表无匹配列跳过衍生，见 augment_log.json） | 【】 |
| 10 | 2026-10-04 | 图像增强（框同步） | scripts/03_augment/augment_images.py | --times 1 --seed 42 | 2521 帧 → +2521 增强副本（共 5042），torchvision v2 模式（水平翻转+仿射平移缩放+色彩抖动，框同步变换），仿射致框过小/出画丢弃 51 个，见 augment_log.json | 【】 |
| 11 | 2026-10-04 | 标准化+8:1:1 划分 | scripts/04_standardize/standardize_and_split.py | --imgsz 640 --seed 42 | 视觉按序列划分（30 序列：24/3/3；5042 图：4316/346/380）→ splits/yolo 标准目录；结构化 5 表与文本 120 篇按行划分（见 split_summary.json） | 【】 |
| 12 | 2026-10-04 | 质量报告 + 加载器验证 | scripts/05_evaluate/quality_report.py; src/basketball_dataset.py | 四维评分 | docs/quality_report.md（完整性 100/一致性 100/代表性 81.2/时效性 90，综合 92.8）；PyTorch Dataset 冒烟通过（batch 8×3×640×640，变长框合并正常） | 【】 |
| 13 | 2026-10-11 | MultiSports 下载（HF 门控仓库 `MCG-NJU/MultiSports`，CC BY-NC 4.0） | scripts/01_acquire/download_multisports_hf.py | Bearer token 直连 huggingface.co；64MB 分段×8 并发 | HF → raw/multisports/trainval.tar（15.55GB，仅 trainval：test 无 GT 免下省 6.8GB） | 【】 |
| 14 | 2026-10-11 | MultiSports 解压+视频清洗 | scripts/02_clean/clean_multisports.py | 首中尾帧解码、帧数±2 对 GT、分辨率、fps≈25 | tar → extract/basketball 526 段 mp4（train 379/val 147）；**526/526 全过、0 丢弃**（clean_metrics.json） | 【】 |
| 15 | 2026-10-11 | GT 标注 → 事件表 | scripts/01_acquire/multisports_to_events.py | @25fps 换算秒 | multisports_GT.pkl → processed/multisports/events.csv（6247 动作实例：视频/split/动作/起止帧与秒/框/中心点） | 【】 |
| 16 | 2026-10-11 | tube 帧 → YOLO 检测帧 | scripts/01_acquire/multisports_to_yolo.py | --every-n 12（2fps）、仅取有 tube 标注帧 | 379 段 train 视频 → processed/vision_ms（7746 帧/9094 框，convert_metrics.json） | 【】 |
| 17 | 2026-10-11~12 | 解说语料爬取（直播吧文字直播缓存接口） | scripts/01_acquire/crawl_zhibo8_livetext.py | 0.5s/页、3 并发、断点续爬、课程 UA、绕系统代理 | 接口 `dingshi4pc.qiumibao.com/livetext/.../page_10/{n}.htm`；70 个季前赛 ID（26 场有解说/32 场未开打）+此前场次 → raw/texts/livetext（41 场非空，40,923 条，crawl_meta.json 记来源） | 【】 |
| 18 | 2026-10-13 | 解说清洗+按场次 8:1:1 | scripts/02_clean/clean_livetext.py | seed=42、按场次划分防同场泄漏 | 40,923 → 40,376 条（去空 386/超短 159/重复 1）；33 场 32,377 / 4 场 4,889 / 4 场 3,110 → processed/texts/livetext/ | 【】 |
| 19 | 2026-10-13 | 实验 2 数据就绪+冒烟 | scripts/03_train/train_yolo.py | data.yaml / data_ablation.yaml / original_train.txt(2158) | CPU 冒烟 A1/A2 管道通过（val 346 图 3104 框全解析）；打包 exp2_colab_pkg.tar(818M) 待上云 | 【】 |
| — | 2026-10-13 | **数据清理（结构化线删除、原始包清理）** | 见 docs/CLEANUP_LOG.md #1-#8 | 用户确认 | 释放 34G+689M；全部可按日志中"重建方式"复现 | 【】 |

### 获取过程问题与解决（报告"问题与解决"素材）

1. **官方申请渠道无响应**：GitHub 页面的 Google Form 申请需人工审批、周期不定。
   解决：改用官方作者组上传的 HuggingFace 仓库（非门控），经 hf-mirror.com 镜像下载，无需审批。
2. **本机无法访问外网**：Clash TUN 模式接管 DNS（域名全部解析为 198.18.x.x fake-ip），
   且其代理节点失效，导致 GitHub / hf-mirror 全部超时。
   解决：经 AliDNS DoH（223.5.5.5）查询 hf-mirror.com 真实 IP（160.16.86.14），
   用 `curl --resolve` 钉住真实 IP 绕过 fake-ip 劫持直连（download_sportsmot_hf.py 自动检测并处理）。
3. **下载中途被动态 RST 阻断**：train.tar 完成后，val.tar 下到 78/100 分段时连接被重置
   （TCP 可握手、发数据即断）。
   解决：脚本按 64 MB 分段断点续传 + resume_download.sh 每 5 分钟探测恢复自动续传，约 1 小时后阻断解除完成下载。
4. **tar 内混有 macOS AppleDouble 文件**（`._*.jpg`）：按字典序排在真图像前，导致首帧校验失败。
   解决：提取与转换脚本均过滤 `._*` 文件。
5. **爬虫 UA 含中文导致全部请求失败**：HTTP 头仅允许 latin-1，`+课程作业用途` 抛 UnicodeEncodeError。
   解决：UA 改为纯 ASCII（用途写入注释与文档）。
6. **新浪 GBK 编码乱码**：响应头无 charset，requests 按 ISO-8859-1 解码得到乱码。
   解决：编码为 latin-1 系时改用 apparent_encoding 自动探测。
7. **网易 robots.txt 返回 403**：Python RobotFileParser 对 401/403 采取保守策略（全部禁止），
   尽管RFC 9309将4xx视为允许，仍按更严格解释执行，弃用网易文章。
8. **新浪频道页静态 HTML 只有 2024-2025 旧文**：最新文章由 JS 异步加载，静态抓取拿不到。
   解决：改用服务端渲染的直播吧（news.zhibo8.com，robots 404=允许）获取当日最新资讯。
9. **torch/torchvision 导入即崩（WinError 1114）**：Windows 事件日志定位到崩溃模块为
   msvcp140.dll 14.27（2020 年版）——全机安装的 D:\Anaconda 自带旧运行库且先于 System32 命中，
   torch 2.14 绑定旧版后初始化失败。图像增强自动降级为 PIL 模式；
   Data-Juicer 强依赖 torch，编写 run_dj.py 在导入前显式预加载新版 msvcp140.dll（vendor/ 下 14.50 副本）修复。
   （根治需管理员权限更新 D:\Anaconda 下的 VC 运行库，或改用官方 python 重建 venv。）
10. **py-data-juicer 1.6.0 兼容性三连**：① 入口命令 dj-ce 已移除，改为 dj-process；
    ② process 段必须为"单键字典列表"（裸算子名会解析失败）；③ dataset_path 标量被误判为
    HuggingFace 数据集，须用结构化 dataset.configs[type=local,path=...]；
    ④ Windows 上日志文件名由 relpath(export_path, work_dir) 拼接，需将 work_dir/export_path
    都放进 {job_id} 占位目录，否则报 FileNotFoundError。
11. **selectolax 1.0.0 与 clean_html_mapper 不兼容**：1.0 移除 modest 后端（selectolax.parser 抛
    ImportError），异常被批量包装器吞掉导致数据集被静默清空（122→0）。
    解决：降级 selectolax==0.3.28（requirements.txt 已加 selectolax<1.0）。
12. **Data-Juicer 默认 ray 执行器**：1.6.0 默认 executor_type=ray_partitioned 并自动安装 ray 失败。
    解决：配置 executor_type: default（单机默认执行器），无需 ray。
13. **PyTorch Dataset labels 路径错误**：basketball_dataset.py 将 labels 目录算成
    images/labels/<split>（少上跳一级），导致数据集长度为 0。
    解决：改为 YOLO 标准结构 yolo/{images,labels}/<split> 的 parent.parent 推导，冒烟测试通过。
14. **torchvision v2 增强的坐标系统 bug**：augment_v2 把 YOLO 归一化坐标当像素坐标送入
    BoundingBoxes（未乘图像宽高），仿射后框全部塌缩到一点、产出无效标注。
    解决：入参乘 W/H 转像素 XYXY、变换后除回；出画/过小框按 0.2% 边长阈值丢弃。
    （永久修复 VC 运行库后 v2 模式首次启用时发现，PIL 降级路径不受影响。）
15. **HF 门控仓库 401**：MultiSports 为 gated repo，hf-mirror 镜像不转发 Authorization 头，镜像下载必 401。
    解决：携带 Bearer token 直连 huggingface.co（token 仅经环境变量使用，未写入任何文件）。
16. **urllib 走 Clash 系统代理极慢**：文字直播爬虫单页可达分钟级（curl 直连仅 0.5s）。
    解决：`urllib.request.ProxyHandler({})` 构建绕过系统代理的 opener。
17. **直播吧接口对超范围页码"夹取"**：页码超出后返回末页而非空页，爬虫疑似无限翻页。
    解决：整页 live_id 与已爬集合完全重复即终止 + 200 页硬上限（后核实大场次 300-1700+ 条均为真实分页）。
18. **MultiSports GT 的 split 列表嵌套**（train_videos 为 list of lists）：直接迭代致 TypeError unhashable。
    解决：展平一层后再处理。
19. **ultralytics 对 txt 训练清单按运行目录解析相对路径**：消融清单用相对路径时标签全部配不上（No labels found）。
    解决：train_yolo.py 训练前自动生成绝对路径清单（换机器重跑自动适配）。

## 环境版本
- Python：【3.12.x】（conda env: basketball）
- 关键库版本：【pandas / opencv-python / torchvision / py-data-juicer，运行 `pip freeze > docs/versions.txt` 贴入】

## 数据血缘示意（v2.0，2026-10-13 起生效；旧线血统见上表 #1-#12）

```
MultiSports HF 门控仓库 ──(download #13)──> trainval.tar ──(解压+视频清洗 #14)──> extract/ 526 段 + GT pkl
      ├──(#15 multisports_to_events)──> processed/multisports/events.csv（6247 实例：画面事件结构层）
      └──(#16 multisports_to_yolo)──> processed/vision_ms（7746 帧检测补充数据）

SportsMOT（血统 #1b-#2，原始包已清理可重建）──(#6 清洗 + #10 框同步增强 + #11 标准化 8:1:1)──> splits/yolo/（4316/346/380，实验 2 主数据集）

直播吧文字直播接口 ──(#17 爬取 41 场)──> raw/texts/livetext ──(#18 清洗+按场次 8:1:1)──> processed/texts/livetext（40,376 条三分卷）

（已删线：Kaggle 五表 #3/#5/#9 —— CSV 已删，指标 json 存档，重建见 CLEANUP_LOG #7）
```
