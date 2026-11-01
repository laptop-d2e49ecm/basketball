from bootstrap import P
import argparse,json,time,hashlib
from pathlib import Path
import numpy as np,cv2

def tensor(f):
 im=cv2.imdecode(np.frombuffer(Path(f).read_bytes(),np.uint8),cv2.IMREAD_COLOR);return np.ascontiguousarray(cv2.resize(im,(640,640))[...,::-1].transpose(2,0,1)[None]).astype(np.float32)/255

def run():
 import onnx, tempfile, importlib
 cv2.setNumThreads(1)
 tempfile.tempdir=str(P/"dependencies/pip_tmp");Path(tempfile.tempdir).mkdir(parents=True,exist_ok=True)
 from onnxruntime.quantization.quant_utils import add_infer_metadata
 def infer_memory(m):
  m=onnx.shape_inference.infer_shapes(m if isinstance(m,onnx.ModelProto) else onnx.load(m));add_infer_metadata(m);return m
 for modname in ["quantize","base_quantizer","onnx_quantizer","qdq_quantizer","calibrate","quant_utils"]:
  mod=importlib.import_module("onnxruntime.quantization."+modname)
  if hasattr(mod,"load_model_with_shape_infer"):mod.load_model_with_shape_infer=infer_memory
  if hasattr(mod,"save_and_reload_model_with_shape_infer"):mod.save_and_reload_model_with_shape_infer=infer_memory
 from onnxconverter_common import float16
 from onnxruntime.quantization import CalibrationDataReader,quantize_static,QuantFormat,QuantType,CalibrationMethod
 import onnxruntime as ort
 from onnxruntime.quantization.calibrate import CalibraterBase
 def create_session(self):
  o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1;o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
  self.infer_session=ort.InferenceSession(self.augmented_model_path,sess_options=o,providers=self.execution_providers)
 CalibraterBase.create_inference_session=create_session
 log={};src=P/'models/a2_fp32.onnx'
 class Reader(CalibrationDataReader):
  def __init__(self,files):self.files=files;self.it=iter(files)
  def get_next(self):
   f=next(self.it,None);return None if f is None else {'images':tensor(f)}
  def rewind(self):self.it=iter(self.files)
 fp=P/'models/a2_fp16.onnx'
 if not fp.exists():
  import subprocess,sys
  subprocess.run([sys.executable,str(P/'scripts/export_fp16.py')],check=True)
 for key,split,n,pc in [('val173_pt','val',173,False),('train500_pt','train',500,False),('train1000_pt','train',1000,False),('train1000_pc','train',1000,True),('train1000_pc_avx2','train',1000,True),('train1000_pc_dflfp32','train',1000,True),('train1000_pc_reglastfp32','train',1000,True),('train1000_pc_reg2fp32','train',1000,True)]:
  files=sorted((P/'data/images'/split).glob('*.jpg'))[:n];out=P/('models/a2_int8_'+key+'.onnx');t=time.time()
  lowrange=key.endswith(('avx2','dflfp32','reglastfp32','reg2fp32','reg2fp32'))
  excluded=[node.name for node in onnx.load(src).graph.node if (key.endswith(('dflfp32','reglastfp32','reg2fp32')) and 'dfl' in node.name) or (key.endswith(('reglastfp32','reg2fp32')) and any(node.name.endswith('/cv2.'+str(i)+'.2/Conv') for i in range(3))) or (key.endswith('reg2fp32') and any(node.name.endswith('/cv2.'+str(i)+'.1/conv/Conv') for i in range(3)))]
  if not out.exists():quantize_static(onnx.load(src),str(out),Reader(files),quant_format=QuantFormat.QDQ,activation_type=QuantType.QUInt8 if lowrange else QuantType.QInt8,weight_type=QuantType.QInt8,per_channel=pc,reduce_range=lowrange,calibrate_method=CalibrationMethod.MinMax,op_types_to_quantize=['Conv'],nodes_to_exclude=excluded,extra_options={'ActivationSymmetric':not lowrange,'WeightSymmetric':True})
  g=onnx.load(out);onnx.checker.check_model(g)
  log[key]={'calibration_split':split,'images':len(files),'per_channel':pc,'QDQ':'U8S8 reduced range (7-bit weight in INT8); nonConv float' if lowrange else 'S8S8 Conv; nonConv float','seconds':time.time()-t,'bytes':out.stat().st_size,'calibration_files':[f.name for f in files],'diagnostic_only':split=='val','excluded_nodes':excluded}
  (P/'results/quantization.json').write_text(json.dumps(log,indent=2),encoding='utf-8');print('QUANT_DONE',key,flush=True)
 import openvino as ov,nncf
 core=ov.Core();m=core.read_model(str(src));out=P/'models/a2_openvino_fp32';out.mkdir(exist_ok=True)
 ov.save_model(m,str(out/'model.xml'),compress_to_fp16=False)
 files=sorted((P/'data/images/train').glob('*.jpg'))[:1000]
 dataset=nncf.Dataset(files,lambda f:{'images':tensor(f)})
 out=P/'models/a2_openvino_int8';out.mkdir(exist_ok=True)
 if not (out/'model.xml').exists():
  q=nncf.quantize(m,dataset,subset_size=1000,preset=nncf.QuantizationPreset.MIXED,target_device=nncf.TargetDevice.CPU)
  ov.save_model(q,str(out/'model.xml'),compress_to_fp16=False)
 log['openvino']={'version':ov.__version__,'nncf':nncf.__version__,'calibration':'original train first1000','preset':'MIXED','target':'CPU'}
 (P/'results/quantization.json').write_text(json.dumps(log,indent=2),encoding='utf-8');print('OV_DONE',flush=True)
if __name__=='__main__':run()
