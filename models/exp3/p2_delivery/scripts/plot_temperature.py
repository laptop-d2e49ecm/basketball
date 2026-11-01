from pathlib import Path
import json,os
P=Path(__file__).resolve().parents[1];G=P/'gpu';os.environ['MPLCONFIGDIR']=str(P/'reports/mplcache')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
v=json.loads((G/'results/temperature_verification.json').read_text(encoding='utf-8'));h=v['full_history'];b=json.loads((G/'results/distill_history.json').read_text(encoding='utf-8'))
fig,ax=plt.subplots(figsize=(6.8,3.2));ax.plot([r['epoch'] for r in h],[r['val']['AP50_95']*100 for r in h],marker='o',label='Selected T='+str(v['selected_temperature']));ax.plot([r['epoch'] for r in b],[r['val']['AP50_95']*100 for r in b],ls='--',label='T=6 reference')
ax.set(xlabel='Epoch',ylabel='Validation custom AP50:95 (%)',xticks=range(1,13));ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(P/'reports/assets/temperature_study.png',dpi=180);print('TEMPERATURE_PLOT_DONE')
