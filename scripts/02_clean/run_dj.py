# -*- coding: utf-8 -*-
"""dj-process.exe 的包装启动器（本机 torch DLL 兼容修复）。

问题：D:\Anaconda（全机安装）自带的 msvcp140.dll 为 14.27 旧版，先于 System32 命中，
torch 2.14 的 c10.dll 初始化即崩溃（WinError 1114）。
实测必须在导入任何扩展前、以解释器完全初始化后的方式显式预加载新版运行库
（vendor/ 下的 14.50 副本，取自 C:\Windows\System32），sitecustomize 时机无效。

用法（替代 dj-process）：
    python scripts/02_clean/run_dj.py --config configs/data_juicer_text.yaml
"""
import ctypes
import os
import sys

# 预加载 14.50 运行库；句柄全程持有，防止 GC 触发 FreeLibrary
_VCR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "vendor")
_HANDLES = []
for _name in ("msvcp140.dll",):
    _p = os.path.join(_VCR_DIR, _name)
    if os.path.exists(_p):
        _HANDLES.append(ctypes.WinDLL(_p))
del _p, _name

from data_juicer.tools.process_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
