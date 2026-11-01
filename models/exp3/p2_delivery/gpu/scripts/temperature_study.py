from bootstrap import P
import subprocess,sys,json,time
root=P/'temperature_sweep';root.mkdir(exist_ok=True)
def run(args,logname):
 print('TEMPERATURE_STEP',args,flush=True)
 with (root/logname).open('a',encoding='utf-8') as f:
  subprocess.run([sys.executable,str(P/'scripts'/args[0]),*args[1:]],cwd=P,stdout=f,stderr=subprocess.STDOUT,check=True)
rows=[]
for t in [5,8,10]:
 f=root/f'T{t}/results/pilot_done.json'
 if not f.exists():run(['distill_temperature.py','--temperature',str(t),'--epochs','12','--stop-after','1','--microbatch','16'],f'pilot_T{t}.log')
 row=json.loads(f.read_text(encoding='utf-8'));rows.append(row)
w=max(rows,key=lambda r:r['val']['AP50_95']);t=w['temperature']
selection={'pilot_epochs_each':1,'total_schedule_epochs':12,'temperatures':[5,8,10],'criterion':'highest validation custom AP50:95 after identical first epoch; no test labels','selected_temperature':t,'pilots':rows,'scope':'one-epoch equal-budget screening then selected candidate completes all 12 epochs'}
(root/'selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
if not (root/f'T{t}/results/distill_done.json').exists():run(['distill_temperature.py','--temperature',str(t),'--epochs','12','--microbatch','16'],f'full_T{t}.log')
print('TEMPERATURE_TRAINING_COMPLETE',t,flush=True)
