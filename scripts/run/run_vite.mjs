// 前端启动器：Vite 在 Windows 上会调用 `net use` 探测网络盘，个别受限环境会因此启动失败；
// 这里只对这一个调用做无害短路，其余原样透传，然后加载 vite CLI。
// 前端目录默认按本文件位置推导（scripts/run → ../../exp4/complete_web_system/frontend），
// 也可用环境变量 VITE_CWD 覆盖。
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend =
  process.env.VITE_CWD ||
  path.resolve(here, '..', '..', 'exp4', 'complete_web_system', 'frontend');

const require = createRequire(path.join(frontend, 'package.json'));
const cp = require('child_process');
const realExec = cp.exec;
const realExecFile = cp.execFile;

const isNetUse = (cmd) => typeof cmd === 'string' && /^\s*net(\.exe)?\s+use/i.test(cmd);

cp.exec = function (cmd, opts, cb) {
  if (isNetUse(cmd)) {
    const callback = typeof opts === 'function' ? opts : cb;
    process.nextTick(() => callback && callback(null, '', ''));
    return { on() {}, kill() {}, stdout: { on() {} }, stderr: { on() {} } };
  }
  return realExec.apply(this, arguments);
};

cp.execFile = function (file, args, opts, cb) {
  if (typeof file === 'string' && /net(\.exe)?$/i.test(file)) {
    const callback = typeof opts === 'function' ? opts : cb;
    process.nextTick(() => callback && callback(null, '', ''));
    return { on() {}, kill() {}, stdout: { on() {} }, stderr: { on() {} } };
  }
  return realExecFile.apply(this, arguments);
};

process.chdir(frontend);
const viteCli = path.join(frontend, 'node_modules', 'vite', 'bin', 'vite.js');
await import(pathToFileURL(viteCli).href);
