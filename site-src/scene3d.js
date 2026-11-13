/* Sentinel Vision — 3D for the site.
   1. A ceiling-mounted camera in the hero that turns to follow the pointer.
   2. A turntable of five floor models (office, shop, exam hall, plant, home) that rebuilds as the page scrolls.
   Everything is built from primitives; there are no model files to download. */
import {
  Scene, OrthographicCamera, PerspectiveCamera, WebGLRenderer, Group, Mesh, BoxGeometry, CylinderGeometry,
  SphereGeometry, CapsuleGeometry, ConeGeometry, ExtrudeGeometry, Shape, ShapeGeometry, EdgesGeometry, PCFShadowMap,
  LineSegments, LineLoop, BufferGeometry, Float32BufferAttribute, LineBasicMaterial, MeshStandardMaterial,
  MeshBasicMaterial, HemisphereLight, DirectionalLight, Vector3, DoubleSide, MathUtils
} from 'three';

const LEVEL = { ok: 0x1b8a4b, alert: 0xcf3a2b, notice: 0xc98a00 };
const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp01 = v => Math.min(1, Math.max(0, v));
const easeOutCubic = u => 1 - Math.pow(1 - u, 3);
const easeOutBack = u => { const c = 1.9; return 1 + (c + 1) * Math.pow(u - 1, 3) + c * Math.pow(u - 1, 2); };

