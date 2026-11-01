from bootstrap import P
import json,time,hashlib,os
import torch
import tensorrt as trt
log=trt.Logger(trt.Logger.WARNING);builder=trt.Builder(log);flags=0 if int(trt.__version__.split('.')[0])>=11 else 1<<int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED);network=builder.create_network(flags);parser=trt.OnnxParser(network,log)
source=P/'models/a2_fp16.onnx';ok=parser.parse(source.read_bytes());assert ok,'\n'.join(str(parser.get_error(i)) for i in range(parser.num_errors))
config=builder.create_builder_config();config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,512*1024**2)
profile=builder.create_optimization_profile();profile.set_shape('images',(1,3,640,640),(8,3,640,640),(32,3,640,640));config.add_optimization_profile(profile)
t=time.time();plan=builder.build_serialized_network(network,config);assert plan is not None
out=P/'models/a2_trt_fp16.engine';out.write_bytes(bytes(plan))
(P/'results/trt_build.json').write_text(json.dumps({'version':trt.__version__,'GPU':torch.cuda.get_device_name(),'CUDA':torch.version.cuda,'source':source.name,'precision':'explicit FP16 ONNX with FP32 I/O; strongly typed TensorRT'+trt.__version__.split('.')[0],'profile':{'min':1,'opt':8,'max':32},'workspace_MiB':512,'seconds':time.time()-t,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'Kaggle_T4_executed':('T4' in torch.cuda.get_device_name() and 'KAGGLE_KERNEL_RUN_TYPE' in os.environ),'portability':'engine tied to local GPU/software; rebuild on T4'},indent=2),encoding='utf-8');print('TRT_BUILD_OK',out,flush=True)
