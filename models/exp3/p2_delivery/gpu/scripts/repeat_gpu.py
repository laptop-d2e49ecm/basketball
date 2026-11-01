from bootstrap import P
import argparse,json
from bench_exp3 import run
q=argparse.ArgumentParser();q.add_argument('--model',required=True);a=q.parse_args()
f=P/'results'/('bench_'+__import__('pathlib').Path(a.model).stem+'_cuda_LATENCY.json')
previous=f.read_bytes()
try:
 r=run(P/a.model,device='cuda',stability=0)
 (P/'results'/('repeat_'+__import__('pathlib').Path(a.model).stem+'.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
finally:f.write_bytes(previous)
