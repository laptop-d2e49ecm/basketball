from bootstrap import P
import json,hashlib,torch
from ultralytics.cfg import get_cfg

def actual_args(epochs=12):
 a=vars(get_cfg()).copy();a.update({'model':'models/a2_original.pt','data':'data/data.yaml','epochs':epochs,'batch':16,'imgsz':640,'seed':42,'optimizer':'AdamW','lr0':.0004,'weight_decay':.0005,'amp':True,'cos_lr':True,'warmup_epochs':0.,'mosaic':0.,'mixup':0.,'translate':0.,'scale':0.,'degrees':0.,'fliplr':.5,'flipud':0.,'hsv_h':.015,'hsv_s':.3,'hsv_v':.2})
 return a

def normalize():
 f=P/'models/a2_distilled.pt';ck=torch.load(f,map_location='cpu',weights_only=False)
 def digest(m):
  h=hashlib.sha256()
  for k,v in sorted(m.state_dict().items()):h.update(k.encode());h.update(str(v.dtype).encode());h.update(v.detach().cpu().numpy().tobytes())
  return h.hexdigest()
 before=digest(ck['model']);hist=json.loads((P/'results/distill_history.json').read_text());best=max(hist,key=lambda r:r['val']['AP50_95']);args=actual_args(len(hist));ck['train_args']=args;ck['model'].args=get_cfg(overrides=args)
 ck['training_method']='custom feature + Bernoulli KD';ck['best_epoch_one_based']=best['epoch'];ck['epoch_indexing']='one-based best epoch';ck['amp_dtype']='bfloat16';ck['model_source']='Experiment2 A2_yolov8n/weights/best.pt'
 tmp=f.with_suffix('.metadata.tmp');torch.save(ck,tmp);check=torch.load(tmp,map_location='cpu',weights_only=False);after=digest(check['model']);assert before==after;tmp.replace(f)
 (P/'results/checkpoint_metadata.json').write_text(json.dumps({'tensor_sha256_before':before,'tensor_sha256_after':after,'identical_weights':True,'best_epoch_one_based':best['epoch'],'training_epochs':len(hist),'args':args},indent=2),encoding='utf-8');print('CHECKPOINT_METADATA_OK',flush=True)
if __name__=='__main__':normalize()
