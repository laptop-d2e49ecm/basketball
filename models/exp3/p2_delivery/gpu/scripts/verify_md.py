from bootstrap import P
import json,hashlib,zipfile,numpy as np,torch,cv2
from infer import Detector
from optimized_trt import Detector as PipelineDetector

def load(f):return json.loads(f.read_text(encoding='utf-8'))
def main():
 torch.set_num_threads(4);cv2.setNumThreads(1)
 source=P.parent.parent.parent.parent/'模型设计与训练.zip'
 proofs=[]
 with zipfile.ZipFile(source) as z:
  for row in load(P/'results/model_provenance.json'):
   local=P/'models'/row['file'];digest=hashlib.sha256(local.read_bytes()).hexdigest()
   assert digest==hashlib.sha256(z.read(row['archive_member'])).hexdigest()==row['sha256']
   proofs.append({'file':row['file'],'sha256':digest,'archive_match':True})
 h=load(P/'results/distill_history.json');done=load(P/'results/distill_done.json')
 assert [r['epoch'] for r in h]==list(range(1,13))
 assert done['lr0']==.0004 and done['epochs']==12 and done['device']=='cuda'
 ck=torch.load(P/'models/a2_distilled.pt',map_location='cpu',weights_only=False)
 assert sum(t.numel() for t in ck['model'].parameters())==3138003
 best=max(h,key=lambda x:x['val']['AP50_95']);assert ck['best_epoch_one_based']==best['epoch']
 checks=[]
 files=sorted((P.parent/'data/images/test').glob('*.jpg'))[:32]
 imgs=[cv2.imdecode(np.frombuffer(f.read_bytes(),np.uint8),cv2.IMREAD_COLOR) for f in files]
 for model in ['a2_original.pt','a2_distilled.pt','a2_trt_fp16.engine','a2_distilled_trt_fp16.engine']:
  det=(PipelineDetector if model.endswith('.engine') else Detector)(P/'models'/model,device='cuda')
  for bs in [1,4,32]:
   out=det.predict_batch(imgs[:bs]);assert len(out)==bs
   assert all(a.ndim==2 and a.shape[1]==6 and np.isfinite(a).all() for a in out)
   checks.append({'model':model,'batch':bs,'finite_Nx6':True})
  for width,height in [(480,320),(300,600)]:
   im=cv2.resize(imgs[0],(width,height));a=det(im)
   assert (a[:,[0,2]]>=0).all() and (a[:,[0,2]]<=width).all()
   assert (a[:,[1,3]]>=0).all() and (a[:,[1,3]]<=height).all()
   checks.append({'model':model,'shape':[height,width],'original_coordinate_bounds':True})
  if hasattr(det,'close'):det.close()
  del det;torch.cuda.empty_cache()
 for stem,buildfile in [('a2_trt_fp16','trt_build.json'),('a2_distilled_trt_fp16','trt_student_build.json')]:
  assert hashlib.sha256((P/'models'/(stem+'.engine')).read_bytes()).hexdigest()==load(P/'results'/buildfile)['sha256']
 result={'passed':True,'sources':proofs,'student_best_epoch':best['epoch'],'training_epochs':12,'initial_lr_ratio':.2,'interface_checks':checks,'GPU':torch.cuda.get_device_name(),'scope':'local GPU, CPU reference; no Kaggle execution claim','source_code_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'scripts').glob('*.py')},'model_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'models').glob('*') if f.is_file()}}
 (P/'results/verification_md.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('MD_VERIFICATION_PASSED',flush=True)
if __name__=='__main__':main()
