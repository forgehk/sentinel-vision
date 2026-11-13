/* Sentinel Vision — the models, running in this browser.
   Loads YOLO26n or YOLO26n-pose (ONNX, 640 px, end-to-end head: no NMS step) with ONNX Runtime Web and runs it on an image.
   Nothing leaves the device: the image is read from a canvas and passed straight to WebAssembly.
   Output rows: objects = x1, y1, x2, y2, confidence, class.  pose = the same six, then 17 keypoints as x, y, confidence. */
const NAMES = ['person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light','fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket','bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed','dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink','refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush'];
const SIZE = 640;
const MODELS = {
  objects: { url: '/models/yolo26n-640.onnx', bytes: 9942036, name: 'YOLO26n', row: 6 },
  pose: { url: '/models/yolo26n-pose-640.onnx', bytes: 12126176, name: 'YOLO26n-pose', row: 57 }
};
let ort = null, threads = 1; const sessions = {};

export function info(kind) { return { threads, model: MODELS[kind].name, size: SIZE }; }
export function loaded(kind) { return !!sessions[kind]; }

export async function load(kind, onProgress) {
  if (sessions[kind]) return;
  const M = MODELS[kind]; if (!M) throw new Error('unknown model');
  if (!ort) {
    ort = await import('/ort/ort.wasm.min.mjs');
    threads = self.crossOriginIsolated ? Math.max(1, Math.min(4, navigator.hardwareConcurrency || 1)) : 1;
    ort.env.wasm.wasmPaths = '/ort/'; ort.env.wasm.numThreads = threads;
  }
  const res = await fetch(M.url); if (!res.ok) throw new Error('model file returned ' + res.status);
  const reader = res.body.getReader(), chunks = []; let got = 0;
  for (;;) { const { done, value } = await reader.read(); if (done) break; chunks.push(value); got += value.length; if (onProgress) onProgress(Math.min(1, got / M.bytes)); }
  const bytes = new Uint8Array(got); let at = 0; for (const c of chunks) { bytes.set(c, at); at += c.length; }
  const session = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
  await session.run({ [session.inputNames[0]]: new ort.Tensor('float32', new Float32Array(3 * SIZE * SIZE), [1, 3, SIZE, SIZE]) });   // warm-up so the first timed run is fair
  sessions[kind] = session;
}

/* source: image, video or canvas. w/h: its pixel size. Returns boxes (and keypoints, for pose) in source pixels and the inference time. */
export async function detect(kind, source, w, h, minConf) {
  const session = sessions[kind], row = MODELS[kind].row;
  if (!session) throw new Error('model not loaded');
  const g = Math.min(SIZE / w, SIZE / h), nw = Math.round(w * g), nh = Math.round(h * g), px = (SIZE - nw) >> 1, py = (SIZE - nh) >> 1;
  const c = document.createElement('canvas'); c.width = c.height = SIZE;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = 'rgb(114,114,114)'; ctx.fillRect(0, 0, SIZE, SIZE); ctx.drawImage(source, px, py, nw, nh);
  const d = ctx.getImageData(0, 0, SIZE, SIZE).data, n = SIZE * SIZE, x = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) { x[i] = d[i * 4] / 255; x[n + i] = d[i * 4 + 1] / 255; x[2 * n + i] = d[i * 4 + 2] / 255; }
  const t0 = performance.now();
  const out = await session.run({ [session.inputNames[0]]: new ort.Tensor('float32', x, [1, 3, SIZE, SIZE]) });
  const ms = performance.now() - t0, o = out[session.outputNames[0]].data, dets = [];
  for (let i = 0; i + row - 1 < o.length; i += row) {
    const score = o[i + 4]; if (score < (minConf || 0.3)) continue;
    const x1 = Math.max(0, Math.min(w, (o[i] - px) / g)), y1 = Math.max(0, Math.min(h, (o[i + 1] - py) / g));
    const x2 = Math.max(0, Math.min(w, (o[i + 2] - px) / g)), y2 = Math.max(0, Math.min(h, (o[i + 3] - py) / g));
    if (x2 - x1 < 2 || y2 - y1 < 2) continue;
    const det = { name: kind === 'pose' ? 'person' : NAMES[Math.round(o[i + 5])] || 'object', score, x1, y1, x2, y2 };
    if (kind === 'pose') { det.kp = []; for (let k = 0; k < 17; k++) det.kp.push([(o[i + 6 + k * 3] - px) / g, (o[i + 7 + k * 3] - py) / g, o[i + 8 + k * 3]]); }
    dets.push(det);
  }
  dets.sort((a, b) => b.score - a.score);
  return { dets, ms };
}