function webglAvailable() {
  try { const c = document.createElement('canvas'); return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl'))); }
  catch (e) { return false; }
}

/* ---------- shared building blocks ---------- */
const mat = (color, extra) => new MeshStandardMaterial(Object.assign({ color, roughness: 0.92, metalness: 0 }, extra));
const MAT = {
  white: mat(0xf4f5f1), stone: mat(0xd6dad2), spruce: mat(0x0e2a21), moss: mat(0x35554a), wood: mat(0xdccfb4),
  lawn: mat(0xb7c8a7), hedge: mat(0x4d6a52), concrete: mat(0xcdd1ca), metal: mat(0x9ba49d, { roughness: 0.55 }),
  jarA: mat(0xa5513f), jarB: mat(0xcda44e), jarC: mat(0x7c987a), glass: mat(0xb9cdc8, { transparent: true, opacity: 0.32 }),
  roof: mat(0x1c3a30), skin: mat(0xe9d6c3)
};
function box(w, h, d, material, x, y, z) {           // y is the underside
  const m = new Mesh(new BoxGeometry(w, h, d), material);
  m.position.set(x || 0, (y || 0) + h / 2, z || 0); m.castShadow = true; m.receiveShadow = true; return m;
}
function cyl(r, h, material, x, y, z, seg) {
  const m = new Mesh(new CylinderGeometry(r, r, h, seg || 24), material);
  m.position.set(x || 0, (y || 0) + h / 2, z || 0); m.castShadow = true; m.receiveShadow = true; return m;
}
function person(x, z, opts) {
  opts = opts || {}; const g = new Group(); const seated = !!opts.seated; const base = seated ? 0.46 : 0;
  const len = seated ? 0.36 : 0.78;
  const body = new Mesh(new CapsuleGeometry(0.2, len, 6, 14), opts.material || MAT.moss);
  body.position.y = base + 0.2 + len / 2; body.castShadow = true;
  const head = new Mesh(new SphereGeometry(0.16, 18, 14), MAT.skin);
  head.position.y = base + 0.4 + len + 0.13; head.castShadow = true;
  g.add(body, head); g.position.set(x, 0, z); g.userData.height = base + 0.4 + len + 0.3; return g;
}
function statusBox(w, h, d, level, x, y, z) {
  const g = new Group(); const geo = new BoxGeometry(w, h, d);
  const lines = new LineSegments(new EdgesGeometry(geo), new LineBasicMaterial({ color: LEVEL[level] }));
  const fill = new Mesh(geo, new MeshBasicMaterial({ color: LEVEL[level], transparent: true, opacity: level === 'ok' ? 0.07 : 0.16, depthWrite: false }));
  g.add(fill, lines); g.position.set(x, y + h / 2, z); g.userData.level = level; g.userData.fill = fill; return g;
}
function zone(points, level) {                         // points: [[x, z], ...] on the floor
  const g = new Group(); const s = new Shape(); points.forEach((p, i) => (i ? s.lineTo(p[0], -p[1]) : s.moveTo(p[0], -p[1])));
  const fill = new Mesh(new ShapeGeometry(s), new MeshBasicMaterial({ color: LEVEL[level], transparent: true, opacity: 0.24, depthWrite: false, side: DoubleSide }));
  fill.rotation.x = -Math.PI / 2; fill.position.y = 0.025;
  const verts = []; points.forEach(p => verts.push(p[0], 0.035, p[1]));
  const line = new LineLoop(new BufferGeometry().setAttribute('position', new Float32BufferAttribute(verts, 3)), new LineBasicMaterial({ color: LEVEL[level] }));
  g.add(fill, line); g.userData.level = level; g.userData.fill = fill; return g;
}
function group() { const g = new Group(); for (let i = 0; i < arguments.length; i++) g.add(arguments[i]); return g; }

/* ---------- the four floors ---------- */
function buildOffice() {
  const pieces = [], labels = [];
  const state = ['alert-absent', 'ok', 'ok', 'alert-phone', 'ok', 'alert-phone'];   // same story as the demo video
  let n = 0;
  for (let row = 0; row < 3; row++) for (let col = 0; col < 2; col++) {
    const x = col ? 2.9 : -2.9, z = -3.4 + row * 3.4, st = state[n]; const id = ++n;
    const desk = group(box(2.3, 0.07, 1.1, MAT.wood, 0, 0.74, 0), box(0.07, 0.74, 1.0, MAT.white, -1.05, 0, 0), box(0.07, 0.74, 1.0, MAT.white, 1.05, 0, 0),
      box(0.74, 0.44, 0.05, MAT.spruce, 0, 0.92, 0.25), box(0.08, 0.14, 0.08, MAT.spruce, 0, 0.8, 0.25), box(0.5, 0.03, 0.18, MAT.spruce, 0, 0.81, -0.12));
    desk.position.set(x, 0, z); pieces.push(desk);
    const away = st === 'alert-absent';
    const chair = group(box(0.5, 0.08, 0.5, MAT.spruce, 0, 0.42, 0), box(0.5, 0.55, 0.07, MAT.spruce, 0, 0.5, -0.24), cyl(0.04, 0.42, MAT.metal, 0, 0, 0, 10));
    chair.position.set(x + (away ? 0.5 : 0), 0, z - (away ? 1.35 : 0.85)); chair.rotation.y = away ? 0.7 : 0; pieces.push(chair);
    if (!away) pieces.push(person(x, z - 0.8, { seated: true }));
    const level = st === 'ok' ? 'ok' : 'alert';
    pieces.push(statusBox(1.25, 1.45, 1.25, level, x, 0.02, z - 0.8));
    if (st === 'alert-phone') pieces.push(statusBox(0.24, 0.24, 0.24, 'notice', x + 0.12, 0.92, z - 0.5));
    if (id === 1) labels.push({ text: 'ID 1 · ABSENT', level: 'alert', pos: new Vector3(x, 1.75, z - 0.8) });
    if (id === 3) labels.push({ text: 'ID 3 · WORKING', level: 'ok', pos: new Vector3(x, 1.75, z - 0.8) });
    if (id === 6) labels.push({ text: 'ID 6 · PHONE USAGE', level: 'alert', pos: new Vector3(x, 1.75, z - 0.8) });
  }
  const planter = group(box(8.4, 0.75, 0.7, MAT.wood, 0, 0, 0));
  for (let i = 0; i < 9; i++) planter.add(box(0.7, 0.42, 0.5, MAT.hedge, -3.6 + i * 0.9, 0.75, 0));
  planter.position.set(0, 0, -5.6); pieces.push(planter);
  pieces.push(box(0.08, 2.3, 7.2, MAT.glass, 5.9, 0, 0.6));
  return { pieces, labels };
}

function shelfUnit(len) {
  const g = group(box(len, 1.7, 0.78, MAT.white, 0, 0, 0));
  const tones = [MAT.jarA, MAT.jarB, MAT.jarC];
  for (let level = 0; level < 3; level++) for (const side of [-1, 1]) {
    const strip = box(len - 0.2, 0.28, 0.1, tones[(level + (side > 0 ? 1 : 0)) % 3], 0, 0.28 + level * 0.46, side * 0.41);
    g.add(strip);
  }
  return g;
}
function buildShop() {
  const pieces = [], labels = [];
  const a = shelfUnit(6.2); a.rotation.y = Math.PI / 2; a.position.set(-5.2, 0, -0.4); pieces.push(a);
  const b = shelfUnit(6.2); b.rotation.y = Math.PI / 2; b.position.set(-2.2, 0, -0.4); pieces.push(b);
  pieces.push(group(box(11.5, 2.5, 0.16, MAT.stone, 0.6, 0, -5.4), box(1.3, 2.1, 0.06, MAT.moss, 3.6, 0, -5.29)));          // back wall + stockroom door
  pieces.push(group(box(1.0, 0.95, 4.2, MAT.metal, 3.4, 0, 1.6), box(0.5, 0.36, 0.3, MAT.spruce, 3.4, 0.95, 0.1)));           // checkout counter + till
  pieces.push(zone([[-4.55, -1.6], [-2.85, -1.6], [-2.85, 1.6], [-4.55, 1.6]], 'alert'));                                    // aisle dwell zone
  pieces.push(person(-3.9, 0.1)); pieces.push(statusBox(0.75, 1.75, 0.75, 'alert', -3.9, 0.02, 0.1));
  labels.push({ text: 'AISLE 1 · DWELL 6.2s', level: 'alert', pos: new Vector3(-3.9, 2.05, 0.1) });
  pieces.push(zone([[2.75, -5.2], [4.45, -5.2], [4.45, -3.6], [2.75, -3.6]], 'alert'));                                      // restricted door zone
  pieces.push(person(3.6, -4.3)); pieces.push(statusBox(0.75, 1.75, 0.75, 'alert', 3.6, 0.02, -4.3));
  labels.push({ text: 'STOCKROOM · ENTRY', level: 'alert', pos: new Vector3(3.6, 2.05, -4.3) });
  pieces.push(zone([[1.2, -0.7], [2.8, -0.7], [2.8, 4.3], [1.2, 4.3]], 'alert'));                                            // queue zone
  for (let i = 0; i < 4; i++) { pieces.push(person(2.0, -0.1 + i * 1.15)); }
  labels.push({ text: 'CHECKOUT · 4 OF 3', level: 'alert', pos: new Vector3(2.0, 2.05, 1.6) });
  pieces.push(person(4.4, 1.4, { material: MAT.spruce }));                                                                   // cashier
  pieces.push(person(-0.4, 3.2)); pieces.push(statusBox(0.75, 1.75, 0.75, 'ok', -0.4, 0.02, 3.2));
  return { pieces, labels };
}

function ellipse(cx, cz, rx, rz, level, y) {              // desk zone drawn on the desk top
  const pts = []; for (let i = 0; i < 28; i++) { const a = i / 28 * Math.PI * 2; pts.push([cx + Math.cos(a) * rx, cz + Math.sin(a) * rz]); }
  const g = zone(pts, level); g.position.y = y; return g;
}
function gazeLine(from, to, level) {                       // thin bar with an arrow head, from a head to a desk
  const g = new Group(); const dir = to.clone().sub(from); const len = dir.length(); dir.normalize();
  const m = new MeshBasicMaterial({ color: LEVEL[level] });
  const bar = new Mesh(new CylinderGeometry(0.03, 0.03, len - 0.3, 8), m); bar.position.y = (len - 0.3) / 2;
  const tip = new Mesh(new ConeGeometry(0.11, 0.3, 12), m); tip.position.y = len - 0.15;
  g.add(bar, tip); g.position.copy(from); g.quaternion.setFromUnitVectors(new Vector3(0, 1, 0), dir); return g;
}
function buildExam() {
  const pieces = [], labels = [];
  const empty = { 4: true, 9: true }, looking = 2, phone = 6;      // same story as the exam-hall clip: one look at a neighbour's desk, one phone
  const spot = {}; let n = 0;
  for (let row = 0; row < 3; row++) for (let col = 0; col < 3; col++) {
    const x = -3.7 + col * 3.7, z = -2.9 + row * 3.1, id = ++n; spot[id] = { x, z };
    const desk = group(box(1.5, 0.06, 0.82, MAT.wood, 0, 0.72, 0), box(0.42, 0.012, 0.3, MAT.white, 0.05, 0.78, -0.05));
    for (const sx of [-0.68, 0.68]) for (const sz of [-0.34, 0.34]) desk.add(box(0.06, 0.72, 0.06, MAT.metal, sx, 0, sz));
    desk.position.set(x, 0, z); pieces.push(desk);
    const chair = group(box(0.46, 0.06, 0.46, MAT.spruce, 0, 0.42, 0), box(0.46, 0.5, 0.06, MAT.spruce, 0, 0.48, -0.22), cyl(0.035, 0.42, MAT.metal, 0, 0, 0, 10));
    chair.position.set(x, 0, z - 0.72); pieces.push(chair);
    if (empty[id]) continue;
    const who = person(x, z - 0.7, { seated: true });
    if (id === looking) who.rotation.y = 1.0;
    pieces.push(who);
    const level = id === looking || id === phone ? 'alert' : 'ok';
    pieces.push(statusBox(0.95, 1.4, 0.95, level, x, 0.02, z - 0.7));
    pieces.push(ellipse(x, z, 0.9, 0.5, level, 0.765));
    if (id === phone) pieces.push(statusBox(0.22, 0.22, 0.22, 'notice', x - 0.3, 0.8, z - 0.18));
  }
  pieces.push(gazeLine(new Vector3(spot[looking].x + 0.1, 1.38, spot[looking].z - 0.62), new Vector3(spot[looking + 1].x - 0.25, 0.86, spot[looking + 1].z - 0.05), 'alert'));
  labels.push({ text: 'S2 · LOOKING AT DESK S3', level: 'alert', pos: new Vector3(spot[2].x, 2.6, spot[2].z - 0.7) });
  labels.push({ text: 'S6 · PHONE', level: 'alert', pos: new Vector3(spot[6].x, 1.75, spot[6].z - 0.7) });
  labels.push({ text: 'S7 · NORMAL', level: 'ok', pos: new Vector3(spot[7].x, 1.75, spot[7].z - 0.7) });
  const wall = group(box(11.4, 2.3, 0.14, MAT.white, 0, 0, 0), box(4.2, 1.1, 0.05, MAT.stone, -1.6, 0.85, 0.09), box(0.5, 0.5, 0.05, MAT.spruce, 3.6, 1.45, 0.09));
  wall.position.set(0, 0, -5.6); pieces.push(wall);
  pieces.push(box(0.08, 2.3, 7.4, MAT.glass, -6.1, 0, 0.3));
  return { pieces, labels };
}

function machine(x, z) {
  const g = group(box(2.6, 1.5, 1.8, MAT.spruce, 0, 0, 0), box(1.2, 0.5, 1.2, MAT.moss, -0.4, 1.5, 0), cyl(0.3, 1.0, MAT.metal, 0.85, 1.5, 0.3), box(0.6, 0.9, 0.08, MAT.jarB, 1.33, 0.4, 0));
  g.position.set(x, 0, z); return g;
}
function buildPlant() {
  const pieces = [], labels = [];
  pieces.push(machine(-3.2, -2.6)); pieces.push(machine(-3.2, 2.0));
  pieces.push(zone([[-5.3, -4.4], [-0.9, -4.4], [-0.9, -0.8], [-5.3, -0.8]], 'alert'));                                      // exclusion zone
  pieces.push(person(-1.5, -1.5)); pieces.push(statusBox(0.75, 1.75, 0.75, 'alert', -1.5, 0.02, -1.5));
  labels.push({ text: 'EXCLUSION ZONE · PERSON', level: 'alert', pos: new Vector3(-1.5, 2.05, -1.5) });
  pieces.push(zone([[-5.3, 0.2], [-0.9, 0.2], [-0.9, 3.8], [-5.3, 3.8]], 'ok'));
  pieces.push(zone([[1.0, -5.0], [2.9, -5.0], [2.9, 5.0], [1.0, 5.0]], 'ok'));                                               // corridor
  pieces.push(person(1.9, -2.6)); pieces.push(statusBox(0.75, 1.75, 0.75, 'ok', 1.9, 0.02, -2.6));
  pieces.push(person(2.0, 1.9)); pieces.push(statusBox(0.75, 1.75, 0.75, 'ok', 2.0, 0.02, 1.9));
  labels.push({ text: 'CORRIDOR · 2 OF 2', level: 'ok', pos: new Vector3(2.0, 2.05, 1.9) });
  for (let i = 0; i < 3; i++) pieces.push(group(box(1.2, 0.14, 1.2, MAT.wood, 4.9, 0, -3.4 + i * 2.6), box(1.05, 0.5 + i * 0.3, 1.05, MAT.white, 4.9, 0.14, -3.4 + i * 2.6)));
  return { pieces, labels };
}

function buildHome() {
  const pieces = [], labels = [];
  pieces.push(box(13.2, 0.06, 9.6, MAT.lawn, 0.2, 0, 0.4));                                                                    // lawn
  pieces.push(box(3.2, 0.09, 9.6, MAT.concrete, 4.6, 0, 0.4));                                                               // driveway
  pieces.push(box(1.2, 0.085, 4.6, MAT.concrete, -2.6, 0, 2.8));                                                             // front path
  const house = group(box(5.2, 2.5, 3.6, MAT.white, 0, 0, 0), box(0.9, 1.8, 0.06, MAT.moss, -0.3, 0, 1.83), box(1.1, 0.9, 0.05, MAT.glass, 1.4, 1.0, 1.83));
  const gable = new Shape(); gable.moveTo(-2.9, 0); gable.lineTo(2.9, 0); gable.lineTo(0, 1.7); gable.closePath();
  const roof = new Mesh(new ExtrudeGeometry(gable, { depth: 4.0, bevelEnabled: false }), MAT.roof);
  roof.position.set(0, 2.5, -2.0); roof.castShadow = true; house.add(roof);
  house.position.set(-2.3, 0, -2.6); pieces.push(house);
  const hedge = new Group(); for (let i = 0; i < 9; i++) hedge.add(box(0.95, 0.6, 0.6, MAT.hedge, -5.8 + i * 1.02, 0.06, 0)); hedge.position.set(0.4, 0, 4.8); pieces.push(hedge);
  pieces.push(zone([[3.1, -4.2], [6.1, -4.2], [6.1, 5.0], [3.1, 5.0]], 'notice'));
  const car = group(box(1.75, 0.62, 3.9, MAT.metal, 0, 0.3, 0), box(1.6, 0.6, 2.1, MAT.spruce, 0, 0.92, -0.2));
  for (const sx of [-0.86, 0.86]) for (const sz of [-1.25, 1.25]) { const w = cyl(0.34, 0.24, MAT.spruce, 0, 0, 0, 18); w.rotation.z = Math.PI / 2; w.position.set(sx, 0.34, sz); car.add(w); }
  car.position.set(4.6, 0.06, -0.6); pieces.push(car);
  pieces.push(statusBox(2.2, 1.75, 4.3, 'notice', 4.6, 0.08, -0.6));
  labels.push({ text: 'DRIVEWAY · VEHICLE', level: 'notice', pos: new Vector3(4.6, 2.1, -0.6) });
  pieces.push(zone([[-3.5, 0.2], [-1.7, 0.2], [-1.7, 5.0], [-3.5, 5.0]], 'alert'));
  pieces.push(person(-2.6, 1.6)); pieces.push(statusBox(0.75, 1.75, 0.75, 'alert', -2.6, 0.1, 1.6));
  labels.push({ text: 'FRONT PATH · PERSON', level: 'alert', pos: new Vector3(-2.6, 2.15, 1.6) });
  const dog = group(box(0.3, 0.3, 0.75, MAT.jarB, 0, 0.22, 0), box(0.26, 0.26, 0.3, MAT.jarB, 0, 0.42, 0.45), box(0.08, 0.08, 0.3, MAT.jarB, 0, 0.42, -0.5));
  for (const sx of [-0.1, 0.1]) for (const sz of [-0.28, 0.28]) dog.add(box(0.08, 0.22, 0.08, MAT.jarB, sx, 0, sz));
  dog.position.set(1.0, 0.06, 2.3); dog.rotation.y = -0.6; pieces.push(dog);
  pieces.push(statusBox(0.75, 0.85, 1.15, 'ok', 1.0, 0.08, 2.3));
  labels.push({ text: 'LAWN · PET, NO ALERT', level: 'ok', pos: new Vector3(1.0, 1.2, 2.3) });
  return { pieces, labels };
}

/* ---------- turntable ---------- */
function initTurntable(stage) {
  const canvas = stage.querySelector('canvas'); const labelLayer = stage.querySelector('.stage-labels');
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = PCFShadowMap;
  const scene = new Scene();
  const camera = new OrthographicCamera(-10, 10, 10, -10, 0.1, 100);
  const camDir = new Vector3(1, 0.86, 1).normalize();
  scene.add(new HemisphereLight(0xffffff, 0xc9cec6, 1.15));
  const sun = new DirectionalLight(0xffffff, 1.75); sun.position.set(7, 14, 5); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048); sun.shadow.camera.left = -12; sun.shadow.camera.right = 12; sun.shadow.camera.top = 12; sun.shadow.camera.bottom = -12;
  sun.shadow.camera.near = 1; sun.shadow.camera.far = 40; sun.shadow.bias = -0.0006; sun.shadow.radius = 5; scene.add(sun);

  const table = new Group(); scene.add(table);
  const plinth = new Mesh(new CylinderGeometry(9.3, 9.3, 0.36, 96), MAT.white); plinth.position.y = -0.18; plinth.receiveShadow = true; table.add(plinth);
  const rim = new Mesh(new CylinderGeometry(9.48, 9.48, 0.2, 96), MAT.spruce); rim.position.y = -0.36; table.add(rim);

  const floors = [buildOffice(), buildShop(), buildExam(), buildPlant(), buildHome()].map((f, index) => {
    const g = new Group(); g.visible = false; g.rotation.y = -index * Math.PI / 2; table.add(g);   // each floor faces front when the table has turned to it
    f.pieces.forEach(p => { g.add(p); p.userData.home = p.position.clone(); p.userData.delay = 0.05 + Math.hypot(p.position.x, p.position.z) * 0.055; p.scale.setScalar(0.0001); });
    const chips = f.labels.map(l => { const el = document.createElement('span'); el.className = 'chip3d'; el.dataset.level = l.level; el.textContent = l.text; labelLayer.appendChild(el); return { el, pos: l.pos }; });
    return { g, pieces: f.pieces, chips, shown: 0, at: 0, state: 'hidden' };
  });

  let active = -1, spin = 0, spinTarget = 0, scrollTurn = 0, px = 0, py = 0, running = false, last = performance.now(), clock = 0, visible = true, dirty = true;

  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return;
    renderer.setSize(w, h, false); const a = w / h; const view = Math.max(14.5, 20.4 / a);   // always fit the whole turntable
    camera.left = -view * a / 2; camera.right = view * a / 2; camera.top = view / 2; camera.bottom = -view / 2; camera.updateProjectionMatrix(); dirty = true;
  }
  function show(i) {
    if (i === active || !floors[i]) return;
    if (floors[active]) { floors[active].state = 'leaving'; floors[active].at = clock; }
    active = i; const f = floors[i]; f.g.visible = true; f.state = 'entering'; f.at = clock + (reduceMotion ? 0 : 0.28);
    spinTarget = i * Math.PI / 2; if (reduceMotion) spin = spinTarget; dirty = true;
  }
  const v = new Vector3();
  function frame(now) {
    const dt = Math.max(0, Math.min(0.05, (now - last) / 1000)); last = now; clock += dt;
    spin += (spinTarget - spin) * Math.min(1, dt * 4.2);
    table.rotation.y = spin + scrollTurn + (reduceMotion ? 0 : Math.sin(clock * 0.35) * 0.05);
    camera.position.copy(camDir).multiplyScalar(40); camera.position.x += px * 1.6; camera.position.y += 1 - py * 1.2; camera.lookAt(0, 1.1, 0);
    let moving = Math.abs(spinTarget - spin) > 0.001;
    floors.forEach((f, fi) => {
      if (f.state === 'hidden') return;
      const e = clock - f.at; let allDone = true;
      f.pieces.forEach(p => {
        let u;
        if (f.state === 'leaving') u = 1 - clamp01(e / 0.32); else u = reduceMotion ? 1 : clamp01((e - p.userData.delay) / 0.62);
        if (f.state === 'entering' && u < 1) allDone = false;
        if (f.state === 'leaving' && u > 0) allDone = false;
        const s = f.state === 'leaving' ? Math.max(0.0001, u) : Math.max(0.0001, easeOutBack(u));
        p.scale.setScalar(s); p.position.y = p.userData.home.y + (f.state === 'leaving' ? (1 - u) * -0.6 : (1 - easeOutCubic(u)) * 2.6);
        if (p.userData.level === 'alert' && p.userData.fill && !reduceMotion) p.userData.fill.material.opacity = 0.14 + 0.1 * (0.5 + 0.5 * Math.sin(clock * 3.2));
      });
      if (!allDone) moving = true;
      if (f.state === 'leaving' && allDone) { f.state = 'hidden'; f.g.visible = false; }
      if (f.state === 'entering' && allDone) f.state = 'shown';
      const labelsOn = fi === active && (f.state === 'shown' || e > 0.9);
      f.chips.forEach(c => {
        c.el.classList.toggle('on', labelsOn);
        if (!labelsOn) return;
        v.copy(c.pos); f.g.localToWorld(v); v.project(camera);
        c.el.style.transform = 'translate(-50%,-100%) translate(' + ((v.x * 0.5 + 0.5) * stage.clientWidth).toFixed(1) + 'px,' + ((-v.y * 0.5 + 0.5) * stage.clientHeight).toFixed(1) + 'px)';
      });
    });
    renderer.render(scene, camera); dirty = false;
    if (visible && (!reduceMotion || moving)) requestAnimationFrame(frame); else running = false;
  }
  function kick() { if (!running) { running = true; last = performance.now(); requestAnimationFrame(frame); } }

  new ResizeObserver(() => { resize(); kick(); }).observe(stage);
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }, { rootMargin: '200px' }).observe(stage);
  window.addEventListener('pointermove', e => { if (reduceMotion) return; px = e.clientX / window.innerWidth - 0.5; py = e.clientY / window.innerHeight - 0.5; }, { passive: true });
  resize();
  return { show(i) { show(i); kick(); }, turn(t) { if (!reduceMotion) { scrollTurn = t; } }, count: floors.length, debug() { return { active, clock, running, visible, states: floors.map(f => f.state + '@' + f.at.toFixed(2)) }; } };
}

