from bootstrap import P
import os,time

def acquire():
 f=(P/'results/gpu_experiment.lock').open('a+b');f.seek(0);f.write(b'0');f.flush()
 if os.name!='nt':
  import fcntl
  fcntl.flock(f.fileno(),fcntl.LOCK_EX);return f
 import msvcrt
 while True:
  try:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);return f
  except OSError:time.sleep(2)
