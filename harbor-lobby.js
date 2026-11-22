/* BLOCK HARBOR — autonomous rainy-deck lobby layer.
   Drop-in: <script type="module" src="harbor-lobby.js"></script> before </body>.
   Does NOT touch game code. Renders only while the lobby UI is visible. */
const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
const ADDON = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/';
import * as THREE from THREE_URL;

const $all = s => [...document.querySelectorAll(s)];
const txt = el => (el.textContent || '').trim();
const vis = el => { if (!el) return false; const r = el.getClientRects(); if (!r.length) return false;
  const c = getComputedStyle(el); return c.display !== 'none' && c.visibility !== 'hidden' && c.opacity !== '0'; };
const findText = s => $all('button,a,div,span,li').filter(e => txt(e).includes(s) && e.children.length < 4);

/* ---- addon loader pinned to our THREE (works with or without host importmap) ---- */
const shimCache = new Map();
async function shim(url) {
  if (shimCache.has(url)) return shimCache.get(url);
  const p = (async () => {
    let src = await (await fetch(url)).text();
    src = src.replace(/from\s*['"]three['"]/g, `from '${THREE_URL}'`);
    for (const m of [...src.matchAll(/from\s*['"](\.[^'"]+)['"]/g)]) {
      const sub = await shim(new URL(m[1], url).href);
      src = src.split(`'${m[1]}'`).join(`'${sub}'`).split(`"${m[1]}"`).join(`"${sub}"`);
    }
    return URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
  })();
  shimCache.set(url, p); return p;
}
const loadAddon = async path => import(await shim(ADDON + path));

/* ---- state ---- */
let renderer, scene, camera, lobby = null, active = false, raf = 0, clockT = 0, lastT = 0;
let hostCanvas = null, hostVis = '';
let quality = 'medium', night = false, nightMix = 0;
let yaw = 0, yawT = 0, dist = 9.5, distT = 9.5;
const slots = []; let playerName = 'NIGHT COURIER';
let audio = null, muted = false;

/* ---- UI chip (loading + sound) ---- */
const chip = document.createElement('div');
chip.style.cssText = 'position:fixed;left:10px;bottom:10px;z-index:2147483000;display:flex;gap:8px;align-items:center;font:12px/1 system-ui,sans-serif;color:#cfe0ea;pointer-events:none';
chip.innerHTML = `<span id="hl-state" style="background:rgba(10,16,22,.78);border:1px solid rgba(90,160,150,.5);padding:7px 11px;border-radius:9px;backdrop-filter:blur(4px)">در حال ساخت لابی…</span>
<button id="hl-snd" style="pointer-events:auto;background:rgba(10,16,22,.78);border:1px solid rgba(176,138,30,.6);color:#e8d9a0;padding:7px 10px;border-radius:9px;font:12px system-ui;cursor:pointer">🔊</button>`;
document.body.appendChild(chip);
const stateEl = chip.querySelector('#hl-state'), sndBtn = chip.querySelector('#hl-snd');
sndBtn.onclick = () => { muted = !muted; sndBtn.textContent = muted ? '🔇' : '🔊'; if (audio) audio.master.gain.value = muted ? 0 : 1; };

/* ---- ambience: rain noise + wind + distant horn (procedural, tied to visible rain) ---- */
function startAudio() {
  if (audio) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const master = ctx.createGain(); master.gain.value = muted ? 0 : 1; master.connect(ctx.destination);
    const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const d = buf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const rain = ctx.createBufferSource(); rain.buffer = buf; rain.loop = true;
    const rf = ctx.createBiquadFilter(); rf.type = 'lowpass'; rf.frequency.value = 1400;
    const rg = ctx.createGain(); rg.gain.value = .045;
    rain.connect(rf).connect(rg).connect(master); rain.start();
    const wind = ctx.createBufferSource(); wind.buffer = buf; wind.loop = true; wind.playbackRate.value = .35;
    const wf = ctx.createBiquadFilter(); wf.type = 'bandpass'; wf.frequency.value = 260; wf.Q.value = .8;
    const wg = ctx.createGain(); wg.gain.value = .03;
    const lfo = ctx.createOscillator(); lfo.frequency.value = .07;
    const lg = ctx.createGain(); lg.gain.value = .018; lfo.connect(lg).connect(wg.gain); lfo.start();
    wind.connect(wf).connect(wg).connect(master); wind.start();
    const horn = () => { if (!active) return;
      const t = ctx.currentTime, g = ctx.createGain();
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.035, t + .5); g.gain.exponentialRampToValueAtTime(.0001, t + 2.4);
      g.connect(master);
      for (const f of [98, 147]) { const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = f; o.connect(g); o.start(t); o.stop(t + 2.5); } };
    setInterval(horn, 32000); setTimeout(horn, 6000);
    audio = { ctx, master };
  } catch (e) { /* audio unavailable — silent */ }
}
addEventListener('pointerdown', startAudio, { once: true });