/* ---------- hero camera ---------- */
function initHeroCamera(holder) {
  const canvas = holder.querySelector('canvas');
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new Scene(); const camera = new PerspectiveCamera(30, 1, 0.1, 100); camera.position.set(0, -1.1, 11.5); camera.lookAt(0, -1.25, 0);
  scene.add(new HemisphereLight(0xffffff, 0xc6ccc4, 1.25)); const key = new DirectionalLight(0xffffff, 1.6); key.position.set(-4, 6, 8); scene.add(key);

  const rig = new Group(); rig.position.set(3.3, 2.2, 0); scene.add(rig);
  rig.add(cyl(0.62, 0.12, MAT.white, 0, -0.12, 0, 40), cyl(0.1, 1.0, MAT.metal, 0, -1.12, 0, 16));
  const joint = new Mesh(new SphereGeometry(0.22, 24, 18), MAT.metal); joint.position.y = -1.2; rig.add(joint);
  const head = new Group(); head.position.y = -1.2; rig.add(head);
  const body = new Mesh(new CylinderGeometry(0.42, 0.42, 1.7, 40), MAT.white); body.rotation.x = Math.PI / 2; body.position.z = 0.75; head.add(body);
  const back = new Mesh(new SphereGeometry(0.42, 32, 20), MAT.white); back.position.z = -0.1; head.add(back);
  head.add(box(0.98, 0.07, 2.15, MAT.white, 0, 0.42, 0.85));                                           // sun shield
  const ring = new Mesh(new CylinderGeometry(0.44, 0.44, 0.16, 40), MAT.spruce); ring.rotation.x = Math.PI / 2; ring.position.z = 1.66; head.add(ring);
  const lens = new Mesh(new CylinderGeometry(0.27, 0.27, 0.06, 32), new MeshStandardMaterial({ color: 0x06140f, roughness: 0.15, metalness: 0.4 })); lens.rotation.x = Math.PI / 2; lens.position.z = 1.75; head.add(lens);
  const led = new Mesh(new SphereGeometry(0.045, 12, 10), new MeshBasicMaterial({ color: 0xcf3a2b })); led.position.set(0.27, 0.2, 1.75); head.add(led);
  const CONE = 7.2; const coneGeo = new ConeGeometry(2.5, CONE, 56, 1, true); coneGeo.translate(0, -CONE / 2, 0); coneGeo.rotateX(-Math.PI / 2);
  const cp = coneGeo.getAttribute('position'), cc = [];                        // fade the beam out along its length
  for (let i = 0; i < cp.count; i++) cc.push(1, 1, 1, Math.pow(1 - clamp01(cp.getZ(i) / CONE), 1.4));
  coneGeo.setAttribute('color', new Float32BufferAttribute(cc, 4));
  const cone = new Mesh(coneGeo, new MeshBasicMaterial({ color: 0x1b8a4b, vertexColors: true, transparent: true, opacity: 0.2, side: DoubleSide, depthWrite: false })); cone.position.z = 1.78; head.add(cone);

  let yaw = -2.2, pitch = -0.9, tYaw = -0.75, tPitch = 0.42, lastMove = -10, clock = 0, last = performance.now(), visible = true, running = false;
  function resize() { const w = holder.clientWidth, h = holder.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  function frame(now) {
    const dt = Math.max(0, Math.min(0.05, (now - last) / 1000)); last = now; clock += dt;
    let gy = tYaw, gp = tPitch;
    if (clock - lastMove > 3.5) { gy = -0.75 + Math.sin(clock * 0.5) * 0.55; gp = 0.42 + Math.sin(clock * 0.31) * 0.08; }   // idle patrol
    yaw += (gy - yaw) * Math.min(1, dt * 3.4); pitch += (gp - pitch) * Math.min(1, dt * 3.4);
    head.rotation.set(pitch, yaw, 0, 'YXZ');
    led.visible = reduceMotion || Math.floor(clock * 1.6) % 2 === 0;
    renderer.render(scene, camera);
    if (visible && !reduceMotion) requestAnimationFrame(frame); else running = false;
  }
  function kick() { if (!running) { running = true; last = performance.now(); requestAnimationFrame(frame); } }
  window.addEventListener('pointermove', e => {
    const r = holder.getBoundingClientRect(); const cx = r.left + r.width * 0.83, cy = r.top + r.height * 0.3;
    const dx = (e.clientX - cx) / window.innerWidth, dy = (e.clientY - cy) / window.innerHeight;
    tYaw = MathUtils.clamp(dx * 2.6, -1.35, 0.55); tPitch = MathUtils.clamp(0.16 + dy * 1.5, 0.16, 0.95); lastMove = clock;
  }, { passive: true });
  new ResizeObserver(() => { resize(); kick(); }).observe(holder);
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }).observe(holder);
  if (reduceMotion) { yaw = tYaw; pitch = tPitch; }
  resize(); kick();
}

