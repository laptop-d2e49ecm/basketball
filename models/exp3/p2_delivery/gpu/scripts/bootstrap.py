from pathlib import Path
import site,sys,os
P=Path(__file__).resolve().parents[1]
STAGE1=P.parent.parent
SOURCE_ROOT=STAGE1.parent.parent
site.addsitedir(site.getusersitepackages())
site.addsitedir(str(STAGE1/'dependencies'))
site.addsitedir(str(STAGE1.parent/'实验3_剩余任务_20261025/dependencies'))
site.addsitedir(str(P/'dependencies'))
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
for stream in [sys.stdout,sys.stderr]:
 if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
