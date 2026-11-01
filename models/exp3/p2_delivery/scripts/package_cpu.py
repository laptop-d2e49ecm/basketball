from pathlib import Path
import json,hashlib,zipfile,time,shutil
P=Path(__file__).resolve().parents[1]
def load(f):return json.loads(Path(f).read_text(encoding='utf-8'))
def main():
 assert load(P/'results/verification_cpu.json')['passed'];assert (P/'reports/实验3报告_CPU推理优化与验证.pdf').exists()
 r=load(P/'results/cpu_recommendation.json');best=r['recommended_result'];base=r['baseline_result']
 text=(P/'README_TEMPLATE.md').read_text(encoding='utf-8')
 for k,v in {'LABEL':r['label'],'MODEL':r['model'],'MODE':r['ov_mode'] or 'LATENCY','BASE_MS':format(base['lat_single_ms_p50'],'.2f'),'MS':format(best['lat_single_ms_p50'],'.2f'),'GAIN':format(r['single_latency_reduction_pct'],'.2f'),'FPS_GAIN':format(r['batch_fps_increase_pct'],'.2f'),'AP':format(best['map50_95']*100,'.2f')}.items():text=text.replace('{{'+k+'}}',str(v))
 (P/'README.md').write_text(text,encoding='utf-8')
 lines=["$ErrorActionPreference = 'Stop'",r"$taskPy = 'C:\Users\87273\Documents\Codex\2026-10-20\gei\work\yolov8s\.venv\Scripts\python.exe'","if (-not (Test-Path -LiteralPath $taskPy)) { $taskPy = 'python' }","$taskImage = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'data/images/test') -Filter '*.jpg' | Sort-Object Name | Select-Object -First 1).FullName","& $taskPy (Join-Path $PSScriptRoot 'scripts/run_cpu.py') --model (Join-Path $PSScriptRoot '"+r['model']+"') --image $taskImage --out (Join-Path $PSScriptRoot 'results/CPU推理示例.json') --conf .25 --ov-mode "+(r['ov_mode'] or 'LATENCY')+""]
 (P/'运行CPU推理.ps1').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
 root=P.parent;rf=root/'README.md'
 if rf.exists() and not (root/'README_历史存档.md').exists():shutil.copy2(rf,root/'README_历史存档.md')
 rf.write_text('# 实验3 CPU优化交付\n\n当前交付位于 [优化/README.md](优化/README.md)。请以 优化/reports/实验3报告_CPU推理优化与验证.pdf 为本次主报告。\n',encoding='utf-8')
 files=[]
 for f in P.rglob('*'):
  if not f.is_file():continue
  rel=f.relative_to(P)
  if any(x in ['dependencies','__pycache__','mplcache','rendered'] for x in rel.parts):continue
  if f.suffix in ['.zip','.pyc'] or f.name in ['CPU交付清单.json','CPU交付校验.json']:continue
  files.append(f)
 assert not any(f.suffix=='.engine' for f in files)
 manifest=[{'path':f.relative_to(P).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(files)]
 mf=P/'CPU交付清单.json';mf.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');files.append(mf)
 out=P/'实验3_CPU优化_完整代码模型数据与报告.zip'
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
  for f in sorted(files):z.write(f,'优化/'+f.relative_to(P).as_posix())
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  for m in manifest:assert hashlib.sha256(z.read('优化/'+m['path'])).hexdigest()==m['sha256']
 proof={'archive':str(out),'bytes':out.stat().st_size,'files':len(files),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'CRC_and_all_SHA256_verified':True,'scope':'CPU-only code/models/results/report','date':time.strftime('%Y-%m-%d %H:%M:%S')}
 (P/'CPU交付校验.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