/* ---- renderer / scene ---- */
function initGL() {
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .9;
  if ('outputColorSpace' in renderer) renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const cv = renderer.domElement;
  cv.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:0;display:none;touch-action:none';
  document.body.insertBefore(cv, document.body.firstChild);
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x3a4550, .038);
  camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, .1, 140);
  hostCanvas = $all('canvas').find(c => c !== cv) || null;
  if (hostCanvas) hostVis = hostCanvas.style.visibility;
  addEventListener('resize', onResize);
  bindTouch(cv);
}
function onResize() {
  if (!renderer) return;
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  if (lobby) lobby.setSize();
}
function bindTouch(cv) {
  let px = 0, pinch = 0;
  cv.addEventListener('pointerdown', e => { px = e.clientX; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener('pointermove', e => { if (e.buttons || e.pointerType === 'touch') { yawT = THREE.MathUtils.clamp(yawT + (e.clientX - px) * .0035, -.6, .6); px = e.clientX; } });
  cv.addEventListener('touchmove', e => { if (e.touches.length === 2) {
    const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
    if (pinch) distT = THREE.MathUtils.clamp(distT - (d - pinch) * .02, 7.2, 12.5); pinch = d; } }, { passive: true });
  cv.addEventListener('touchend', () => pinch = 0);
  cv.addEventListener('dblclick', () => { yawT = 0; distT = 9.5; });
  cv.addEventListener('wheel', e => { distT = THREE.MathUtils.clamp(distT + e.deltaY * .004, 7.2, 12.5); }, { passive: true });
}

/* ---- sky / env / lights / rain / shafts / plates ---- */
function gradientTex(stops) {
  const c = document.createElement('canvas'); c.width = 2; c.height = 256;
  const g = c.getContext('2d'); const gr = g.createLinearGradient(0, 0, 0, 256);
  for (const [o, col] of stops) gr.addColorStop(o, col);
  g.fillStyle = gr; g.fillRect(0, 0, 2, 256);
  const t = new THREE.CanvasTexture(c);
  if ('colorSpace' in t) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const skyDay = gradientTex([[0, '#1a1e24'], [.72, '#39434d'], [1, '#55606a']]);
const skyNight = gradientTex([[0, '#0a0d13'], [.7, '#1a2230'], [1, '#2c3644']]);

function buildAtmosphere(root) {
  scene.background = skyDay;
  const pm = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  env.add(new THREE.Mesh(new THREE.SphereGeometry(20, 12, 8), new THREE.MeshBasicMaterial({ color: 0x10141a, side: THREE.BackSide })));
  const panel = (col, x, y, z, s) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(s, s), new THREE.MeshBasicMaterial({ color: col })); m.position.set(x, y, z); m.lookAt(0, 0, 0); env.add(m); };
  panel(0xcfe0ff, -8, 9, -6, 9); panel(0xffb36b, 7, 1.5, -4, 4); panel(0x33404c, 0, 12, 4, 10);
  const rt = pm.fromScene(env, .06); scene.environment = rt.texture; pm.dispose();
  env.traverse(o => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); });

  const hemi = new THREE.HemisphereLight(0x6b7c8c, 0x141a20, .55); root.add(hemi);
  const spot = new THREE.SpotLight(0xdfeaff, 3.2, 45, .62, .55, 0);
  spot.position.set(-5.5, 7, -6);
  const tgt = new THREE.Object3D(); tgt.position.set(2, 0, -4); root.add(tgt); spot.target = tgt; root.add(spot);
  spot.shadow.mapSize.set(1024, 1024); spot.shadow.camera.near = 2; spot.shadow.camera.far = 30;
  spot.shadow.bias = -.0004; spot.shadow.normalBias = .02;
  const warm = new THREE.PointLight(0xffb36b, .85, 10, 0); warm.position.set(5.4, .55, -4.6); root.add(warm);

  const shaftMats = [];
  const mkShaft = (radius, op, off) => {
    const from = new THREE.Vector3(-5.5, 7, -6), to = new THREE.Vector3(2 + off, 0, -4 + off * .4);
    const dir = from.clone().sub(to), len = dir.length();
    const mat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uColor: { value: new THREE.Color(0xbfd6ee) }, uOpacity: { value: op } },
      vertexShader: 'varying vec2 vUv;varying vec3 vN;varying vec3 vV;void main(){vUv=uv;vec4 wp=modelMatrix*vec4(position,1.0);vN=normalize(mat3(modelMatrix)*normal);vV=normalize(cameraPosition-wp.xyz);gl_Position=projectionMatrix*viewMatrix*wp;}',
      fragmentShader: 'uniform vec3 uColor;uniform float uOpacity;varying vec2 vUv;varying vec3 vN;varying vec3 vV;void main(){float a=pow(vUv.y,1.5)*pow(abs(dot(normalize(vN),normalize(vV))),1.4);gl_FragColor=vec4(uColor,a*uOpacity);}' });
    mat.userData.base = op; shaftMats.push(mat);
    const m = new THREE.Mesh(new THREE.ConeGeometry(radius, len, 20, 1, true), mat);
    m.position.copy(from).add(to).multiplyScalar(.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    m.renderOrder = 3; root.add(m); return m;
  };
  const shafts = [mkShaft(2.3, .16, 0), mkShaft(1.1, .10, 1.4)];

  const N = 360, pos = new Float32Array(N * 6), seeds = [];
  for (let i = 0; i < N; i++) seeds.push([-9 + Math.random() * 18, Math.random() * 10, -10 + Math.random() * 16, 6 + Math.random() * 3]);
  const rg = new THREE.BufferGeometry(); rg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const rain = new THREE.LineSegments(rg, new THREE.LineBasicMaterial({ color: 0xaebfd0, transparent: true, opacity: .28 }));
  rain.renderOrder = 4; rain.frustumCulled = false; root.add(rain);
  let rainCount = N;
  const updateRain = dt => {
    for (let i = 0; i < rainCount; i++) { const s = seeds[i];
      s[1] -= s[3] * dt; s[0] += .6 * dt; if (s[1] < 0) { s[1] += 10; s[0] = -9 + Math.random() * 18; }
      const j = i * 6; pos[j] = s[0]; pos[j + 1] = s[1]; pos[j + 2] = s[2];
      pos[j + 3] = s[0] + .1; pos[j + 4] = s[1] + .45; pos[j + 5] = s[2] + .02; }
    rg.attributes.position.needsUpdate = true; rg.setDrawRange(0, rainCount * 2);
  };
  return { hemi, spot, warm, shafts, shaftMats, updateRain, setRain: n => rainCount = n, envRT: rt };
}

