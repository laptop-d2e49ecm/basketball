from pathlib import Path
import json,csv,os
P=Path(__file__).resolve().parents[1];G=P/'gpu'
os.environ['MPLCONFIGDIR']=str(P/'reports/mplcache')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt

def load(f):return json.loads(f.read_text(encoding='utf-8'))
def main():
 assert load(G/'results/verification_md.json')['passed']
 specs=[('原A2 CPU','a2_original','cpu'),('原A2 GPU','a2_original','cuda'),('原A2 TRT流水线','a2_trt_fp16_pipeline','cuda'),('蒸馏学生 GPU','a2_distilled','cuda'),('蒸馏TRT流水线','a2_distilled_trt_fp16_pipeline','cuda')]
 rows=[]
 for label,stem,device in specs:
  r=load(G/'results'/f'bench_{stem}_{device}_LATENCY.json');e=load(P/'results/eval_a2_original_test.json') if device=='cpu' else load(G/'results'/f'eval_{stem}_test.json');r.update(e['coco']);r['label']=label;r['id']=stem+'_'+device
  nf=G/'results'/f'eval_{stem}_test_noise002.json';r['noise']=load(nf)['coco'] if nf.exists() else None
  rows.append(r)
 b=rows[1]
 def comparison(a,r):return {'single_reduction_pct':(1-r['lat_single_ms_p50']/a['lat_single_ms_p50'])*100,'batch_reduction_pct':(1-r['lat_batch32_ms']/a['lat_batch32_ms'])*100,'fps_increase_pct':(r['fps']/a['fps']-1)*100,'ap50_difference_pp':(r['map50']-a['map50'])*100,'ap95_difference_pp':(r['map50_95']-a['map50_95'])*100}
 comparisons={'hardware_CPU_to_GPU':comparison(rows[0],b),'same_GPU_TensorRT':comparison(b,rows[2]),'same_GPU_distilled':comparison(b,rows[3]),'same_GPU_combined':comparison(b,rows[4])}
 repeats=[]
 rb=load(G/'results/repeat_a2_original.json')
 for stem in ['a2_trt_fp16_pipeline','a2_distilled_trt_fp16_pipeline']:
  rr=load(G/'results'/f'repeat_{stem}.json');repeats.append({'model':stem,'single_reduction_pct':(1-rr['lat_single_ms_p50']/rb['lat_single_ms_p50'])*100,'batch_reduction_pct':(1-rr['lat_batch32_ms']/rb['lat_batch32_ms'])*100,'fps_increase_pct':(rr['fps']/rb['fps']-1)*100})
 summary={'direct_trt_reference':load(G/'results/bench_a2_trt_fp16_cuda_LATENCY.json'),'rows':rows,'comparisons':comparisons,'independent_repeats':repeats,'same_GPU_reference':'original A2 FP32','CPU_reference':'original A2 FP32','training':load(G/'results/distill_done.json'),'teacher':load(G/'results/eval_m1_teacher_test.json')['coco']}
 (P/'results/md_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 with (P/'results/md_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['label','backend','hardware','size_mb','params_m','flops_g','lat_single_ms_p50','lat_single_ms_p95','lat_batch32_ms','fps','map50','map50_95','ap_small','ap_medium','ap_large','mem_peak_mb'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 h=load(G/'results/distill_history.json');fig,ax=plt.subplots(figsize=(6.8,3.2));ax.plot([r['epoch'] for r in h],[r['val']['AP50_95']*100 for r in h],marker='o',label='Student KD validation AP50:95')
 for stem,label,color in [('a2_original','Original student','#5179a6'),('m1_teacher','Teacher','#ac7438')]:ax.axhline(load(G/'results'/f'eval_{stem}_val.json')['custom']['AP50_95']*100,label=label,ls='--',color=color)
 ax.set(xlabel='Epoch',ylabel='Validation custom AP (%)',xticks=range(1,13));ax.grid(alpha=.2);ax.legend(fontsize=8);fig.tight_layout();fig.savefig(P/'reports/assets/md_training.png',dpi=180);plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(7.1,3.2));names=['Original','TensorRT','KD','KD + TensorRT'];gr=rows[1:]
 axes[0].barh(names,[r['lat_single_ms_p50'] for r in gr]);axes[0].set_xlabel('GPU single p50 latency (ms)')
 axes[1].barh(names,[r['map50_95']*100 for r in gr],color='#34836e');axes[1].set_xlabel('Test COCO AP50:95 (%)');axes[1].set_xlim(0,100)
 fig.tight_layout();fig.savefig(P/'reports/assets/md_gpu_comparison.png',dpi=180);plt.close(fig)
 print(json.dumps(comparisons,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
