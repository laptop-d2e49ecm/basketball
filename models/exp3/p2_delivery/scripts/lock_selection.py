from bootstrap import P
import json,hashlib
rows=[]
for f in sorted((P/'results').glob('eval_*_val.json')):
 r=json.loads(f.read_text(encoding='utf-8'));r['model']=r['model'].replace('\\','/');rows.append(r)
baseline=next(r for r in rows if r['model']=='models/a2_fp32.onnx')
candidates=[r for r in rows if 'a2_int8_train' in r['model']]
best=max(candidates,key=lambda r:r['coco']['map50_95']);loss=baseline['coco']['map50_95']-best['coco']['map50_95']
lock={'selected_int8':best['model'],'selection_split':'val173 only','criterion':'highest COCO AP50:95 among train-calibrated ORT candidates; val173-calibrated candidate diagnostic only','baseline_val_AP95':baseline['coco']['map50_95'],'selected_val_AP95':best['coco']['map50_95'],'loss_pp':loss*100,'within_1pp':loss<=.01,'fallback_if_over_1pp':'models/a2_fp16.onnx','model_sha256':hashlib.sha256((P/best['model']).read_bytes()).hexdigest(),'all_validation_models':[{'model':r['model'],'coco':r['coco']} for r in rows]}
ovcandidates=[r for r in rows if 'a2_openvino_int8' in r['model']]
lock['selected_openvino_int8']=max(ovcandidates,key=lambda r:r['coco']['map50_95'])['model'] if ovcandidates else None
(P/'results/selection_lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8');print(json.dumps(lock,indent=2))