/* ---- nameplates + slots ---- */
function makeSlots(root) {
  const defs = [[-2.4, 0, 0], [-.8, 0, .2], [.8, 0, .2], [2.4, 0, 0]];
  defs.forEach((p, i) => {
    const a = new THREE.Group(); a.position.set(...p); a.rotation.y = i === 0 ? -.12 : i === 3 ? .12 : 0;
    root.add(a);
    const cv = document.createElement('canvas'); cv.width = 256; cv.height = 80;
    const tex = new THREE.CanvasTexture(cv); if ('colorSpace' in tex) tex.colorSpace = THREE.SRGBColorSpace;
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(.95, .3),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
    pl.position.set(p[0], 2.18, p[2]); pl.renderOrder = 5; pl.visible = false; root.add(pl);
    slots.push({ anchor: a, plate: pl, cv, tex, mixer: null, clips: {}, avatar: null });
  });
}
function setSlotName(i, name) {
  const s = slots[i]; if (!s) return;
  if (!name) { s.plate.visible = false; if (s.avatar) s.avatar.visible = false; return; }
  if (s.avatar) s.avatar.visible = true;
  const g = s.cv.getContext('2d'); g.clearRect(0, 0, 256, 80);
  g.fillStyle = 'rgba(10,14,20,.75)'; g.strokeStyle = i === 0 ? 'rgba(176,138,30,.95)' : 'rgba(90,160,150,.9)'; g.lineWidth = 3;
  g.beginPath(); if (g.roundRect) g.roundRect(4, 4, 248, 72, 14); else g.rect(4, 4, 248, 72); g.fill(); g.stroke();
  g.fillStyle = '#eaf2f6'; g.font = 'bold 28px system-ui,sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(String(name).slice(0, 16), 128, 42);
  s.tex.needsUpdate = true; s.plate.visible = true;
}

