from bootstrap import P
from pathlib import Path
from runtime_lock import acquire
gpu_lock=acquire()
import json,subprocess,sys,shutil,hashlib,torch
root=P/'temperature_sweep';selection=json.loads((root/'selection.json').read_text());t=selection['selected_temperature'];run=root/f'T{t}'
done=json.loads((run/'results/distill_done.json').read_text());hist=json.loads((run/'results/distill_history.json').read_text())
assert done['epochs']==12 and done['temperature']==t and done['lr0']==.0004
assert [r['epoch'] for r in hist]==list(range(1,13))
f=P/'models/a2_temperature.pt';shutil.copy2(run/'models/a2_distilled.pt',f)
steps=[['eval_detail.py','--model','models/a2_temperature.pt'],['eval_detail.py','--model','models/a2_temperature.pt','--noise','.02'],['eval_detail.py','--model','models/a2_temperature.pt','--split','val'],['bench_exp3.py','--model','models/a2_temperature.pt','--device','cuda'],['native_val.py','--models','models/a2_temperature.pt','--device','0'],['eval_detail.py','--model','models/a2_distilled.pt','--split','val'],['verify_auto.py'],['smoke_train.py']]
outputs=['eval_a2_temperature_test.json','eval_a2_temperature_test_noise002.json','eval_a2_temperature_val.json','bench_a2_temperature_cuda_LATENCY.json','native_a2_temperature.json','eval_a2_distilled_val.json','auto_deployment_verification.json','training_smoke_verification.json']
sourcefile=P/'results/temperature_evaluation_source.json';digest=hashlib.sha256(f.read_bytes()).hexdigest()
same_source=sourcefile.exists() and json.loads(sourcefile.read_text())['sha256']==digest
sourcefile.write_text(json.dumps({'sha256':digest,'temperature':t}),encoding='utf-8')
for i,args in enumerate(steps):
 if same_source and (P/'results'/outputs[i]).exists():continue
 with (root/f'final_{i}.log').open('w',encoding='utf-8') as log:subprocess.run([sys.executable,str(P/'scripts'/args[0]),*args[1:]],cwd=P,stdout=log,stderr=subprocess.STDOUT,check=True)
ck=torch.load(f,map_location='cpu',weights_only=False);best=max(hist,key=lambda r:r['val']['AP50_95']);assert ck['best_epoch_one_based']==best['epoch'];assert sum(q.numel() for q in ck['model'].parameters())==3138003
proof={'passed':True,'selected_temperature':t,'pilot_epochs_each':1,'full_epochs':12,'best_epoch':best['epoch'],'model_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'selection':selection,'full_history':hist,'model':'gpu/models/a2_temperature.pt','test_used_for_selection':False}
(P/'results/temperature_verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print('TEMPERATURE_VALIDATION_COMPLETE',t,flush=True)
