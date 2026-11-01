from bootstrap import P
import openvino as ov,nncf,json
from export_quant import tensor
from pathlib import Path
core=ov.Core();m=core.read_model(str(P/'models/a2_fp32.onnx'));files=sorted((P/'data/images/train').glob('*.jpg'))[:1000]
scope=nncf.IgnoredScope(patterns=['.*model.22/dfl.*'])
q=nncf.quantize(m,nncf.Dataset(files,lambda f:{'images':tensor(f)}),subset_size=1000,preset=nncf.QuantizationPreset.MIXED,target_device=nncf.TargetDevice.CPU,ignored_scope=scope)
out=P/'models/a2_openvino_int8_dflfp32';out.mkdir(exist_ok=True);ov.save_model(q,str(out/'model.xml'),compress_to_fp16=False)
(P/'results/ov_dfl_quantization.json').write_text(json.dumps({'calibration':'first1000 original train','ignore_patterns':['.*model.22/dfl.*'],'preset':'MIXED','note':'DFL distance expectation remains floating point; rest is NNCF PTQ'},indent=2),encoding='utf-8');print('OV_DFL_DONE',flush=True)