/* ---- avatars from YOUR character.glb + AK117.glb ---- */
const CLIP_MAP = [['idle', /idle|stand|ایست/i], ['look', /look|نگاه/i], ['walk', /walk|راه/i], ['run', /run|دو/i], ['wave', /wave|تکان/i]];
async function loadAvatars() {
  let GLTFLoader, SkeletonUtils;
  try { ({ GLTFLoader } = await loadAddon('loaders/GLTFLoader.js'));
        ({ clone: SkeletonUtils } = await loadAddon('utils/SkeletonUtils.js')); }
  catch (e) { SkeletonUtils = o => o.clone(true); }
  const loader = GLTFLoader ? new GLTFLoader() : null;
  let char = null, gun = null;
  if (loader) {
    char = await loader.loadAsync('character.glb').catch(() => null);
    gun = await loader.loadAsync('AK117.glb').catch(() => null);
  }
  if (gun) { const b = new THREE.Box3().setFromObject(gun.scene); const L = b.getSize(new THREE.Vector3()).length() || 1;
    gun.scene.scale.multiplyScalar(.85 / L); }
  for (let i = 0; i < 4; i++) {
    const s = slots[i]; let av;
    if (char) {
      av = SkeletonUtils(char.scene);
      av.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
      if (char.animations.length) {
        s.mixer = new THREE.AnimationMixer(av);
        for (const [key, rx] of CLIP_MAP) { const c = char.animations.find(a => rx.test(a.name)); if (c) s.clips[key] = c; }
        if (!s.clips.idle) s.clips.idle = char.animations[0];
        playClip(i, 'idle');
      }
      if (gun) {
        const g = gun.scene.clone(true); let hand = null;
        av.traverse(o => { if (o.isBone && /hand.*r|r.*hand|right.*hand/i.test(o.name)) hand = o; });
        if (hand) { hand.add(g); g.position.set(0, 0, 0); }
        else { g.position.set(.22, 1.12, .28); av.add(g); }
        g.rotation.set(0, Math.PI, -.12);
      }
    } else {
      av = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CapsuleGeometry(.22, .9, 4, 12), new THREE.MeshStandardMaterial({ color: 0x3d5a66, roughness: .7 }));
      body.position.y = .95; body.castShadow = true; av.add(body);
      const vest = new THREE.Mesh(new THREE.BoxGeometry(.4, .42, .28), new THREE.MeshStandardMaterial({ color: 0x22303a, roughness: .8 }));
      vest.position.y = 1.12; vest.castShadow = true; av.add(vest);
      const head = new THREE.Mesh(new THREE.SphereGeometry(.14, 14, 10), new THREE.MeshStandardMaterial({ color: 0xc9b8a6, roughness: .8 }));
      head.position.y = 1.62; head.castShadow = true; av.add(head);
      const helm = new THREE.Mesh(new THREE.SphereGeometry(.155, 14, 8, 0, Math.PI * 2, 0, Math.PI * .55), new THREE.MeshStandardMaterial({ color: 0x2f4a50, roughness: .5, metalness: .3 }));
      helm.position.y = 1.66; av.add(helm);
      const gunM = new THREE.Mesh(new THREE.BoxGeometry(.07, .1, .72), new THREE.MeshStandardMaterial({ color: 0x22262b, roughness: .5, metalness: .6 }));
      gunM.position.set(.2, 1.1, .3); gunM.rotation.x = -.15; av.add(gunM);
    }
    av.visible = false; s.anchor.add(av); s.avatar = av;
  }
  setSlotName(0, playerName);
}
function playClip(i, key) {
  const s = slots[i]; if (!s || !s.mixer || !s.clips[key]) return;
  const next = s.mixer.clipAction(s.clips[key]);
  if (s.current === next) return;
  next.reset().fadeIn(.25).play();
  if (s.current) s.current.fadeOut(.25);
  s.current = next;
}