/* ---------- wire up ---------- */
function start() {
  const stage = document.getElementById('stage'); const holder = document.getElementById('heroCam');
  if (!webglAvailable()) { document.documentElement.classList.add('no-webgl'); return; }
  document.documentElement.classList.add('has-webgl');
  try { if (holder && getComputedStyle(holder).display !== 'none') initHeroCamera(holder); } catch (e) { if (holder) holder.hidden = true; }
  if (!stage) return;
  let table;
  try { table = initTurntable(stage); } catch (e) { document.documentElement.classList.remove('has-webgl'); document.documentElement.classList.add('no-webgl'); return; }
  const steps = Array.prototype.slice.call(document.querySelectorAll('.floor-step'));
  const section = document.getElementById('floors');
  function pick() {
    const mid = window.innerHeight * (window.innerWidth <= 1040 ? 0.72 : 0.5); let best = 0, bestD = Infinity;
    steps.forEach((s, i) => { const r = s.getBoundingClientRect(); const d = Math.abs((r.top + r.bottom) / 2 - mid); if (d < bestD) { bestD = d; best = i; } });
    steps.forEach((s, i) => s.classList.toggle('active', i === best));
    table.show(best);
    const r = section.getBoundingClientRect(); const p = clamp01((window.innerHeight - r.top) / (r.height + window.innerHeight));
    table.turn((p - 0.5) * 0.7);
  }
  window.addEventListener('scroll', pick, { passive: true }); window.addEventListener('resize', pick);
  pick();
  window.__sentinel3d = { show: i => table.show(i), debug: () => table.debug() };
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
