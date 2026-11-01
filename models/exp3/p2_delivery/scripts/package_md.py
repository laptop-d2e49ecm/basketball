from pathlib import Path
import json,zipfile,hashlib,time,shutil
P=Path(__file__).resolve().parents[1]
def load(f):return json.loads(f.read_text(encoding='utf-8-sig'))
assert load(P/'results/final_verification.json')['passed']
pdf=P/'reports/实验3报告_模型优化与对比验证.pdf'
qa=load(P/'reports/visual_review_md.json')
assert qa['pdf_sha256']==hashlib.sha256(pdf.read_bytes()).hexdigest() and qa['all_pages_visually_reviewed']
shutil.copy2(P/'README_MD_TEMPLATE.md',P/'README.md')
(P.parent/'README.md').write_text('# 实验3优化交付\n\n当前报告与完整交付见 [优化/README.md](优化/README.md)。以模型优化与对比验证报告为准。\n',encoding='utf-8')
(P.parent/'reports/README.md').write_text('# 当前正式报告\n\n请使用 [模型优化与对比验证](../优化/reports/实验3报告_模型优化与对比验证.pdf)。历史版本仅供留档。\n',encoding='utf-8')
items=[]
for f in P.rglob('*'):
 if not f.is_file():continue
 rel=f.relative_to(P)
 if any(x in ['dependencies','__pycache__','mplcache','rendered','rendered_md','tmp_layout'] for x in rel.parts):continue
 if f.suffix in ['.zip','.pyc','.lock'] or f.name in ['完整交付清单.json','完整交付校验.json','CPU交付清单.json','CPU交付校验.json']:continue
 items.append(f)
manifest=[{'path':f.relative_to(P).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(items)]
m=P/'完整交付清单.json';m.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');items.append(m)
out=P/'实验3_优化完整代码模型数据与报告.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
 for f in sorted(items):z.write(f,'优化/'+f.relative_to(P).as_posix())
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for r in manifest:assert hashlib.sha256(z.read('优化/'+r['path'])).hexdigest()==r['sha256']
result={'archive':str(out),'files':len(items),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'CRC_and_all_SHA256_verified':True,'scope':'CPU and GPU experiments with source weights, models, dataset, code and report','date':time.strftime('%Y-%m-%d %H:%M:%S')}
(P/'完整交付校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