/* ---- environment: baked GLB, procedural fallback ---- */
const MIRROR_NAMES = ['left_wall', 'left_base', 'left_ribs', 'center_blue', 'center_blue_base', 'center_red', 'center_green', 'center_green_base', 'drum', 'crates_blue', 'crates_white', 'alum_stack', 'beige_case'];
async function loadEnvironment(root) {
  let gltf = null;
  try { const { GLTFLoader } = await loadAddon('loaders/GLTFLoader.js');
    gltf = await new GLTFLoader().loadAsync('assets/lobby.glb'); } catch (e) { gltf = null; }
  const mirrorSrc = [];
  if (gltf) {
    root.add(gltf.scene);
    gltf.scene.traverse(o => {
      if (!o.isMesh) return;
      const n = o.name || '';
      o.receiveShadow = /deck|steel/.test(n);
      o.castShadow = /left|center|drum|crates|alum|beige/.test(n);
      const m = o.material;
      if (m) { m.envMapIntensity = /alum/.test(n) ? 1.6 : /deck/.test(n) ? 1.3 : .7;
        if (/deck/.test(n)) { m.transparent = true; m.opacity = .85; m.roughness = .3; o.renderOrder = 1; }
        m.needsUpdate = true; }
      if (MIRROR_NAMES.some(k => n.includes(k))) mirrorSrc.push(o);
    });
    stateEl.textContent = 'لابی آماده ✓';
  } else {
    fallbackEnv(root, mirrorSrc);
    stateEl.textContent = 'لابی آماده (حالت سبک)';
  }
  const mirror = new THREE.Group(); mirror.scale.y = -1;
  for (const m of mirrorSrc) { const c = m.clone(); c.castShadow = c.receiveShadow = false;
    c.position.copy(m.position); c.quaternion.copy(m.quaternion); c.scale.copy(m.scale);
    m.updateWorldMatrix(true, false); c.applyMatrix4(m.matrixWorld); mirror.add(c); }
  root.add(mirror);
  return mirror;
}
function fallbackEnv(root, mirrorSrc) {
  const ct = (base, label) => { const c = document.createElement('canvas'); c.width = c.height = 256;
    const g = c.getContext('2d'); g.fillStyle = base; g.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 16; i++) { g.fillStyle = i % 2 ? 'rgba(0,0,0,.18)' : 'rgba(255,255,255,.10)'; g.fillRect(i * 16, 0, 8, 256); }
    for (let i = 0; i < 90; i++) { g.fillStyle = 'rgba(96,52,30,.25)'; g.fillRect(Math.random() * 256, Math.random() * 128, 3, 30 + Math.random() * 90); }
    if (label) { g.fillStyle = 'rgba(230,238,242,.8)'; g.font = 'bold 44px sans-serif'; g.fillText(label, 20, 140); }
    const t = new THREE.CanvasTexture(c); if ('colorSpace' in t) t.colorSpace = THREE.SRGBColorSpace; return t; };
  const mk = (w, h, d, x, y, z, mat, name) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z); m.name = name; m.castShadow = true; root.add(m); mirrorSrc.push(m); return m; };
  const deck = new THREE.Mesh(new THREE.PlaneGeometry(16, 14), new THREE.MeshStandardMaterial({ color: 0x2f5a52, roughness: .3, metalness: .55, transparent: true, opacity: .85, envMapIntensity: 1.3 }));
  deck.rotation.x = -Math.PI / 2; deck.position.set(0, 0, -2); deck.receiveShadow = true; deck.renderOrder = 1; root.add(deck);
  const std = (t, r = .6) => new THREE.MeshStandardMaterial({ map: t, roughness: r, metalness: .35, envMapIntensity: .7 });
  mk(2.7, 5.2, 9, -6.15, 2.6, -1.5, std(ct('#2d4e7a', 'Rohan')), 'left_wall');
  mk(3, 2.6, 2.44, -.7, 1.3, -7.8, std(ct('#33547f')), 'center_blue');
  mk(3, 2.6, 2.44, 2.3, 1.3, -7.8, std(ct('#7a3f33'), .68), 'center_red');
  mk(6.1, 2.6, 2.44, .8, 3.9, -7.8, std(ct('#2f4a50', '..VOGEL')), 'center_green');
  const drum = new THREE.Mesh(new THREE.CylinderGeometry(.35, .35, 1, 20), new THREE.MeshStandardMaterial({ color: 0xb9b8b0, roughness: .5, metalness: .55 }));
  drum.position.set(-3.6, .5, -1.5); drum.castShadow = true; root.add(drum); mirrorSrc.push(drum);
  mk(1.15, 1.56, .72, 5.55, .78, -6, new THREE.MeshStandardMaterial({ color: 0xcfd2d4, roughness: .35, metalness: .8, envMapIntensity: 1.6 }), 'alum_stack');
  mk(1.6, 2.2, 1.4, 7.6, 1.1, -4.6, std(ct('#cfc4a8'), .75), 'beige_case');
  const sea = new THREE.Mesh(new THREE.PlaneGeometry(240, 240), new THREE.MeshStandardMaterial({ color: 0x1d242b, roughness: .85 }));
  sea.rotation.x = -Math.PI / 2; sea.position.set(0, -.55, -40); root.add(sea);
}

