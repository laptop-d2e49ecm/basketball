from bootstrap import P
import subprocess,sys,json
for name in ['complete_deployment.py','temperature_study.py','finish_temperature.py']:
 print('RUN',name,flush=True)
 subprocess.run([sys.executable,str(P/'scripts'/name)],cwd=P,check=True)
print('ALL_TRAIN_AND_DEPLOY_STAGES_DONE',flush=True)
