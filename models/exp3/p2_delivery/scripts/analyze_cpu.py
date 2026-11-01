from bootstrap import P
import json,csv
from pathlib import Path
def load(f):return json.loads(Path(f).read_text(encoding='utf-8'))
def name(r):
 s=r['model']
 if 'cpu_resolution' in s:return load((P/s).parent/'cpu_resolution_config.json')['label']
 if 'cpu_tuned' in s:return load((P/s).parent/'cpu_tuned_config.json')['label']
 if s.endswith('.pt'):return 'A2 PyTorch FP32'
 if 'openvino' in s:return ('OpenVINO INT8' if 'int8' in s else 'OpenVINO FP32')+' '+('LAT' if r['ov_mode']=='LATENCY' else 'THR')
 if 'int8' in s:return 'ORT INT8 mixed'
 return 'ORT FP16' if 'fp16' in s else 'ORT FP32'
def main():
 rows=[];lock=load(P/'results/selection_lock.json');val={r['model']:r['coco']['map50_95'] for r in lock['all_validation_models']}
 for f in sorted((P/'results').glob('bench_*.json')):
  r=load(f);p=Path(r['model']);key=p.parent.name if p.suffix=='.xml' else p.stem
  r.update(load(P/'results'/('eval_'+key+'_test.json'))['coco']);r['label']=name(r)
  nf=P/'results'/('eval_'+key+'_test_noise002.json');r['noise_map50']=load(nf)['coco']['map50'] if nf.exists() else None
  vf=P/'results'/('eval_'+key+'_val.json');r['validation_ap95']=load(vf)['coco']['map50_95'] if vf.exists() else val.get(r['model'],lock['baseline_val_AP95']);r['validation_loss_pp']=(lock['baseline_val_AP95']-r['validation_ap95'])*100
  r['precision']='int8-mixed' if 'int8' in r['model'] else 'fp16' if 'fp16' in r['model'] else 'fp32';r['hardware']=load(P/'results/environment.json')['CPU'];r['accuracy_evaluator']='pycocotools COCOeval bbox; test190'
  f.write_text(json.dumps(r,indent=2),encoding='utf-8');rows.append(r)
 base=next(r for r in rows if r['model'].endswith('.pt'))
 eligible=[r for r in rows if r['validation_loss_pp']<=1 and (not r['model'].endswith('.pt') or 'cpu_tuned' in r['model'] or 'cpu_resolution' in r['model'])]
 fast=min(r['lat_single_ms_p50'] for r in eligible);near=[r for r in eligible if r['lat_single_ms_p50']<=fast*1.05];rec=max(near,key=lambda r:r['fps'])
 out={'label':rec['label'],'model':rec['model'],'ov_mode':rec['ov_mode'],'selection':'validation AP95 loss <=1pp; single p50 within 5% of fastest eligible CPU configuration, then maximum batch32 FPS','baseline':base['label'],'single_latency_reduction_pct':(1-rec['lat_single_ms_p50']/base['lat_single_ms_p50'])*100,'batch_latency_reduction_pct':(1-rec['lat_batch32_ms']/base['lat_batch32_ms'])*100,'batch_fps_increase_pct':(rec['fps']/base['fps']-1)*100,'test_ap95_difference_pp':(rec['map50_95']-base['map50_95'])*100,'recommended_result':rec,'baseline_result':base}
 (P/'results/cpu_comparison.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');(P/'results/cpu_recommendation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 fields=['label','model','backend','precision','hardware','device','size_mb','lat_single_ms_p50','lat_single_ms_p95','lat_batch32_ms','fps','map50','map50_95','ap_small','ap_medium','ap_large','noise_map50','mem_peak_mb','validation_loss_pp']
 with (P/'results/cpu_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 print('CPU_RECOMMENDATION',out['label'],out['single_latency_reduction_pct'],out['batch_fps_increase_pct'],flush=True)
if __name__=='__main__':main()