/* ---- cheap bloom (high only) ---- */
let bloom = null;
function buildBloom() {
  const sz = renderer.getDrawingBufferSize(new THREE.Vector2());
  const rtS = new THREE.WebGLRenderTarget(sz.x, sz.y);
  if ('colorSpace' in rtS.texture) rtS.texture.colorSpace = THREE.SRGBColorSpace;
  const rtA = new THREE.WebGLRenderTarget(sz.x >> 2, sz.y >> 2), rtB = rtA.clone();
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  const V = 'varying vec2 vUv;void main(){vUv=position.xy*0.5+0.5;gl_Position=vec4(position.xy,0.0,1.0);}';
  const mat = (f, u) => new THREE.ShaderMaterial({ depthTest: false, depthWrite: false, toneMapped: false, uniforms: u, vertexShader: V, fragmentShader: f });
  const bright = mat('uniform sampler2D tex;varying vec2 vUv;void main(){vec3 c=texture2D(tex,vUv).rgb;float l=dot(c,vec3(0.299,0.587,0.114));gl_FragColor=vec4(c*smoothstep(0.72,1.0,l),1.0);}', { tex: { value: null } });
  const blur = mat('uniform sampler2D tex;uniform vec2 dir;varying vec2 vUv;void main(){vec3 s=texture2D(tex,vUv).rgb*0.227;s+=(texture2D(tex,vUv+dir*1.384).rgb+texture2D(tex,vUv-dir*1.384).rgb)*0.316;s+=(texture2D(tex,vUv+dir*3.230).rgb+texture2D(tex,vUv-dir*3.230).rgb)*0.070;gl_FragColor=vec4(s,1.0);}', { tex: { value: null }, dir: { value: new THREE.Vector2() } });
  const comp = mat('uniform sampler2D base;uniform sampler2D bl;varying vec2 vUv;void main(){gl_FragColor=vec4(texture2D(base,vUv).rgb+texture2D(bl,vUv).rgb*0.55,1.0);}', { base: { value: null }, bl: { value: null } });
  const fs = new THREE.Scene(); const fm = new THREE.Mesh(geo, bright); fm.frustumCulled = false; fs.add(fm);
  bloom = { rtS, rtA, rtB, bright, blur, comp, fs, fm, fc: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1) };
}
function renderFrame() {
  if (!bloom) { renderer.setRenderTarget(null); renderer.render(scene, camera); return; }
  const b = bloom;
  renderer.setRenderTarget(b.rtS); renderer.render(scene, camera);
  b.fm.material = b.bright; b.bright.uniforms.tex.value = b.rtS.texture;
  renderer.setRenderTarget(b.rtA); renderer.render(b.fs, b.fc);
  b.fm.material = b.blur; b.blur.uniforms.tex.value = b.rtA.texture; b.blur.uniforms.dir.value.set(1 / b.rtA.width, 0);
  renderer.setRenderTarget(b.rtB); renderer.render(b.fs, b.fc);
  b.blur.uniforms.tex.value = b.rtB.texture; b.blur.uniforms.dir.value.set(0, 1 / b.rtA.height);
  renderer.setRenderTarget(b.rtA); renderer.render(b.fs, b.fc);
  b.fm.material = b.comp; b.comp.uniforms.base.value = b.rtS.texture; b.comp.uniforms.bl.value = b.rtA.texture;
  renderer.setRenderTarget(null); renderer.render(b.fs, b.fc);
}

