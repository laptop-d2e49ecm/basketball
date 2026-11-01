from pathlib import Path
import json
import pypdfium2 as pdfium
import pdfplumber
from PIL import Image
P=Path(__file__).resolve().parents[1];f=P/'reports/实验3报告_模型优化与对比验证.pdf';out=P/'reports/rendered_md';out.mkdir(exist_ok=True);pdf=pdfium.PdfDocument(f);images=[]
for i,page in enumerate(pdf):
 im=page.render(scale=1.3).to_pil().convert('RGB');im.save(out/('page_'+str(i+1).zfill(2)+'.png'));images.append(im)
for k in range(0,len(images),4):
 w,h=images[0].size;sheet=Image.new('RGB',(w*2,h*2),'#cccccc')
 for j,im in enumerate(images[k:k+4]):sheet.paste(im,((j%2)*w,(j//2)*h))
 sheet.save(out/('sheet_'+str(k//4+1)+'.png'))
checks=[]
with pdfplumber.open(f) as d:
 for i,p in enumerate(d.pages):
  text=p.extract_text() or '';assert len(text)>20
  assert all(c['x0']>=0 and c['x1']<=p.width+.5 and c['top']>=0 and c['bottom']<=p.height for c in p.chars)
  checks.append({'page':i+1,'chars':len(text),'bounds_ok':True})
(P/'reports/report_structure_md.json').write_text(json.dumps({'pages':len(images),'checks':checks},indent=2),encoding='utf-8');print('MD_REPORT_RENDERED',len(images),flush=True)
