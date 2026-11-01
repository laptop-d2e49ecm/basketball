"""Resumable YOLOv8m -> original A2 YOLOv8n detection distillation.
Single-class KD uses Bernoulli KL; singleton softmax KL would be zero.
Training adapters never enter the exported student. Native hard detection loss.
"""
from bootstrap import P,STAGE1,SOURCE_ROOT
import argparse,copy,math,json,time,random,os,sys
from pathlib import Path
import numpy as np,cv2,torch,torchvision
from torch import nn
from torch.nn import functional as F
from torch.utils.data import Dataset,DataLoader
from ultralytics import YOLO
from ultralytics.cfg import get_cfg
from checkpoint_metadata import actual_args
from ultralytics.utils.nms import non_max_suppression
from metrics import score_detections

from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from collections import deque
class ThreadFrames:
 def __init__(self,dataset,batch):self.dataset=dataset;self.batch=batch
 def __len__(self):return math.ceil(len(self.dataset)/self.batch)
 def __iter__(self):
  order=torch.randperm(len(self.dataset)).tolist()
  with ThreadPoolExecutor(max_workers=4) as pool:
   indices=iter(order);pending=deque()
   for i in islice(indices,self.batch*2):pending.append(pool.submit(self.dataset.__getitem__,i))
   rows=[]
   while pending:
    rows.append(pending.popleft().result())
    i=next(indices,None)
    if i is not None:pending.append(pool.submit(self.dataset.__getitem__,i))
    if len(rows)==self.batch:yield collate(rows);rows=[]
   if rows:yield collate(rows)

class Frames(Dataset):
 def __init__(self,split,augment=False):self.files=sorted((P.parent/'data/images'/split).glob('*.jpg'));self.split=split;self.augment=augment;self.epoch=0
 def __len__(self):return len(self.files)
 def __getitem__(self,i):
  f=self.files[i];im=cv2.imread(str(f));im=cv2.resize(im,(640,640));rows=np.loadtxt(P.parent/'data/labels'/self.split/(f.stem+'.txt'),ndmin=2,dtype=np.float32)
  if rows.size==0:rows=np.zeros((0,5),np.float32)
  if self.augment:
   rng=random if self.epoch==0 else random.Random(42+self.epoch*100000+i)
   if rng.random()<.5:im=im[:,::-1].copy();rows[:,1]=1-rows[:,1]
   hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV).astype(np.float32)
   hsv[...,0]=(hsv[...,0]+rng.uniform(-.015,.015)*180)%180
   hsv[...,1]=np.clip(hsv[...,1]*rng.uniform(.7,1.3),0,255)
   hsv[...,2]=np.clip(hsv[...,2]*rng.uniform(.8,1.2),0,255)
   im=cv2.cvtColor(hsv.astype(np.uint8),cv2.COLOR_HSV2BGR)
  x=torch.from_numpy(np.ascontiguousarray(im[...,::-1].transpose(2,0,1))).float()/255
  return x,torch.from_numpy(rows),f.name

def worker_init(worker_id):cv2.setNumThreads(1)

def collate(rows):
 x=torch.stack([r[0] for r in rows]);labels=torch.cat([r[1] for r in rows]);idx=torch.cat([torch.full((len(r[1]),),i) for i,r in enumerate(rows)])
 return {'img':x,'cls':labels[:,:1],'bboxes':labels[:,1:],'batch_idx':idx},[r[2] for r in rows]

@torch.inference_mode()
def val(model):
 model.eval();pred={};gt={}
 for batch,names in DataLoader(Frames('val'),batch_size=4,collate_fn=collate,num_workers=0):
  y=model(batch['img'].cuda());y=y[0] if isinstance(y,tuple) else y
  out=non_max_suppression(y,conf_thres=.001,iou_thres=.55,nc=1,agnostic=True,max_det=100,max_time_img=5)
  for i,n in enumerate(names):
   a=out[i].float().cpu().numpy();pred[n]={'boxes':np.clip(a[:,:4],0,640),'scores':a[:,4]}
   b=batch['bboxes'][batch['batch_idx']==i].numpy()*640
   gt[n]=np.stack([b[:,0]-b[:,2]/2,b[:,1]-b[:,3]/2,b[:,0]+b[:,2]/2,b[:,1]+b[:,3]/2],1)
 return score_detections(pred,gt)

def save_student(model,path,epoch,metric,total_epochs=12):
 m=copy.deepcopy(model).cpu().half().eval()
 if hasattr(m,'criterion'):del m.criterion
 m.args=get_cfg(overrides=actual_args(total_epochs))
 torch.save({'model':m,'epoch':epoch,'best_fitness':metric,'train_args':actual_args(total_epochs),'best_epoch_one_based':epoch,'epoch_indexing':'one-based best epoch','date':'2026-10-26','version':'8.4.183'},path)