/* ---- quality ---- */
function setQuality(q) {
  quality = q;
  renderer.setPixelRatio(Math.min(devicePixelRatio, q === 'low' ? 1.5 : 2));
  renderer.shadowMap.enabled = q !== 'low';
  if (lobby) { lobby.atmo.spot.castShadow = q !== 'low'; lobby.mirror.visible = q !== 'low';
    lobby.atmo.setRain(q === 'low' ? 200 : 360); lobby.atmo.shafts[1].visible = q !== 'low'; }
  if (q === 'high' && !bloom) buildBloom();
  if (q !== 'high' && bloom) { bloom.rtS.dispose(); bloom.rtA.dispose(); bloom.rtB.dispose(); bloom = null; }
  onResize();
}

/* ---- DOM bridge to YOUR existing lobby UI (graceful: missing pieces are skipped) ---- */
function readName() {
  const inp = $all('input').find(i => (i.placeholder || '').includes('نام نمایشی'));
  if (inp && inp.value.trim().length >= 3) return inp.value.trim();
  const mark = $all('*').find(e => e.children.length === 0 && txt(e).startsWith('◈'));
  if (mark) return txt(mark).replace('◈', '').trim() || playerName;
  for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)) || '';
    if (v.length >= 3 && v.length <= 16 && /^[A-Za-z0-9 _\u0600-\u06FF-]+$/.test(v) && /name|player|نام/i.test(localStorage.key(i))) return v; }
  return playerName;
}
function readOnline() {
  const panel = findText('کاربران آنلاین').pop(); if (!panel) return [];
  const box = panel.closest('section,div') || panel;
  const bad = /آنلاین|آفلاین|اتصال|کاربران|ONLINE|دریافت|کد|لابی|ورود|خروج|بخش|سرور|استفاده|اطلاعات|دوستان|همگی|درخواست|نمایشی|هر کس/i;
  const names = [];
  for (const el of box.querySelectorAll('li,div,span')) {
    if (el.children.length) continue; const t = txt(el);
    if (t.length >= 3 && t.length <= 16 && !bad.test(t) && !/^\d+$/.test(t) && t !== playerName && !names.includes(t)) names.push(t);
    if (names.length >= 3) break;
  }
  return names;
}
function bridge() {
  document.addEventListener('click', e => {
    const t = txt(e.target.closest('button,a,[role=button]') || e.target);
    const anim = [['ایستادن', 'idle'], ['نگاه کردن', 'look'], ['راه رفتن', 'walk'], ['دویدن', 'run'], ['دست تکان دادن', 'wave']];
    for (const [label, key] of anim) if (t.includes(label)) { playClip(0, key); break; }
    if (t.includes('روز /')) night = !night;
    if (t.includes('ورود به میدان')) setActive(false);
    if (t.includes('ورود به لابی') || t.includes('تغییر نام') || t.includes('اعمال تنظیمات')) setTimeout(syncSettings, 120);
    setTimeout(checkActive, 60);
  }, true);
  document.addEventListener('input', e => { if (e.target.type === 'range') syncSettings(); }, true);
  document.addEventListener('change', e => { if (e.target.tagName === 'SELECT') syncSettings(); }, true);
  setInterval(() => { if (!active) return;
    const n = readName(); if (n !== playerName) { playerName = n; setSlotName(0, n); }
    const on = readOnline();
    for (let i = 1; i < 4; i++) setSlotName(i, on[i - 1] || null);
  }, 1500);
}
function syncSettings() {
  const sel = $all('select').find(s => s.innerText.includes('متوسط'));
  if (sel) setQuality(['low', 'medium', 'high'][sel.selectedIndex] || 'medium');
  const ranges = $all('input[type=range]');
  if (ranges[0]) { camera.fov = THREE.MathUtils.clamp(+ranges[0].value + 15, 60, 80); camera.updateProjectionMatrix(); }
  if (ranges[1]) renderer.toneMappingExposure = +ranges[1].value || .9;
  if (ranges[2] && lobby) lobby.atmo.hemi.intensity = (+ranges[2].value || .68) * .8;
}

