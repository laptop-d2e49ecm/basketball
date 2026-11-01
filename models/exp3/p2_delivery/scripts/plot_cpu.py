from bootstrap import P
from pathlib import Path
import json,os
os.environ['MPLCONFIGDIR']=str(P/'reports/mplcache')
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image,ImageDraw,ImageFont
def load(f):return json.loads(Path(f).read_text(encoding='utf-8'))
def key_of(model):
 f=Path(model);return f.parent.name if f.suffix=='.xml' else f.stem
def main():
 asset=P/'reports/assets';asset.mkdir(parents=True,exist_ok=True);rows=load(P/'results/cpu_comparison.json');lock=load(P/'results/selection_lock.json')
 fig,axes=plt.subplots(1,2,figsize=(8,3.9))
 names=[str(i+1) for i in range(len(rows))]
 axes[0].barh(names,[r['lat_single_ms_p50'] for r in rows],color='#376e99');axes[0].set(xlabel='CPU single p50 (ms)',ylabel='Configuration ID')
 axes[1].barh(names,[r['map50_95']*100 for r in rows],color='#3b806c');axes[1].set(xlabel='Test COCO AP50:95 (%)',xlim=(0,100))
 for ax in axes:ax.grid(axis='x',alpha=.2)
 fig.tight_layout();fig.savefig(asset/'cpu_performance.png',dpi=180);plt.close(fig)
 (P/'results/plot_legend.json').write_text(json.dumps([{'id':i+1,'label':r['label']} for i,r in enumerate(rows)],indent=2),encoding='utf-8')
 original=load(P/'results/eval_a2_fp32_test.json');quantfile=P/'results'/('eval_'+key_of(lock['selected_int8'])+'_test.json');quant=load(quantfile)
 delta={n:quant['per_image_custom_ap95'][n]-v for n,v in original['per_image_custom_ap95'].items()};arr=np.array(list(delta.values()))
 fig,ax=plt.subplots(figsize=(6.7,2.8));ax.hist(arr*100,bins=20,color='#547eaa',edgecolor='white');ax.axvline(0,color='black',lw=.8);ax.set(xlabel='INT8 minus FP32 per-image custom AP50:95 (pp)',ylabel='Images');fig.tight_layout();fig.savefig(asset/'per_image_delta.png',dpi=180);plt.close(fig)
 worst=sorted(delta,key=delta.get)[:3];font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',12);canvas=Image.new('RGB',(640,790),'white');draw=ImageDraw.Draw(canvas)
 def predictions(stem):
  a=np.load(P/'results'/('pred_'+stem+'_test.npz'));return {n:a['boxes'][a['offsets'][i]:a['offsets'][i+1]][a['scores'][a['offsets'][i]:a['offsets'][i+1]]>=.25] for i,n in enumerate(a['names'])}
 op=predictions('a2_fp32');qp=predictions(key_of(lock['selected_int8']));bad=[]
 for i,name in enumerate(worst):
  im=Image.open(P/'data/images/test'/name).convert('RGB');lab=np.loadtxt(P/'data/labels/test'/(Path(name).stem+'.txt'),ndmin=2);b=lab[:,1:]*640;gt=np.stack([b[:,0]-b[:,2]/2,b[:,1]-b[:,3]/2,b[:,0]+b[:,2]/2,b[:,1]+b[:,3]/2],1).clip(0,640)
  # Full-frame thumbnails preserve aspect ratio; labels and crop policy are fixed.
  for j,(pred,title) in enumerate([(op[name],'Original A2 FP32'),(qp[name],'Selected INT8')]):
   panel=im.copy();pd=ImageDraw.Draw(panel)
   for box in gt:pd.rectangle(tuple(map(float,box)),outline=(0,180,40),width=2)
   for box in pred:pd.rectangle(tuple(map(float,box)),outline=(230,40,40),width=2)
   panel.thumbnail((220,220));x=j*320+50;y=i*260+30;canvas.paste(panel,(x,y));draw.text((j*320+50,i*260+8),title,fill='black',font=font)
  draw.text((8,i*260+250),str(i+1)+' '+name+'  delta='+str(round(delta[name]*100,2))+' pp',fill='black',font=small);bad.append({'name':name,'delta_per_image_custom_AP95_pp':delta[name]*100})
 canvas.save(asset/'bad_cases.png')
 (P/'results/error_analysis.json').write_text(json.dumps({'per_image_delta':delta,'worst3':bad,'metric':'per-image custom AP diagnosis, not averaged global COCO AP','colors':'green GT, red predictions conf>=.25','selection':'three lowest INT8 minus FP32 AP95 on locked test; diagnostic only, no subsequent tuning'},indent=2),encoding='utf-8')

 print('CPU_PLOTS_DONE',flush=True)
if __name__=='__main__':main()