def run(a):
 global RUN
 RUN=P/"temperature_sweep"/("T"+str(a.temperature))
 (RUN/"models").mkdir(parents=True,exist_ok=True);(RUN/"results").mkdir(exist_ok=True)
 random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
 cv2.setNumThreads(1);torch.set_num_threads(4);torch.backends.cudnn.benchmark=False
 student=YOLO(str(P/'models/a2_original.pt')).model.float().cuda().to(memory_format=torch.channels_last);teacher=YOLO(str(P/'models/m1_teacher.pt')).model.float().cuda().to(memory_format=torch.channels_last).eval()
 for name,q in student.named_parameters():q.requires_grad_('.dfl.' not in name)
 student.args=get_cfg();student.args.box=7.5;student.args.cls=.5;student.args.dfl=1.5
 for q in teacher.parameters():q.requires_grad_(False)
 sf=[];tf=[]
 sh=student.model[-1].register_forward_pre_hook(lambda m,args:sf.__setitem__(slice(None),list(args[0])))
 th=teacher.model[-1].register_forward_pre_hook(lambda m,args:tf.__setitem__(slice(None),list(args[0])))
 with torch.no_grad():student.eval()(torch.zeros(1,3,640,640,device='cuda'));teacher(torch.zeros(1,3,640,640,device='cuda'))
 adapters=nn.ModuleList([nn.Sequential(nn.Conv2d(s.shape[1],t.shape[1],1,bias=False),nn.BatchNorm2d(t.shape[1])) for s,t in zip(sf,tf)]).cuda()
 sh.remove();th.remove();sf.clear();tf.clear()
 ema=copy.deepcopy(student).eval()
 for q in ema.parameters():q.requires_grad_(False)
 amp_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
 if a.amp_dtype!='auto':amp_dtype=getattr(torch,a.amp_dtype)
 scaler=torch.amp.GradScaler('cuda',enabled=amp_dtype==torch.float16,init_scale=128.)
 criterion=student.init_criterion();params=list(student.parameters())+list(adapters.parameters());opt=torch.optim.AdamW(params,lr=.0004,weight_decay=.0005)
 hist=[];start=0;best=-1;updates=0;resume=RUN/'results/distill_resume.pt';beg=time.time()
 if resume.exists() and not a.fresh:
  ck=torch.load(resume,map_location='cpu',weights_only=False);student.load_state_dict(ck['student']);teacher.eval();ema.load_state_dict(ck['ema']);adapters.load_state_dict(ck['adapters']);opt.load_state_dict(ck['optimizer']);hist=ck['history'];start=ck['epoch']+1;best=ck['best'];updates=ck['updates']
  if ck.get('scaler'):scaler.load_state_dict(ck['scaler'])
  random.setstate(ck['random']);np.random.set_state(ck['numpy']);torch.set_rng_state(ck['torch']);torch.cuda.set_rng_state_all(ck['cuda'])
 for epoch in range(start,min(a.epochs,a.stop_after or a.epochs)):
  micro=4 if epoch==0 else a.microbatch
  loader=DataLoader(Frames('train',True),batch_size=micro,shuffle=True,collate_fn=collate,num_workers=0) if epoch==0 else ThreadFrames(Frames('train',True),micro)
  loader.dataset.epoch=epoch
  student.train();adapters.train()
  for g in opt.param_groups:g['lr']=.0004*(.01+.99*(1+math.cos(math.pi*epoch/a.epochs))/2)
  means=np.zeros(4);opt.zero_grad(set_to_none=True)
  for j,(batch,names) in enumerate(loader):
   batch={k:v.cuda(non_blocking=True) for k,v in batch.items()};x=batch['img'].contiguous(memory_format=torch.channels_last)
   with torch.autocast('cuda',dtype=amp_dtype):
    with torch.no_grad():tout=teacher(x);tr=tout[1]
    sp=student(x);hard=criterion(sp,batch)[0].sum()/x.shape[0]
    feat=sum(F.mse_loss(F.normalize(ad(s).float(),dim=1),F.normalize(t.float(),dim=1)) for ad,s,t in zip(adapters,sp['feats'],tr['feats']))/3
    T=float(a.temperature);mask=(tr['scores'].sigmoid()>.1).float();p=(tr['scores'].float()/T).sigmoid().clamp(1e-5,1-1e-5);q=sp['scores'].float()/T
    kl=(F.binary_cross_entropy_with_logits(q,p,reduction='none')+p*p.log()+(1-p)*(1-p).log())*T*T
    soft=(kl*mask).sum()/mask.sum().clamp_min(1);loss=.3*hard+.5*feat+.2*soft
   if not torch.isfinite(loss):raise RuntimeError('nonfinite loss')
   scaler.scale((loss*x.shape[0])/16).backward()
   if j==0:
    grad=next(student.parameters()).grad
    assert grad is not None and torch.isfinite(grad).all() and grad.abs().sum()>0, 'student backbone must receive gradients'
    print('STUDENT_GRAD_OK',float(grad.abs().mean()),'allocated_MiB',torch.cuda.max_memory_allocated()/1024**2,flush=True)
   if (j+1)*micro%16==0 or j==len(loader)-1:
    scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(params,10);scaler.step(opt);scaler.update();opt.zero_grad(set_to_none=True);updates+=1
    decay=.9999*(1-math.exp(-updates/2000))
    with torch.no_grad():
     sd=student.state_dict()
     for k,v in ema.state_dict().items():
      if v.dtype.is_floating_point:v.mul_(decay).add_(sd[k].detach(),alpha=1-decay)
   means+=np.array([loss.item(),hard.item(),feat.item(),soft.item()])
   if j%20==0:print('TRAIN',epoch+1,j,'/',len(loader),'loss',means[0]/(j+1),'minutes',round((time.time()-beg)/60,1),flush=True)
   if a.smoke and j>=3:
    print('SMOKE_OK',{'loss':loss.item(),'feature_grad':float(adapters[0][0].weight.grad.abs().mean()) if adapters[0][0].weight.grad is not None else 'optimizer stepped','soft':soft.item()},flush=True);return
  metric=val(ema);row={'epoch':epoch+1,'lr':opt.param_groups[0]['lr'],'losses':(means/len(loader)).tolist(),'val':metric,'microbatch':micro,'minutes':(time.time()-beg)/60};hist.append(row)
  key=metric['mAP50_95'] if 'mAP50_95' in metric else metric.get('AP50_95',metric.get('mAP50-95'))
  if key is None:print(metric);raise RuntimeError('metric key')
  if key>best:best=key;save_student(ema,RUN/'models/a2_distilled.pt',epoch+1,best,a.epochs)
  torch.save({'student':student.state_dict(),'ema':ema.state_dict(),'adapters':adapters.state_dict(),'optimizer':opt.state_dict(),'scaler':scaler.state_dict(),'epoch':epoch,'history':hist,'best':best,'updates':updates,'random':random.getstate(),'numpy':np.random.get_state(),'torch':torch.get_rng_state(),'cuda':torch.cuda.get_rng_state_all()},resume)
  (RUN/'results/distill_history.json').write_text(json.dumps(hist,indent=2),encoding='utf-8');print('EPOCH',json.dumps(row),flush=True)
 if len(hist)<a.epochs:
  (RUN/'results/pilot_done.json').write_text(json.dumps({'temperature':a.temperature,'epochs_completed':len(hist),'full_schedule_epochs':a.epochs,'val':hist[-1]['val']},indent=2),encoding='utf-8');return
 (RUN/'results/distill_done.json').write_text(json.dumps({'epochs':a.epochs,'best_val_map50_95':best,'effective_batch':16,'microbatch_schedule':{'epoch1':4,'later':a.microbatch},'temperature':a.temperature,'loss_weights':[.3,.5,.2],'adapters':'Conv1x1+BN train-only','single_class_KD':'Bernoulli KL; teacher p>.1','student_BN':'train statistics, validation uses EMA running stats','AMP':str(amp_dtype).replace('torch.',''),'lr0':.0004,'teacher':'original experiment2 v8m best','selection':'validation173 only','matched_nonKD_control':False,'device':'cuda','source_lr0':.002,'lr_ratio':.2,'training_seconds_current_resume':time.time()-beg,'channels_last':True},indent=2),encoding='utf-8')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=12);p.add_argument('--microbatch',type=int,default=16);p.add_argument('--smoke',action='store_true');p.add_argument('--fresh',action='store_true');p.add_argument('--amp-dtype',choices=['auto','bfloat16','float16'],default='auto');p.add_argument('--temperature',type=int,required=True,choices=[5,8,10]);p.add_argument('--stop-after',type=int);a=p.parse_args()
 from runtime_lock import acquire
 gpu_lock=acquire()
 out=P/'temperature_sweep'/('T'+str(a.temperature))/'results'
 donefile=out/('pilot_done.json' if a.stop_after else 'distill_done.json')
 if donefile.exists():print('ALREADY_COMPLETE',donefile,flush=True)
 else:run(a)
