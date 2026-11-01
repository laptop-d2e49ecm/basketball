from bootstrap import P,STAGE1,SOURCE_ROOT
import argparse,contextlib,io,json,hashlib,sys
from pathlib import Path
import numpy as np,cv2,torch,torchvision
from infer import Detector
from metrics import score_detections

def data(split):
 rows=[]
 for f in sorted((P.parent/'data/images'/split).glob('*.jpg')):
  im=cv2.imdecode(np.frombuffer(f.read_bytes(),np.uint8),cv2.IMREAD_COLOR);lab=np.loadtxt(P.parent/'data/labels'/split/(f.stem+'.txt'),ndmin=2,dtype=np.float32)
  if lab.size:
   b=lab[:,1:]*640;gt=np.stack([b[:,0]-b[:,2]/2,b[:,1]-b[:,3]/2,b[:,0]+b[:,2]/2,b[:,1]+b[:,3]/2],1).clip(0,640)
  else:gt=np.zeros((0,4),np.float32)
  rows.append((f.name,im,gt))
 return rows

def coco_metric(pred,gt):
 from pycocotools.coco import COCO
 from pycocotools.cocoeval import COCOeval
 db={'images':[],'annotations':[],'categories':[{'id':1,'name':'player'}],'info':{}};dets=[];ann=1
 for i,n in enumerate(gt,1):
  db['images'].append({'id':i,'width':640,'height':640,'file_name':n})
  for b in gt[n]:
   x,y,x2,y2=map(float,b);w=x2-x;h=y2-y;db['annotations'].append({'id':ann,'image_id':i,'category_id':1,'bbox':[x,y,w,h],'area':w*h,'iscrowd':0});ann+=1
  for b,s in zip(pred[n]['boxes'],pred[n]['scores']):
   x,y,x2,y2=map(float,b);dets.append({'image_id':i,'category_id':1,'bbox':[x,y,x2-x,y2-y],'score':float(s)})
 with contextlib.redirect_stdout(io.StringIO()):
  c=COCO();c.dataset=db;c.createIndex()
  if not dets:return {'map50':0.,'map50_95':0.,'ap_small':None,'ap_medium':None,'ap_large':None}
  d=c.loadRes(dets);e=COCOeval(c,d,'bbox');e.params.maxDets=[1,10,100];e.evaluate();e.accumulate();e.summarize()
 vals=e.stats[:6]
 return {k:float(v) if v>=0 else None for k,v in zip(['map50_95','map50','map75','ap_small','ap_medium','ap_large'],vals)}

@torch.inference_mode()
def evaluate(path,split='test',noise=0,device=None,graph=False):
 torch.set_num_threads(4);cv2.setNumThreads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;det=Detector(path,device=device,graph=graph);rows=data(split);pred={};gt={}
 for start in range(0,len(rows),4):
  group=rows[start:start+4];x=np.stack([det.letterbox(r[1])[0] for r in group])
  if noise:
   for i,r in enumerate(group):
    seed=int(hashlib.sha256(r[0].encode()).hexdigest()[:8],16);x[i]=np.clip(x[i]+np.random.default_rng(seed).normal(0,noise,x[i].shape).astype(np.float32),0,1)
  out=det.tensor_batch(x)
  for (n,im,g),a in zip(group,out):pred[n]={'boxes':a[:,:4].clip(0,640),'scores':a[:,4]};gt[n]=g
  if start%80==0:print('EVAL',Path(path).name,split,noise,start,flush=True)
 key=Path(path).stem if Path(path).suffix!='.xml' else Path(path).parent.name
 tag=key+('_graph' if graph else '')+'_'+split+('_noise002' if noise else '')
 offsets=np.r_[0,np.cumsum([len(pred[n]['boxes']) for n in pred])]
 np.savez_compressed(P/'results'/('pred_'+tag+'.npz'),names=np.array(list(pred)),boxes=np.concatenate([pred[n]['boxes'] for n in pred]),scores=np.concatenate([pred[n]['scores'] for n in pred]),offsets=offsets)
 result={'model':Path(path).relative_to(P).as_posix(),'split':split,'images':len(rows),'noise_sigma':noise,'graph':graph,'coco':coco_metric(pred,gt),'custom':score_detections(pred,gt),'per_image_custom_ap95':{n:score_detections({n:pred[n]},{n:gt[n]})['AP50_95'] for n in gt}}
 (P/'results'/('eval_'+tag+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print('SCORE',tag,result['coco'],flush=True)
 del det;torch.cuda.empty_cache();return result

def main():
 q=argparse.ArgumentParser();q.add_argument('--model');q.add_argument('--split',default='test');q.add_argument('--noise',type=float,default=0);q.add_argument('--graph',action='store_true');q.add_argument('--validation-matrix',action='store_true');a=q.parse_args()
 if a.validation_matrix:
  paths=[P/'models/a2_fp32.onnx',P/'models/a2_fp16.onnx']+sorted((P/'models').glob('a2_int8*.onnx'))+[P/'models/a2_openvino_fp32/model.xml',P/'models/a2_openvino_int8/model.xml']
  rows=[]
  for f in paths:
   if f.exists():rows.append(evaluate(f,'val'))
  eligible=[r for r in rows if 'int8_train' in r['model']];best=max(eligible,key=lambda r:r['coco']['map50_95'])
  baseline=rows[0]['coco']['map50_95'];loss=baseline-best['coco']['map50_95']
  lock={'selected_int8':best['model'],'selection_split':'val173 only','criterion':'highest official COCO AP50:95 among train-calibrated ORT INT8; validation-calibrated candidate diagnostic only','baseline_val_AP95':baseline,'selected_val_AP95':best['coco']['map50_95'],'loss_pp':loss*100,'within_1pp':loss<=.01,'fallback_if_over_1pp':'models/a2_fp16.onnx','all_validation_models':[{'model':r['model'],'coco':r['coco']} for r in rows]}
  (P/'results/selection_lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8');print('LOCKED',json.dumps(lock),flush=True)
 else:evaluate(P/a.model,a.split,a.noise,graph=a.graph)
if __name__=='__main__':main()
