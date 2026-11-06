import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const here = path.dirname(fileURLToPath(import.meta.url));
const workspace = path.resolve(here, '../..');
const bundle = path.join(workspace, '.runtime/basketball-remote/exp4/complete_web_system');
const require = createRequire(path.join(bundle, 'frontend/package.json'));
const { chromium } = require('@playwright/test');
const output = path.join(workspace, 'docs/验收记录/第三版真实视频联调_20261106');
await fs.mkdir(output, { recursive: true });
const sample = path.join(workspace, 'share_exp4_handoff/samples/18f2064977d665f5dd41a9c19c7e1635.mp4');
const videoName = `36秒真实联调_20261106_${Date.now()}`;
const record = {
  date: '2026-11-06', started_at: new Date().toISOString(), source_commit: 'cec6547bd893fe96a38414e590ef3699b26f82bb',
  scope: 'Third-version UI -> real API -> independent Worker -> real best.pt inference -> UI playback, detections and event seek. No API/WS mocks.',
  environment: { browser: 'Microsoft Edge', headless: true, viewport: { width: 1440, height: 1000 }, device: 'cpu', frame_step: 2, backend_mode: 'worker', isolated_database: true },
  sample: { file: path.basename(sample), bytes: (await fs.stat(sample)).size, sha256: createHash('sha256').update(await fs.readFile(sample)).digest('hex') },
  checks: [], screenshots: [], responses: [], websocket: [], page_errors: [], console_errors: [],
};
let browser, context, page, frame;
const pending = new Set();
function pass(name, details = {}) { record.checks.push({ name, status: 'passed', ...details }); console.log(`PASS ${name}`); }
async function waitFor(fn, label, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await fn()) return; await new Promise(r => setTimeout(r, 200)); }
  throw Error(`Timed out: ${label}`);
}
async function shot(name) { await page.screenshot({ path: path.join(output, name), fullPage: true }); record.screenshots.push(name); }
async function api(relative) {
  const r = await fetch(`http://127.0.0.1:8000/api/v1/${relative}`);
  const j = await r.json(); assert.equal(r.status, 200, relative); assert.equal(j.code, 0, relative); return j.result;
}
const videoState = () => frame.locator('#video').evaluate(v => ({ paused: v.paused, ended: v.ended, seeking: v.seeking, currentTime: v.currentTime, duration: v.duration, readyState: v.readyState, width: v.videoWidth, height: v.videoHeight, src: v.currentSrc, error: v.error?.message || null, totalVideoFrames: v.getVideoPlaybackQuality().totalVideoFrames }));
const canvasPixels = () => frame.locator('#detectionCanvas').evaluate(c => {
  const bytes = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
  let opaque = 0; for (let i=3;i<bytes.length;i+=4) if(bytes[i]) opaque++;
  return { width:c.width,height:c.height,nontransparent_pixels:opaque };
});
try {
  await waitFor(async () => { try { record.health = await api('health'); return record.health.status === 'ok'; } catch { return false; } }, 'real API startup', 120000);
  assert.equal(record.health.backend_mode, 'worker');
  assert.equal(record.health.video_frame_step, 2);
  pass('Real backend healthy with models loaded', record.health);
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  record.environment.browser_version = browser.version();
  context = await browser.newContext({ viewport: record.environment.viewport });
  await context.tracing.start({ screenshots: false, snapshots: false, sources: true });
  page = await context.newPage();
  page.on('pageerror', e => record.page_errors.push(e.message));
  page.on('console', m => { if(m.type()==='error') record.console_errors.push(m.text()); });
  page.on('response', response => {
    if (!response.url().includes('/api/v1/')) return;
    const work = (async () => {
      const row = { at: new Date().toISOString(), method: response.request().method(), url: response.url(), status: response.status() };
      if (response.headers()['content-type']?.includes('json')) row.body = await response.json();
      record.responses.push(row);
    })().catch(e => record.responses.push({ url: response.url(), read_error: e.message }));
    pending.add(work); work.finally(()=>pending.delete(work));
  });
  page.on('websocket', ws => { if(!ws.url().includes('/ws/task/')) return; ws.on('framereceived', ({payload}) => { try { record.websocket.push({ at: new Date().toISOString(), url: ws.url(), message: JSON.parse(String(payload)) }); } catch {} }); });
  await page.goto('http://127.0.0.1:5173/video-v3');
  frame = page.frameLocator('iframe');
  await frame.locator('#uploadBtn').waitFor();
  await frame.locator('#videoName').fill(videoName);
  await shot('01-上传前.png');
  pass('Third-version page loaded with empty task');
  await frame.locator('#analysisProgress').evaluate(el => {
    window.__progressAudit = [];
    const capture = () => window.__progressAudit.push({ time: Date.now(), value: Number(el.getAttribute('aria-valuenow')), text: document.querySelector('#analysisDetail').textContent, open: document.querySelector('#analysisDialog').open });
    new MutationObserver(capture).observe(el, { attributes: true, attributeFilter: ['aria-valuenow'] });
  });
  const choice = page.waitForEvent('filechooser');
  await frame.locator('#uploadBtn').click();
  const chooser = await choice;
  const createdPromise = page.waitForResponse(r => r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/tasks');
  const submitAt = Date.now();
  await chooser.setFiles(sample);
  await frame.getByRole('dialog', {name:'正在分析中，请稍等'}).waitFor({state:'visible'});
  const createdResponse = await createdPromise;
  record.create_http_status = createdResponse.status(); assert.equal(createdResponse.status(),202);
  record.created = (await createdResponse.json()).result;
  record.task_id = record.created.task_id;
  pass('Real MP4 uploaded through file chooser, HTTP 202', {task_id:record.task_id});
  await waitFor(async () => Number(await frame.locator('#analysisProgress').getAttribute('aria-valuenow')) > 0, 'real analysis progress', 120000);
  await shot('02-真实分析进度.png');
  pass('Waiting dialog shows real progress');
  await waitFor(async () => (await frame.locator('#videoStatus').textContent())==='分析完成', 'real video analysis completion', 180000);
  record.submit_to_visible_results_seconds = +( (Date.now()-submitAt)/1000 ).toFixed(3);
  assert.equal(await frame.locator('#analysisDialog').evaluate(d=>d.open), false);
  record.final_task = await api(`tasks/${record.task_id}`);
  record.events = await api(`tasks/${record.task_id}/events`);
  const detections = await api(`tasks/${record.task_id}/detections`);
  record.detection_summary = { records: detections.length, boxes: detections.reduce((n,f)=>n+(f.boxes?.length||0),0), first: detections[0], last: detections.at(-1) };
  await fs.writeFile(path.join(output,'detections.json'), JSON.stringify(detections));
  assert.equal(record.final_task.status,'ready');
  assert.equal(record.final_task.frames_done,record.final_task.frames_total);
  assert.equal(record.final_task.frames_done,450);
  assert.ok(record.events.length>0);
  assert.equal(await frame.locator('#eventList .event-row').count(), record.events.length);
  const uiTexts = await frame.locator('#eventList .event-name').allTextContents();
  assert.deepEqual(uiTexts, record.events.map(e=>e.text));
  pass('Worker inference completed and UI events match real backend', { frames: detections.length, events: record.events.length, submit_to_results_s:record.submit_to_visible_results_seconds });
  await waitFor(async () => (await videoState()).readyState>=2, 'real local video decode');
  record.local_video = await videoState();
  assert.ok(Math.abs(record.local_video.duration-36.04)<0.2);
  assert.ok(record.local_video.width>0 && record.local_video.height>0);
  assert.equal(record.local_video.error,null);
  await frame.locator('#boxesToggle').click();
  await waitFor(async () => (await canvasPixels()).nontransparent_pixels>0, 'real detection boxes painted');
  record.boxes_on = await canvasPixels();
  await shot('03-分析完成与检测框.png');
  await frame.locator('#boxesToggle').click();
  await waitFor(async () => (await canvasPixels()).nontransparent_pixels===0, 'boxes cleared');
  await frame.locator('#boxesToggle').click();
  pass('Real video decoded and detection overlay toggles on/off', record.boxes_on);
  const chart = await frame.locator('#countChart').evaluate(c=>({width:c.width,height:c.height,painted:c.getContext('2d').getImageData(0,0,c.width,c.height).data.some((x,i)=>i%4===3&&x>0)}));
  assert.ok(chart.painted);
  assert.equal(Number(await frame.locator('#eventMetric').textContent()), record.events.length);
  assert.equal(Number(await frame.locator('#peakMetric').textContent()),Math.max(...record.events.map(e=>e.player_count||0)));
  pass('Event count, player-count peak and chart match backend',chart);
  await frame.locator('#playBtn').click();
  await waitFor(async () => {const v=await videoState();return !v.paused&&v.currentTime>0.5&&v.totalVideoFrames>2}, 'video playing');
  const eventIndex=record.events.findIndex(e=>e.t_ms>=5000&&e.t_ms<30000);
  assert.ok(eventIndex>=0);
  record.seek_target_seconds=record.events[eventIndex].t_ms/1000;
  await frame.locator(`.event-row[data-event-index="${eventIndex}"]`).click();
  await waitFor(async () => {const v=await videoState();return v.paused&&Math.abs(v.currentTime-record.seek_target_seconds)<0.15}, 'event seek and pause');
  const before = await videoState();
  await new Promise(r=>setTimeout(r,1200));
  record.seek_state=await videoState();
  assert.ok(record.seek_state.paused&&Math.abs(record.seek_state.currentTime-before.currentTime)<0.05);
  await shot('04-点击事件后保持暂停.png');
  await frame.locator('#playBtn').click();
  await waitFor(async () => (await videoState()).currentTime>record.seek_target_seconds+0.5, 'manual resume');
  pass('Click event while playing seeks and stays paused; manual play resumes', {target_s:record.seek_target_seconds,paused_time_s:record.seek_state.currentTime});
  await frame.locator('.event-row[data-event-index="0"]').click();
  await waitFor(async()=> {const v=await videoState();return !v.seeking&&v.readyState>=3&&v.paused},'seek decode settled before replay');
  await frame.locator('#playBtn').click();
  console.log('Playing the complete 36-second video at normal speed...');
  record.playback_samples=[];
  let lastLog=0;
  await waitFor(async()=> {const v=await videoState(); if(Date.now()-lastLog>5000){lastLog=Date.now();record.playback_samples.push({at:new Date().toISOString(),...v});console.log(`Playback ${v.currentTime.toFixed(2)}/${v.duration} s; paused=${v.paused}; ready=${v.readyState}`)}return v.ended},'complete video playback',65000);
  record.played_to_end = await videoState();
  assert.ok(record.played_to_end.totalVideoFrames>800);
  await shot('05-完整视频播放结束.png');
  pass('36-second video played through to natural end at normal speed',record.played_to_end);
  record.progress_ui = await frame.locator('#analysisProgress').evaluate(()=>window.__progressAudit);
  assert.ok(record.progress_ui.some(p=>p.value>0&&p.value<100));
  assert.equal(record.progress_ui.at(-1).value,100);
  assert.ok(record.websocket.some(w=>w.message.type==='progress'));
  assert.ok(record.websocket.some(w=>w.message.type==='done'));
  pass('Actual WebSocket progress/done and final UI 100% recorded');
  await frame.locator('#historyTasksBtn').click();
  await frame.locator('#recentPage').waitFor({state:'visible'});
  const taskButton = frame.getByRole('button',{name:videoName,exact:true});
  await taskButton.waitFor();
  await shot('06-历史任务记录.png');
  await taskButton.click();
  await waitFor(async()=> { const v=await videoState(); return v.src.includes(`/tasks/${record.task_id}/preview`)&&v.readyState>=2 },'history compatible preview',120000);
  record.history_video = await videoState();
  record.preview_status=await api(`tasks/${record.task_id}/preview/status`);
  assert.equal(record.preview_status.status,'ready');
  await frame.locator('#playBtn').click();
  await waitFor(async()=> (await videoState()).currentTime>0.5,'history preview playing');
  await frame.locator(`.event-row[data-event-index="${eventIndex}"]`).click();
  await waitFor(async()=> (await videoState()).paused,'history event pause');
  await frame.locator('#boxesToggle').click();
  await waitFor(async()=> (await canvasPixels()).nontransparent_pixels>0,'history detection overlay');
  await shot('07-历史任务回放.png');
  pass('History task reloads server preview, events and detection overlay',record.preview_status);
  await frame.locator('#clearTaskBtn').click();
  assert.equal(await frame.locator('#video').getAttribute('src'),null);
  assert.equal(await frame.locator('#eventList .event-row').count(),0);
  assert.equal((await api(`tasks/${record.task_id}`)).status,'ready');
  await shot('08-清除当前任务.png');
  const nextChoice=page.waitForEvent('filechooser');
  await frame.locator('#uploadBtn').click();
  await nextChoice;
  pass('Clear resets the workspace, preserves saved task and allows selecting another video');
  assert.deepEqual(record.page_errors,[]);
  pass('No uncaught JavaScript errors during real workflow');
  record.status='passed';
} catch(e) {
  record.status='failed'; record.error=e.stack||String(e); console.error(record.error);
  if(frame) record.last_video_state=await videoState().catch(()=>null);
  if(page) await shot('failure.png').catch(()=>{});
  process.exitCode=1;
} finally {
  await Promise.allSettled([...pending]);
  if(context) await context.tracing.stop({path:path.join(output,'browser-trace.zip')}).catch(()=>{});
  if(browser) await browser.close();
  record.finished_at = new Date().toISOString();
  await fs.writeFile(path.join(output,'integration-result.json'),JSON.stringify(record,null,2));
  console.log(`Evidence: ${output}`);
  console.log(`Result: ${record.status}; ${record.checks.length} checks passed`);
}
