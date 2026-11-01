"""CPU-only Experiment3 report. Numbers come from real result JSON."""
import json,html,re,hashlib
from pathlib import Path
from PIL import Image as PILImage
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
P=Path(__file__).resolve().parents[1]
def load(f):return json.loads(Path(f).read_text(encoding='utf-8'))
def main():
 rows=load(P/'results/cpu_comparison.json');rec=load(P/'results/cpu_recommendation.json');env=load(P/'results/environment.json');lock=load(P/'results/selection_lock.json');assert load(P/'results/verification_cpu.json')['passed']
 base=rec['baseline_result'];best=rec['recommended_result']
 pdfmetrics.registerFont(TTFont('Song','C:/Windows/Fonts/simsun.ttc'));pdfmetrics.registerFont(TTFont('Hei','C:/Windows/Fonts/simhei.ttf'));pdfmetrics.registerFont(TTFont('TNR','C:/Windows/Fonts/times.ttf'));pdfmetrics.registerFont(TTFont('TNRB','C:/Windows/Fonts/timesbd.ttf'))
 st={k:ParagraphStyle(k,fontName=f,fontSize=z,leading=l,spaceAfter=s,wordWrap='CJK',keepWithNext=k in ['h','sub']) for k,f,z,l,s in [('body','Song',12,20,7),('small','Song',10.5,16,6),('h','Hei',16,24,12),('sub','Hei',13,20,8),('cell','Song',10,14,0),('center','Song',14,24,12),('cover','Hei',24,36,20)]};st['center'].alignment=1;st['cover'].alignment=1
 W=A4[0]-112;story=[];md=[]
 def fmt(s,bold=False):return ''.join('<font name="'+('TNRB' if bold else 'TNR')+'">'+html.escape(t)+'</font>' if t and all(ord(ch)<128 for ch in t) else html.escape(t) for t in re.split(r'([\x20-\x7e]+)',str(s)))
 def para(t,k='body'):story.append(Paragraph(fmt(t,k in ['h','sub','cover']),st[k]));md.append(str(t)+'\n')
 def title(t):para(t,'h')
 def sub(t):para(t,'sub')
 def page():story.append(PageBreak())
 def table(head,data,widths=None):
  t=Table([[Paragraph(fmt(x),st['cell']) for x in r] for r in [head]+data],colWidths=widths or [W/len(head)]*len(head),repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#999999')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,8)]);md.extend(['| '+' | '.join(map(str,head))+' |','|'+'---|'*len(head),*['| '+' | '.join(map(str,r))+' |' for r in data],''])
 def pic(n,width=W):
  f=P/'reports/assets'/n;i=PILImage.open(f);story.extend([Image(str(f),width=width,height=width*i.height/i.width),Spacer(1,5)]);md.append('![](assets/'+n+')\n')
 def num(x):return 'N/A' if x is None else f'{x:.2f}'
 def pc(x):return 'N/A' if x is None else num(x*100)
 def label(m):
  if 'cpu_resolution' in m:return 'CPU尺寸/布局调优版'
  if 'cpu_tuned' in m:return 'CPU执行调优版'
  if 'openvino' in m:return 'OV INT8+DFL浮点' if 'dflfp32' in m else 'OV INT8' if 'int8' in m else 'OV FP32'
  if 'reg2fp32' in m:return 'E9 回归末两层浮点'
  if 'reglastfp32' in m:return 'E8 回归输出层浮点'
  if 'dflfp32' in m:return 'E7 DFL浮点'
  if 'avx2' in m:return 'E6 AVX2数值范围'
  if 'train1000_pc' in m:return 'E4 训练1000逐通道'
  if 'train1000_pt' in m:return 'E3 训练1000逐张量'
  if 'train500' in m:return 'E2 训练500逐张量'
  if 'val173' in m:return 'E1 验证173逐张量'
  return 'FP16 ONNX' if 'fp16' in m else 'FP32 ONNX'
 # 1
 story.append(Spacer(1,42));para('西 安 邮 电 大 学','center');story.append(Spacer(1,28));para('AI全栈开发实验','cover');para('题目  算法优化实验','center');para('基于实验二模型的CPU推理优化','center');story.append(Spacer(1,20));para('组号  17','center');table(['学号','姓名','分工'],[['2610321173','高晓琦',''],['2610321160','王亿荣',''],['2610321144','杨文超',''],['2610321212','黄琛聪',''],['2610321071','牛翼帆',''],['2610321088','刘大勇','']],[W*.35,W*.25,W*.40]);story.append(Spacer(1,22));para('时间  2026年10月26日','center')
 # 2
 page();title('一 实验目的');para('以实验二A2 YOLOv8n已训练权重在CPU上的运行结果为基线，实施3.1.4 CPU推理加速并逐项验证任务目标。通过ONNX导出、ORT计算图优化、OpenVINO部署及INT8量化对照，验证同一CPU上精度、时延、吞吐量、模型体积与内存稳定性的变化，并提供可直接运行的CPU接口。')
 para('本实验的主要优化对象是模型执行与部署流程。浮点部署使用同一训练权重，不通过更换硬件计算加速比；量化版本单独分析精度代价。3.1.1量化作为补充的模型压缩实验，噪声测试用于诊断，不作为鲁棒性训练的完成证明。')
 title('二 实验环境');table(['项目','实际配置'],[['CPU',env['CPU']],['内存','系统可识别物理内存约'+num(env['RAM_GiB'])+' GiB'],['系统 / Python',env['OS']+'；Python '+env['python']],['模型加载框架','PyTorch '+env['torch'].split('+')[0]+'；torchvision '+env['torchvision'].split('+')[0]+'；Ultralytics '+env['ultralytics']],['CPU部署框架','ONNX '+env['onnx']+'；ONNX Runtime '+env['onnxruntime']+'；OpenVINO '+env['openvino'].split('-')[0]],['量化 / 评价','NNCF '+env['nncf']+'；pycocotools COCOeval bbox'],['执行约束','所有推理device=cpu；标准对照4线程、640输入；额外CPU线程/布局/尺寸调优见结果；OpenCV单线程']],[100,W-100])
 # 3
 page();title('三 实验内容与步骤');sub('3.1 基线模型与数据');para('原模型来自模型设计与训练.zip中的A2_yolov8n/weights/best.pt，检测类别为player。文件已与压缩包原件逐字节核对。参数量3,138,003，卷积/线性等价运算量约8.64 GFLOPs；推理部署未改变单类别检测任务。')
 para('原模型SHA256：2e8624bf93eba97a0adc7f899fbb8e4cd9fd90e42f6546c74f32cc9ba9134776。','small')
 table(['集合','原始图片数','本实验用途'],[['train','2158','INT8校准，使用排序后的前500或1000张'],['val','173','选择量化配置与精度保持候选'],['test','190','配置锁定后的最终精度验证；1792个标注框']],[80,100,W-180])
 para('使用原始图片及配套标签，保留实验二的集合身份。本次使用的校准与评测数据不含离线_aug副本，不把不一致的离线增强标签用于评价。历史划分含同源视频跨集合情况，因此结论限于该测试池和本机CPU，不能据此声称跨比赛泛化能力提升。')
 sub('3.2 比较方法');para('基线为原A2 PyTorch FP32的CPU推理。部署候选包括FP32 ONNX、FP16 ONNX、训练集校准INT8 ONNX，以及OpenVINO FP32/INT8的LATENCY与THROUGHPUT两种性能提示。所有版本使用同一letterbox规则、RGB归一化、NMS和原图坐标还原；标准对照输入640，尺寸调优配置另行标识。')
 # 4
 page();sub('3.3 CPU推理加速的实现');table(['环节','具体实现'],[['模型导出','eval模式、Conv-BN融合、ONNX opset17；输入空间640x640，batch维动态'],['ORT图优化','只注册CPUExecutionProvider；ORT_ENABLE_ALL；intra_op=4、inter_op=1'],['OpenVINO执行','compile_model(device=CPU)，INFERENCE_NUM_THREADS=4，INFERENCE_PRECISION_HINT=f32'],['性能提示对照','LATENCY和THROUGHPUT分别测量；均为同步调用，未模拟异步服务并发'],['统一输入与输出','BGR图像 -> letterbox -> RGB CHW float32/255 -> 推理 -> torchvision NMS -> 原图Nx6坐标'],['后处理','conf=.001、NMS IoU=.55、单类别、max_det=100；用户演示入口默认conf=.25'],['执行约束','Detector固定使用CPU；仅接受pt/onnx/xml格式，CLI与API不自动选择其他设备']],[100,W-100])
 para('额外CPU执行调优：对浮点模型比较2、4、8线程；PyTorch分支同时使用Conv-BN融合与channels_last布局。每个配置预热10次、单张计时30次，仅按时延筛选；选定配置再执行完整10/100/20计时、1000次稳定性和全量精度验证。基线与标准对照为4线程，调优版的实际线程数和布局单独记录，不能把收益完全归于计算图格式。另比较576与512输入，只用验证集AP50-95损失不超过1个百分点筛选；保持同一A2权重，将预测坐标正确还原到原图后评价。')
 sub('3.4 量化方案');para('静态量化使用ORT QDQ格式，校准卷积的权重和激活。比较逐张量与逐通道权重量化；非卷积算子保持浮点。针对定位敏感计算，保留DFL距离期望、回归输出层或回归分支末两层卷积的浮点精度。AVX2配置采用U8激活、S8权重及reduce_range，INT8权重存储中使用7位数值范围。')
 para('OpenVINO INT8采用NNCF MIXED预设和1000张原始训练图校准，并额外比较保留DFL浮点的版本。所有校准文件名与排除节点均写入quantization.json。FP16 ONNX作为浮点存储压缩对照，其CPU执行不保证快于FP32。FP16名称描述导出图精度，执行提供器仍为CPU。','small')
 # OpenVINO execution evidence
 page();sub('3.5 OpenVINO CPU部署与执行证据')
 para('本实验已实际完成OpenVINO模型转换、CPU编译、推理、全量测试集评价和独立进程复测。最终使用OpenVINO FP32、4个CPU线程、LATENCY性能提示，输入640x640。这里的工具完成情况由模型文件、实际调用与验证记录共同证明。')
 table(['证据项','实际内容'],[['工具版本','OpenVINO '+env['openvino'].split('-')[0]],['部署模型','models/a2_cpu_tuned/model.xml 与 model.bin'],['执行设备','CPU；INFERENCE_NUM_THREADS=4；INFERENCE_PRECISION_HINT=f32'],['实际编译调用','ov.Core().compile_model(model_path, CPU, 配置参数)'],['统一接口','scripts/resolution_runtime.py -> cpu_runtime.py -> infer.py；最终模型使用640输入与4线程配置'],['正式测速记录','results/bench_a2_cpu_tuned_LATENCY.json'],['独立进程复测','results/repeat_selected.json；配套原CPU基线repeat_baseline.json'],['检测精度记录','results/eval_a2_cpu_tuned_test.json；190张图片、1792个标注框'],['原生交叉核验','results/native_a2_cpu_tuned.json；device=cpu，原生model.val已实际运行'],['接口与来源检查','results/verification_cpu.json：原A2文件哈希、动态batch1/4/32、宽高比和预测一致性检查通过']],[110,W-110])
 for name in ['model.xml','model.bin']:
  f=P/'models/a2_cpu_tuned'/name
  para(name+'：'+str(f.stat().st_size)+' bytes；SHA256 '+hashlib.sha256(f.read_bytes()).hexdigest(),'small')
 para('该CPU调优目录与标准OpenVINO FP32 LAT配置使用相同FP32模型和4线程设置，是线程搜索确认后的选定部署及再次测量，不代表重新训练了一个模型。不同计时轮次分别保留，不将微小耗时差异解释为新的模型精度收益。','small')
 # 5
 page();sub('3.6 验证集上的量化选择');vr=list(lock['all_validation_models']);tune=load(P/'results/cpu_tuning.json');tf=Path(tune['alias_model']);tk=tf.parent.name if tf.suffix=='.xml' else tf.stem;vr.append(load(P/'results'/('eval_'+tk+'_val.json')));resfile=P/'results/eval_a2_cpu_resolution_val.json';
 if resfile.exists():vr.append(load(resfile))
 data=[]
 for r in vr:
  f=P/r['model'];size=sum(x.stat().st_size for x in f.parent.glob('model.*')) if f.suffix=='.xml' else f.stat().st_size
  data.append([label(r['model']),pc(r['coco']['map50']),pc(r['coco']['map50_95']),num(size/1e6)])
 table(['验证配置','AP50 %','AP50-95 %','文件MB'],data,[W*.46,W*.18,W*.21,W*.15])
 para('E1使用验证图校准，仅作诊断；最终INT8配置选择限定于训练集校准候选。验证集最高AP50-95的ORT INT8候选为E9，其验证集AP50-95损失为'+num(lock['loss_pp'])+'个百分点，未满足1个百分点的精度保持门槛。因此不将其直接选为默认部署。')
 para('默认CPU部署的规则为：先按验证集AP50-95损失不超过1个百分点筛选，再在单张p50距离最快配置不超过5%的候选中，优先选择batch32吞吐最高者。该规则避免为约1毫秒的单张差异放弃明显的批量吞吐收益。测试标签不参与校准、层选择或精度门槛筛选。量化模型保留用于展示体积与定位误差的取舍。','small')
 # 6
 page();sub('3.7 统一验证与计时协议');table(['项目','统一设置'],[['精度','pycocotools COCOeval bbox：mAP50、mAP50-95、AP-S/M/L；IoU .50:.05:.95，maxDets=100'],['单张测速','预热10次，计时100次；报告p50/p95'],['batch32测速','预热10次，计时20次；报告平均批延迟及32/平均秒数'],['计时范围','内存JPEG解码、letterbox、RGB归一化、CPU推理、共享NMS和原图坐标还原'],['排除范围','磁盘读写、模型加载、冷启动、视频/Web链路开销'],['内存','进程RSS每10次采样取峰值；单位MB=10^6 bytes'],['连续运行','每配置1000次单张循环，每100次记录RSS；波动=(max-min)/mean，阈值5%'],['测量安排','单个配置顺序运行，校准与导出不并行占用CPU'],['噪声诊断','归一化输入加sigma=.02高斯扰动，按文件名固定随机种子，裁剪到[0,1]']],[100,W-100])
 title('四 实验关键技术与难点');para('重点在于保持各后端预处理及NMS一致，避免将评价器差异误写为精度提升；校准集合与测试集合分离，避免依测试结果选择量化层；区分文件存储压缩、参数量、实际运行内存和算子执行速度；对定位敏感层保留浮点表示，并核对最终接口与已保存预测的一致性。')
 # 7
 page();title('五 实验结果与分析');sub('5.1 CPU加速主结果');table(['配置','p50 ms','p95 ms','B32均值ms','B32 FPS'],[[r['label'],num(r['lat_single_ms_p50']),num(r['lat_single_ms_p95']),num(r['lat_batch32_ms']),num(r['fps'])] for r in rows],[W*.34,W*.15,W*.15,W*.21,W*.15])
 para('最终CPU推荐为'+best['label']+'。相对实验二原A2 CPU PyTorch，单张中位延迟由'+num(base['lat_single_ms_p50'])+' ms降至'+num(best['lat_single_ms_p50'])+' ms，下降'+num(rec['single_latency_reduction_pct'])+'%；batch32平均批延迟下降'+num(rec['batch_latency_reduction_pct'])+'%，吞吐量由'+num(base['fps'])+' FPS提高至'+num(best['fps'])+' FPS，提高'+num(rec['batch_fps_increase_pct'])+'%。')
 para('这些数值均在同一CPU上、按相同计时范围得到；标准对照使用4线程，额外调优版使用'+str(tune['config']['threads'])+'线程，'+('启用Conv-BN融合与channels_last布局。' if tune['config']['fused_channels_last'] else '保持浮点模型结构。')+'THR为性能提示，不等同于异步多请求服务吞吐；FPS是batch32吞吐率，不能直接视为带视频读取、跟踪或Web服务的整链路帧率。','small')
 rb=load(P/'results/repeat_baseline.json');rr=load(P/'results/repeat_selected.json')
 para('独立进程第二轮复测：原CPU基线单张p50 '+num(rb['1']['p50'])+' ms，推荐方案'+num(rr['1']['p50'])+' ms；本轮单张下降'+num((1-rr['1']['p50']/rb['1']['p50'])*100)+'%；B32延迟下降'+num((1-rr['32']['mean']/rb['32']['mean'])*100)+'%，B32吞吐提高'+num((rb['32']['mean']/rr['32']['mean']-1)*100)+'%。第二轮只复测主对照的10/100/20计时；1000次稳定性记录来自主测试。两轮原始数据分别保存，主表不择优替换。','small')
 # 8
 page();sub('5.2 精度、定位与模型体积');table(['配置','AP50 %','AP50-95 %','AP-S %','AP-M %','AP-L %','文件MB'],[[r['label'],pc(r['map50']),pc(r['map50_95']),pc(r['ap_small']),pc(r['ap_medium']),pc(r['ap_large']),num(r['size_mb'])] for r in rows],[W*.28,W*.12,W*.16,W*.11,W*.11,W*.11,W*.11])
 para('推荐部署相对基线的测试AP50-95变化为'+num(rec['test_ap95_difference_pp'])+'个百分点。浮点CPU加速的主要收益是执行效率，不能将微小浮点数值差异解释为新的训练精度提升。')
 a=load(P/'results/area_GT_counts.json');para('测试集面积分组：小于32²的目标'+str(a['small_lt32sq'])+'个，32²至96²之间'+str(a['medium_32sq_to_96sq'])+'个，大于等于96²的目标'+str(a['large_ge96sq'])+'个。AP-S仅对应1个小目标，统计很不稳定，不据此概括小目标泛化表现。COCOeval保留面积ignore规则，没有简单过滤其他尺寸GT后将其预测当成误检。','small')
 para('各部署版本源网络均为3.138M参数；640输入约8.64等价GFLOPs，576/512输入的卷积等价运算量按尺寸平方比例下降。量化改变数值表示与执行内核，未通过剪枝减少主体网络参数。FP32 ONNX、原PT和OpenVINO IR的文件格式不同，应分别比较文件体积；不能用文件缩减比例替代内存降幅。','small')
 # 9
 page();sub('5.3 速度与精度的关联');para('尺寸调优验证记录：'+'；'.join(str(t['imgsz'])+'输入的AP50-95损失'+num(t['validation_AP95_loss_pp'])+'pp、初筛p50 '+num(t['p50_ms'])+' ms' for t in load(P/'results/cpu_resolution_trials.json')['trials'])+'。该初筛计时不替代主表正式测速。','small');pic('cpu_performance.png');table(['编号','CPU配置'],[[str(x['id']),x['label']] for x in load(P/'results/plot_legend.json')],[60,W-60]);para('图1  全部候选使用相同CPU和评价口径。量化是否有效须分别回答：文件是否更小、推理是否更快、定位质量是否保持。若INT8在本机反而更慢，或AP50-95损失超过门槛，则不将其作为默认CPU方案。','small')
 # 10
 page();sub('5.4 原生评价器独立复核');native=[]
 for m in ['models/a2_original.pt',best['model']]:
  k=Path(m).parent.name if m.endswith('.xml') else Path(m).stem;r=load(P/'results'/('native_'+k+'.json'))['native_ultralytics'];native.append([k,pc(r['metrics/precision(B)']),pc(r['metrics/recall(B)']),pc(r['metrics/mAP50(B)']),pc(r['metrics/mAP50-95(B)'])])
 table(['模型','P %','R %','mAP50 %','mAP50-95 %'],native,[W*.30,W*.15,W*.15,W*.20,W*.20])
 para('原生model.val固定device=cpu、test190、batch4；标准模型imgsz640，尺寸调优模型按选定输入尺寸验证、conf=.001、IoU=.55、rect=False、workers0。其P/R为原生工作点指标，不是固定conf=.25的计数。主表采用COCOeval，本页指标单独列出，不跨评价器计算增益。')
 sub('与实验二的比较口径');para('报告使用实验二A2原权重的CPU复测作为优化前基线，数据身份、硬件、预处理规则、NMS及计时范围保持一致；尺寸调优版本明确记录输入尺寸变化，不能把其收益完全归于后端。实验二原报告中的验证摘要0.418来自不同集合和评价口径，不能直接减去本次原始test的AP值来证明优化效果。')
 sub('5.5 噪声诊断');noise=[r for r in rows if r['noise_map50'] is not None and r['ov_mode']!='THROUGHPUT'];table(['配置','干净AP50 %','噪声AP50 %','下降pp'],[[r['label'],pc(r['map50']),pc(r['noise_map50']),num((r['map50']-r['noise_map50'])*100)] for r in noise],[W*.37,W*.21,W*.21,W*.21]);para('噪声仅作压缩可靠性诊断，未进行鲁棒性训练，不能据此列为3.1.6方向已完成。','small')
 # 11
 page();sub('5.6 量化误差分布');pic('per_image_delta.png');para('图2  已锁定INT8减FP32的逐帧自定义AP50-95差值。该指标用于定位误差集中帧，不能将逐帧均值替代全局COCO AP。以下样例按差值从低到高固定选择前三帧，不根据测试样例继续调整模型。')
 sub('5.7 内存与连续运行');table(['CPU配置','RSS峰值MB','1000次RSS波动 %','不超过5%'],[[r['label'],num(r['mem_peak_mb']),num(r['stability']['range_over_mean']*100),'通过' if r['stability']['within_5pct'] else '未通过'] for r in rows],[W*.37,W*.21,W*.24,W*.18]);para('RSS为整个Python进程内存，包含框架与模型运行开销。1000次检查反映该窗口内的增长情况，不能证明所有输入和运行时长均无内存泄漏。','small')
 para('推荐CPU方案的进程RSS峰值由基线'+num(base['mem_peak_mb'])+' MB变为'+num(best['mem_peak_mb'])+' MB，增加'+num((best['mem_peak_mb']/base['mem_peak_mb']-1)*100)+'%。因此本实验可以证明CPU批量推理提速与本轮连续运行稳定，但不能声称实现了内存占用降低30%的目标。','small')
 # 12
 page();sub('5.8 量化误差样例');pic('bad_cases.png',W*.94);para('图3  左侧FP32、右侧INT8；绿框为GT，红框为conf>=.25的预测；相同图片保持原比例。图示用于解释定位误差，不代替完整测试集指标。','small')
 # 13
 page();sub('5.9 任务书要求对照');acc=max(abs(best['map50']-base['map50']),abs(best['map50_95']-base['map50_95']))*100;passed=rec['single_latency_reduction_pct']>=40 and rec['batch_latency_reduction_pct']>=40 and rec['batch_fps_increase_pct']>=50 and acc<=1
 table(['要求','本次CPU证据','判断'],[['以实验二模型为起点','A2原件SHA256核验、单类别与参数量核验','完成'],['CPU优化方向','3.1.4推理加速：完成部署、测速与精度验证；全部性能目标未同时达到','实施完成；目标部分达成'],['OpenVINO工具执行','FP32 IR模型、CPU编译、190图评价与独立复测，证据见3.5','已完成'],['单张延迟降低40%','主测下降'+num(rec['single_latency_reduction_pct'])+'%；复测下降'+num((1-rr['1']['p50']/rb['1']['p50'])*100)+'%','未达标'],['B32延迟降低40%','主测下降'+num(rec['batch_latency_reduction_pct'])+'%；复测下降'+num((1-rr['32']['mean']/rb['32']['mean'])*100)+'%','两轮均达标'],['B32吞吐提高50%','主测提高'+num(rec['batch_fps_increase_pct'])+'%；复测提高'+num((rb['32']['mean']/rr['32']['mean']-1)*100)+'%','两轮均达标'],['精度变化不超过1pp','两种AP指标最大变化'+num(acc)+'pp','达标' if acc<=1 else '未达到'],['量化实验3.1.1','校准矩阵、混合精度、原生与COCO对照','完成实验；部分候选不满足保持门槛'],['稳定性检查',str(len(rows))+'配置各1000次，逐点RSS归档','见5.7逐项结果'],['统一CPU接口','pt/onnx/xml、动态batch1/4/32、不同宽高比坐标检查','通过'],['其他方向','未在本次CPU方案中开展剪枝、蒸馏或鲁棒性训练','不列为完成']],[W*.26,W*.53,W*.21])
 para('3.1.4的联合判据结论为：'+('达到所列时延、吞吐与精度保持目标。' if passed else '未同时达到所列全部门槛，按表中实测分别判断。')+'本报告仅用CPU同设备对照判断，不使用不同硬件之间的速度差证明优化。')
 # 14
 page();title('六 实验总结与展望');para('本实验实施的主要方向是实验二A2模型的CPU推理加速，达标情况按5.9的实测逐项判断。采用'+best['label']+'作为本机默认部署，保留原模型、浮点ONNX、量化ONNX与OpenVINO产物及完整对照结果。推荐依据是验证精度门槛、单张延迟容差和本机批量吞吐，不预设INT8或某一后端一定更优。')
 para('推荐CPU方案单张p50为'+num(best['lat_single_ms_p50'])+' ms，测试mAP50-95为'+pc(best['map50_95'])+'%；相对原CPU基线，单张延迟下降'+num(rec['single_latency_reduction_pct'])+'%，batch32吞吐提高'+num(rec['batch_fps_increase_pct'])+'%。量化的体积、速度与定位代价单独保留，便于按部署约束选择。')
 para('OpenVINO CPU部署已经完成。两轮测试均证明批量延迟、吞吐与精度保持达到所列目标；单张延迟降幅未达到40%，因此不将任务3.1.4的全部指标写成全部达标。')
 para('结论限于当前CPU、640输入及历史数据划分。后续优先补充独立比赛视频与更稳定的小目标测试样本，并测量视频解码、跟踪和服务接口组成的完整CPU链路；若目标CPU型号改变，应在该CPU上重跑当前脚本验证。')
 sub('复现与交付');para('代码、模型、原始train/val/test图片标签、逐配置结果、预测归档、报告与可编辑正文统一位于优化目录。scripts/resolution_runtime.py为CPU接口，run_cpu.py为命令入口，bench_exp3.py为统一测速，eval_detail.py为COCO与分层/噪声评价，native_val.py为原生评价，export_fp32.py/export_fp16.py/export_quant.py为导出量化入口。README.md提供命令，运行CPU推理.ps1自动选择测试图片。','small')
 title('七 参考文献');
 for t in ['[1] 实验3任务书、程序优化实验指导 第三课、EXP3_IMPL_2P实施文档、实验二原报告与模型产物。','[2] ONNX Runtime. Quantize ONNX models. https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html','[3] OpenVINO / NNCF. Quantization API. https://openvinotoolkit.github.io/nncf/autoapi/nncf/','[4] Ultralytics. Detection validation. https://docs.ultralytics.com/modes/val/']:para(t,'small')
 def footer(c,d):
  if d.page==1:return
  c.saveState();c.setFont('Song',9);c.drawCentredString(A4[0]/2,25,str(d.page-1));c.restoreState()
 out=P/'reports/实验3报告_CPU推理优化与验证.pdf';doc=SimpleDocTemplate(str(out),pagesize=A4,leftMargin=56,rightMargin=56,topMargin=48,bottomMargin=44,title='实验3 CPU推理优化与验证',author='第17组');doc.build(story,onFirstPage=footer,onLaterPages=footer)
 (P/'reports/实验3报告_CPU推理优化可编辑正文.md').write_text('\n'.join(md),encoding='utf-8');print(out,flush=True)
if __name__=='__main__':main()
