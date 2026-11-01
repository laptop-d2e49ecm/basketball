from pathlib import Path
import os,json,numpy as np
P=Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR']=str(P/'reports/mplcache')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
rows=json.loads((P/'results/cpu_comparison.json').read_text(encoding='utf-8'))
rows=[r for r in rows if r['ov_mode']!='THROUGHPUT']
base=next(r for r in rows if r['backend']=='pytorch-cpu')
keys=['map50','map50_95','ap_small','ap_medium','ap_large']
a=np.array([[np.nan if r[k] is None else (r[k]-base[k])*100 for k in keys] for r in rows])
names=['OV FP32 selected' if 'cpu_tuned' in r['model'] else 'Original PT FP32' if r['backend']=='pytorch-cpu' else 'ORT INT8 mixed' if 'reg2fp32' in r['model'] else 'ORT FP16' if r['model'].endswith('fp16.onnx') else 'ORT FP32' if r['model'].endswith('fp32.onnx') else 'OV INT8' if 'int8' in r['model'] else 'OV FP32 LAT' for r in rows]
fig,ax=plt.subplots(figsize=(7.1,4.0));lim=max(1,float(np.nanmax(np.abs(a))));im=ax.imshow(a,cmap='RdBu',vmin=-lim,vmax=lim,aspect='auto')
ax.set_xticks(range(5),['AP50','AP50:95','AP small','AP medium','AP large']);ax.set_yticks(range(len(rows)),names)
for i in range(a.shape[0]):
 for j in range(a.shape[1]):
  if np.isfinite(a[i,j]):ax.text(j,i,f'{a[i,j]:+.2f}',ha='center',va='center',fontsize=9,color='white' if abs(a[i,j])>lim*.55 else 'black')
fig.colorbar(im,ax=ax,label='AP difference from original (percentage points)');fig.tight_layout();fig.savefig(P/'reports/assets/quant_error_heatmap.png',dpi=180)
(P/'results/quant_error_heatmap.json').write_text(json.dumps({'columns':keys,'labels':names,'values_pp':a.tolist(),'small_GT_count':1},indent=2),encoding='utf-8')
print('HEATMAP_DONE')