/* ---- lobby detection: ON only while YOUR lobby UI is up ---- */
function lobbyVisible() {
  const enter = findText('ورود به میدان آنلاین').some(vis);
  const profile = findText('PLAYER PROFILE').some(vis) || findText('پیش‌نمایش انیمیشن').some(vis);
  const inGame = findText('شروع / ریستارت').some(vis) || (findText('امتیاز').some(vis) && !enter);
  const naming = findText('ورود به لابی').some(vis);
  return (enter || profile || naming) && !inGame;
}
function setActive(on) {
  if (on === active || !renderer) return;
  active = on;
  renderer.domElement.style.display = on ? 'block' : 'none';
  chip.style.display = on ? 'flex' : 'none';
  if (hostCanvas) hostCanvas.style.visibility = on ? 'hidden' : hostVis;
  if (on) { lastT = performance.now(); if (!raf) raf = requestAnimationFrame(tick); if (audio) audio.ctx.resume(); }
  else { cancelAnimationFrame(raf); raf = 0; if (audio) audio.ctx.suspend(); }
}
function checkActive() { setActive(lobbyVisible()); }

/* ---- main loop ---- */
function tick(now) {
  raf = requestAnimationFrame(tick);
  const dt = Math.min((now - lastT) / 1000, .05); lastT = now; clockT += dt;
  const t = clockT;
  yaw += (yawT - yaw) * Math.min(1, dt * 6); dist += (distT - dist) * Math.min(1, dt * 6);
  nightMix += ((night ? 1 : 0) - nightMix) * Math.min(1, dt * 1.5);
  const look = new THREE.Vector3(0, 1.3, -2);
  camera.position.set(Math.sin(yaw) * dist + .4 + Math.sin(t * .5) * .05,
    1.5 + Math.sin(t * .8) * .03, Math.cos(yaw) * dist);
  camera.lookAt(look.x + Math.sin(t * .33) * .02, look.y, look.z);
  if (lobby) {
    const a = lobby.atmo;
    a.updateRain(dt);
    a.hemi.intensity = THREE.MathUtils.lerp(.55, .22, nightMix);
    a.spot.intensity = THREE.MathUtils.lerp(3.2, 2.1, nightMix);
    a.warm.intensity = THREE.MathUtils.lerp(.85, 1.35, nightMix);
    scene.fog.color.setHex(nightMix > .5 ? 0x232c38 : 0x3a4550);
    scene.background = nightMix > .5 ? skyNight : skyDay;
    for (let i = 0; i < a.shaftMats.length; i++)
      a.shaftMats[i].uniforms.uOpacity.value = a.shaftMats[i].userData.base * (0.9 + .1 * Math.sin(t * 1.7 + i * 2.1)) * (1 + nightMix * .6);
  }
  for (const s of slots) { if (s.mixer) s.mixer.update(dt); if (s.plate.visible) s.plate.quaternion.copy(camera.quaternion); }
  renderFrame();
}

/* ---- boot ---- */
(async function boot() {
  try { initGL(); } catch (e) { chip.remove(); return; }
  const root = new THREE.Group(); scene.add(root);
  const atmo = buildAtmosphere(root);
  makeSlots(root);
  const mirror = await loadEnvironment(root);
  lobby = { root, atmo, mirror, setSize: () => { if (bloom) { const s = renderer.getDrawingBufferSize(new THREE.Vector2());
    bloom.rtS.setSize(s.x, s.y); bloom.rtA.setSize(Math.max(1, s.x >> 2), Math.max(1, s.y >> 2)); bloom.rtB.setSize(Math.max(1, s.x >> 2), Math.max(1, s.y >> 2)); } } };
  setQuality('medium'); syncSettings();
  playerName = readName();
  loadAvatars();
  bridge();
  setInterval(checkActive, 500); checkActive();
  addEventListener('pagehide', () => { cancelAnimationFrame(raf); renderer.dispose(); });
  setTimeout(() => { if (stateEl.textContent.includes('✓') || stateEl.textContent.includes('سبک')) stateEl.style.opacity = '.55'; }, 4000);
})();
