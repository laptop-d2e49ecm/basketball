from bootstrap import P
import cv2,numpy as np,json,torch
from auto_infer import AutoDetector
f=sorted((P.parent/'data/images/test').glob('*.jpg'))[0];im=cv2.imdecode(np.frombuffer(f.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
checks=[]
for prefer in [True,False]:
 d=AutoDetector(prefer_gpu=prefer);y=d(im);assert y.ndim==2 and y.shape[1]==6 and np.isfinite(y).all()
 assert d.backend==('TensorRT GPU pipeline' if prefer and torch.cuda.is_available() else 'OpenVINO CPU')
 checks.append({'prefer_gpu':prefer,'actual_backend':d.backend,'detections':len(y),'finite_original_Nx6':True})
 if hasattr(d.detector,'close'):d.detector.close()
 del d;torch.cuda.empty_cache()
(P/'results/auto_deployment_verification.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2),encoding='utf-8');print('AUTO_DEPLOYMENT_VERIFIED')
