"""CPU-only runtime setup. Never selects an accelerator."""
import os,site,sys
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='-1'
P=Path(__file__).resolve().parents[1]
site.addsitedir(site.getusersitepackages())
site.addsitedir(P/'dependencies')
# The current machine already has ORT/ONNX here; portable installs use requirements.txt.
site.addsitedir(P.parent/'dependencies')
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
