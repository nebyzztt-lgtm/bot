/**
 * RAFT ISLAND 3D - Videojuego de Supervivencia en Primera Persona
 * Versión Clean: Brazo 3D en primera persona, Cinemática inicial, Iconos vectoriales y Movimiento fluido.
 */

// ==========================================
// 1. CONFIGURACIÓN Y ESTADO DEL JUEGO
// ==========================================
const CONFIG = {
  GRAVITY: 28,
  WALK_SPEED: 7.5,
  RUN_SPEED: 13.5,
  SWIM_SPEED: 6.0,
  JUMP_FORCE: 9.8,
  WATER_LEVEL: 0.5,
  ISLAND_RADIUS: 95,
  FOG_DENSITY: 0.0055,
  MOUSE_SENSITIVITY: 0.002
};

const state = {
  health: 100,
  hunger: 90,
  thirst: 85,
  resources: {
    wood: 8,
    plastic: 6,
    stone: 4,
    coconut: 3,
    leaves: 4
  },
  activeSlot: 1,
  timePresetIndex: 0,
  isUnderwater: false,
  isCraftingOpen: false,
  buildMode: null,
  placedStructures: [],
  inCinematic: false,
  cinematicProgress: 0
};

// ==========================================
// 2. MOTOR DE AUDIO PROCEDURAL (Web Audio API)
// ==========================================
class SoundFX {
  constructor() {
    this.ctx = null;
    this.initialized = false;
  }

  init() {
    if (this.initialized) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
      this.initialized = true;
      this.startOceanAmbient();
    } catch (e) {
      console.warn("Audio Context:", e);
    }
  }

  startOceanAmbient() {
    if (!this.ctx) return;
    const bufferSize = this.ctx.sampleRate * 2;
    const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1;
    }

    const noise = this.ctx.createBufferSource();
    noise.buffer = buffer;
    noise.loop = true;

    const filter = this.ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 380;

    const gain = this.ctx.createGain();
    gain.gain.value = 0.07;

    noise.connect(filter);
    filter.connect(gain);
    gain.connect(this.ctx.destination);
    noise.start();

    setInterval(() => {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      filter.frequency.setTargetAtTime(280 + Math.sin(t * 0.4) * 120, t, 0.4);
    }, 400);
  }

  playStep(isWater = false) {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = isWater ? 'sine' : 'triangle';
    osc.frequency.setValueAtTime(isWater ? 170 : 85, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(30, this.ctx.currentTime + 0.07);

    gain.gain.setValueAtTime(isWater ? 0.09 : 0.05, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.07);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.08);
  }

  playHookThrow() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(420, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(110, this.ctx.currentTime + 0.22);

    gain.gain.setValueAtTime(0.15, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.22);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.23);
  }

  playChopWood() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(130, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(35, this.ctx.currentTime + 0.1);

    gain.gain.setValueAtTime(0.18, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.1);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.11);
  }

  playPickup() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(380, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(740, this.ctx.currentTime + 0.12);

    gain.gain.setValueAtTime(0.12, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.12);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.13);
  }

  playEat() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(260, this.ctx.currentTime);
    osc.frequency.setValueAtTime(310, this.ctx.currentTime + 0.07);

    gain.gain.setValueAtTime(0.12, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.18);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.19);
  }

  playBuild() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(210, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(420, this.ctx.currentTime + 0.12);

    gain.gain.setValueAtTime(0.11, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.12);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.13);
  }
}
const sfx = new SoundFX();

// ==========================================
// 3. ESCENA 3D Y RENDERER
// ==========================================
const container = document.getElementById('game-container');
const scene = new THREE.Scene();

const skyPresets = [
  { sky: 0x6ec6ff, fog: 0x81d4fa, ground: 0xecd189, sun: 0xfffaed, hemi: 0xdff3ff, name: "Mediodía Tropical" },
  { sky: 0xff7b54, fog: 0xfda085, ground: 0xb55400, sun: 0xffaa44, hemi: 0xffd2a6, name: "Atardecer Cálido" },
  { sky: 0x050b1a, fog: 0x081329, ground: 0x02050e, sun: 0x4f6d99, hemi: 0x1a263f, name: "Noche Estrellada" },
  { sky: 0xfdbb2d, fog: 0xf8b195, ground: 0xd97736, sun: 0xffe29f, hemi: 0xffeedb, name: "Amanecer Dorado" }
];

scene.fog = new THREE.FogExp2(skyPresets[0].fog, CONFIG.FOG_DENSITY);

const camera = new THREE.PerspectiveCamera(72, window.innerWidth / window.innerHeight, 0.1, 1400);
camera.position.set(22, 2.8, 22);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
container.appendChild(renderer.domElement);

// ==========================================
// 4. ILUMINACIÓN ESTILO RAFT
// ==========================================
const hemiLight = new THREE.HemisphereLight(skyPresets[0].hemi, skyPresets[0].ground, 0.7);
scene.add(hemiLight);

const sunLight = new THREE.DirectionalLight(skyPresets[0].sun, 1.4);
sunLight.position.set(120, 180, 90);
sunLight.castShadow = true;
sunLight.shadow.mapSize.width = 2048;
sunLight.shadow.mapSize.height = 2048;
sunLight.shadow.camera.near = 10;
sunLight.shadow.camera.far = 400;
const d = 80;
sunLight.shadow.camera.left = -d;
sunLight.shadow.camera.right = d;
sunLight.shadow.camera.top = d;
sunLight.shadow.camera.bottom = -d;
sunLight.shadow.bias = -0.0006;
scene.add(sunLight);

const ambientLight = new THREE.AmbientLight(0xffffff, 0.25);
scene.add(ambientLight);

// ==========================================
// 5. CÚPULA CELESTE Y NUBES ESTILIZADAS
// ==========================================
const skyGeo = new THREE.SphereGeometry(750, 32, 16);
const skyMat = new THREE.MeshBasicMaterial({ color: skyPresets[0].sky, side: THREE.BackSide });
const skyMesh = new THREE.Mesh(skyGeo, skyMat);
scene.add(skyMesh);

const cloudsGroup = new THREE.Group();
const cloudMat = new THREE.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, flatShading: true });
for (let i = 0; i < 20; i++) {
  const cloud = new THREE.Group();
  const puffs = 3 + Math.floor(Math.random() * 4);
  for (let p = 0; p < puffs; p++) {
    const puffGeo = new THREE.DodecahedronGeometry(12 + Math.random() * 9, 1);
    const puff = new THREE.Mesh(puffGeo, cloudMat);
    puff.position.set((p - puffs / 2) * 14 + Math.random() * 6, Math.random() * 4, Math.random() * 8);
    puff.scale.set(1.4, 0.7, 1);
    cloud.add(puff);
  }
  const angle = (i / 20) * Math.PI * 2;
  const dist = 180 + Math.random() * 180;
  cloud.position.set(Math.cos(angle) * dist, 70 + Math.random() * 30, Math.sin(angle) * dist);
  cloudsGroup.add(cloud);
}
scene.add(cloudsGroup);

// ==========================================
// 6. MAPEO PROCEDURAL DE LA ISLA (TERRENO SUAVE)
// ==========================================
const simplex = typeof SimplexNoise !== 'undefined' ? new SimplexNoise() : {
  noise2D: (x, y) => Math.sin(x) * Math.cos(y)
};

function getTerrainHeight(x, z) {
  const distFromCenter = Math.sqrt(x * x + z * z);
  if (distFromCenter > CONFIG.ISLAND_RADIUS) {
    return -4 - (distFromCenter - CONFIG.ISLAND_RADIUS) * 0.15;
  }

  const islandShapeMask = 1 - Math.pow(distFromCenter / CONFIG.ISLAND_RADIUS, 1.8);
  const n1 = simplex.noise2D(x * 0.018, z * 0.018);
  const n2 = simplex.noise2D(x * 0.045, z * 0.045) * 0.5;
  const n3 = simplex.noise2D(x * 0.1, z * 0.1) * 0.2;
  const combinedNoise = (n1 + n2 + n3 + 1.2) * 0.5;

  let h = combinedNoise * 18 * islandShapeMask;

  if (distFromCenter < 35) {
    const mountainFactor = (1 - distFromCenter / 35);
    h += Math.max(0, simplex.noise2D(x * 0.03, z * 0.03)) * 8 * mountainFactor;
  }

  if (h < 1.5) {
    h = h * 0.7 - 0.2;
  }

  return h;
}

const islandWidth = 260;
const islandSegments = 130;
const islandGeo = new THREE.PlaneGeometry(islandWidth, islandWidth, islandSegments, islandSegments);
islandGeo.rotateX(-Math.PI / 2);

const islandPositions = islandGeo.attributes.position;
const islandColors = new Float32Array(islandPositions.count * 3);

const colSand = new THREE.Color(0xe5cca0);
const colGrass = new THREE.Color(0x56a63e);
const colRock = new THREE.Color(0x64748b);
const colLush = new THREE.Color(0x3e8a2a);

for (let i = 0; i < islandPositions.count; i++) {
  const x = islandPositions.getX(i);
  const z = islandPositions.getZ(i);
  const y = getTerrainHeight(x, z);
  islandPositions.setY(i, y);

  let vertexCol = new THREE.Color();
  if (y < 1.8) {
    vertexCol.copy(colSand).offsetHSL((Math.random() - 0.5) * 0.02, 0, (Math.random() - 0.5) * 0.03);
  } else if (y < 8.5) {
    const blend = (y - 1.8) / 6.7;
    vertexCol.lerpColors(colGrass, colLush, blend);
  } else {
    vertexCol.copy(colRock).offsetHSL(0, 0, (Math.random() - 0.5) * 0.04);
  }

  islandColors[i * 3] = vertexCol.r;
  islandColors[i * 3 + 1] = vertexCol.g;
  islandColors[i * 3 + 2] = vertexCol.b;
}

islandGeo.setAttribute('color', new THREE.BufferAttribute(islandColors, 3));
islandGeo.computeVertexNormals();

const islandMat = new THREE.MeshStandardMaterial({
  vertexColors: true,
  roughness: 0.85,
  metalness: 0.05,
  flatShading: true
});

const islandMesh = new THREE.Mesh(islandGeo, islandMat);
islandMesh.receiveShadow = true;
islandMesh.castShadow = true;
scene.add(islandMesh);

// ==========================================
// 7. OCÉANO DINÁMICO ESTILO RAFT
// ==========================================
const waterGeo = new THREE.PlaneGeometry(1200, 1200, 90, 90);
waterGeo.rotateX(-Math.PI / 2);

const waterMat = new THREE.MeshStandardMaterial({
  color: 0x0088aa,
  roughness: 0.12,
  metalness: 0.25,
  transparent: true,
  opacity: 0.86,
  flatShading: true
});

const waterMesh = new THREE.Mesh(waterGeo, waterMat);
waterMesh.position.y = CONFIG.WATER_LEVEL;
waterMesh.receiveShadow = true;
scene.add(waterMesh);

const waterBasePositions = waterGeo.attributes.position.clone();

// ==========================================
// 8. ELEMENTOS DE LA ISLA: PALMERAS Y ROCAS
// ==========================================
const interactables = [];
const palmTrees = [];

function createPalmTree(x, z, scale = 1) {
  const group = new THREE.Group();
  const terrainY = getTerrainHeight(x, z);
  group.position.set(x, terrainY, z);
  group.scale.set(scale, scale, scale);

  const segments = 6;
  let currentY = 0;
  let currentXOffset = 0;
  const curveDir = Math.random() * Math.PI * 2;
  const trunkMat = new THREE.MeshStandardMaterial({ color: 0x8b5a2b, roughness: 0.9, flatShading: true });

  for (let s = 0; s < segments; s++) {
    const radiusTop = 0.45 - s * 0.03;
    const radiusBottom = 0.55 - s * 0.03;
    const height = 1.3;
    const segGeo = new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 6);
    const segMesh = new THREE.Mesh(segGeo, trunkMat);
    segMesh.castShadow = true;
    segMesh.receiveShadow = true;

    currentXOffset += Math.cos(curveDir) * (s * 0.12);
    segMesh.position.set(currentXOffset, currentY + height / 2, Math.sin(curveDir) * (s * 0.12));
    segMesh.rotation.z = Math.cos(curveDir) * 0.08 * s;
    group.add(segMesh);
    currentY += height;
  }

  const leafMat = new THREE.MeshStandardMaterial({
    color: 0x2e8b2e,
    roughness: 0.7,
    side: THREE.DoubleSide,
    flatShading: true
  });

  const leafCount = 9;
  for (let l = 0; l < leafCount; l++) {
    const angle = (l / leafCount) * Math.PI * 2;
    const leafGeo = new THREE.ConeGeometry(0.85, 4.2, 4);
    leafGeo.rotateX(Math.PI / 2.3);
    const leafMesh = new THREE.Mesh(leafGeo, leafMat);
    leafMesh.position.set(currentXOffset, currentY, Math.sin(curveDir) * (segments * 0.12));
    leafMesh.rotation.y = angle;
    leafMesh.castShadow = true;
    group.add(leafMesh);
  }

  const coconutMat = new THREE.MeshStandardMaterial({ color: 0x4a2e18, roughness: 0.85 });
  for (let c = 0; c < 3; c++) {
    const cocoGeo = new THREE.DodecahedronGeometry(0.3, 1);
    const cocoMesh = new THREE.Mesh(cocoGeo, coconutMat);
    const cAngle = (c / 3) * Math.PI * 2;
    cocoMesh.position.set(
      currentXOffset + Math.cos(cAngle) * 0.45,
      currentY - 0.2,
      Math.sin(curveDir) * (segments * 0.12) + Math.sin(cAngle) * 0.45
    );
    cocoMesh.castShadow = true;
    group.add(cocoMesh);
  }

  group.userData = { type: 'palmTree', health: 4, x, z };
  scene.add(group);
  palmTrees.push(group);
  interactables.push(group);
  return group;
}

function createRock(x, z, scale = 1) {
  const rockGeo = new THREE.DodecahedronGeometry(1.5 * scale, 1);
  const rockMat = new THREE.MeshStandardMaterial({ color: 0x71717a, roughness: 0.9, flatShading: true });
  const rockMesh = new THREE.Mesh(rockGeo, rockMat);
  const terrainY = getTerrainHeight(x, z);
  rockMesh.position.set(x, terrainY + 0.5 * scale, z);
  rockMesh.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, 0);
  rockMesh.castShadow = true;
  rockMesh.receiveShadow = true;
  rockMesh.userData = { type: 'rock', health: 3, x, z };
  scene.add(rockMesh);
  interactables.push(rockMesh);
}

for (let i = 0; i < 48; i++) {
  const angle = Math.random() * Math.PI * 2;
  const dist = 14 + Math.random() * (CONFIG.ISLAND_RADIUS - 22);
  const x = Math.cos(angle) * dist;
  const z = Math.sin(angle) * dist;
  const y = getTerrainHeight(x, z);

  if (y > 2.0 && y < 9.5) {
    createPalmTree(x, z, 0.8 + Math.random() * 0.4);
  } else if (y > 0.8) {
    createRock(x, z, 0.7 + Math.random() * 0.7);
  }
}

// ==========================================
// 9. LA BALSA INICIAL EN LA BAHÍA
// ==========================================
const raftGroup = new THREE.Group();
const raftWoodMat = new THREE.MeshStandardMaterial({ color: 0x82542a, roughness: 0.85, flatShading: true });

for (let rx = -1; rx <= 1; rx += 2) {
  for (let rz = -1; rz <= 1; rz += 2) {
    const plankGeo = new THREE.BoxGeometry(2.2, 0.35, 2.2);
    const plank = new THREE.Mesh(plankGeo, raftWoodMat);
    plank.position.set(rx * 1.15, 0, rz * 1.15);
    plank.castShadow = true;
    plank.receiveShadow = true;
    raftGroup.add(plank);
  }
}

const mastGeo = new THREE.CylinderGeometry(0.1, 0.12, 3.8, 6);
const mast = new THREE.Mesh(mastGeo, raftWoodMat);
mast.position.set(0, 1.9, 0);
raftGroup.add(mast);

const sailGeo = new THREE.PlaneGeometry(2.4, 2.6);
const sailMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.8, side: THREE.DoubleSide });
const sail = new THREE.Mesh(sailGeo, sailMat);
sail.position.set(0, 2.3, 0.1);
sail.rotation.y = 0.2;
raftGroup.add(sail);

raftGroup.position.set(28, CONFIG.WATER_LEVEL + 0.1, 28);
scene.add(raftGroup);

// ==========================================
// 10. BASURA FLOTANTE DEL OCÉANO
// ==========================================
const debrisList = [];
const debrisTypes = [
  { type: 'wood', color: 0xa06535, geo: () => new THREE.BoxGeometry(1.6, 0.25, 0.6), name: 'Tablón de Madera' },
  { type: 'plastic', color: 0x0284c7, geo: () => new THREE.CylinderGeometry(0.35, 0.35, 0.9, 8), name: 'Barril de Plástico' },
  { type: 'leaves', color: 0x4ade80, geo: () => new THREE.BoxGeometry(1.2, 0.05, 1.2), name: 'Hojas Tropicales' }
];

function spawnDebris() {
  if (debrisList.length >= 24) return;
  const dType = debrisTypes[Math.floor(Math.random() * debrisTypes.length)];
  const mat = new THREE.MeshStandardMaterial({ color: dType.color, roughness: 0.6, flatShading: true });
  const mesh = new THREE.Mesh(dType.geo(), mat);
  
  const spawnAngle = Math.random() * Math.PI * 2;
  const spawnDist = 85 + Math.random() * 55;
  mesh.position.set(
    Math.cos(spawnAngle) * spawnDist,
    CONFIG.WATER_LEVEL,
    Math.sin(spawnAngle) * spawnDist
  );
  mesh.castShadow = true;
  mesh.userData = {
    resourceType: dType.type,
    name: dType.name,
    speedX: -Math.cos(spawnAngle) * (0.04 + Math.random() * 0.04),
    speedZ: -Math.sin(spawnAngle) * (0.04 + Math.random() * 0.04),
    rotSpeed: (Math.random() - 0.5) * 0.02
  };

  scene.add(mesh);
  debrisList.push(mesh);
}

for (let d = 0; d < 18; d++) spawnDebris();
setInterval(spawnDebris, 3500);

// ==========================================
// 11. GAVIOTAS EN EL CIELO
// ==========================================
const seagulls = [];
function createSeagull() {
  const bird = new THREE.Group();
  const birdMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
  
  const wingLeft = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 0.35), birdMat);
  wingLeft.position.x = -0.6;
  bird.add(wingLeft);

  const wingRight = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 0.35), birdMat);
  wingRight.position.x = 0.6;
  bird.add(wingRight);

  bird.userData = {
    wingLeft,
    wingRight,
    angle: Math.random() * Math.PI * 2,
    radius: 40 + Math.random() * 60,
    speed: 0.008 + Math.random() * 0.006,
    height: 35 + Math.random() * 20
  };

  scene.add(bird);
  seagulls.push(bird);
}
for (let b = 0; b < 6; b++) createSeagull();

// ==========================================
// 12. BRAZO Y MANO EN PRIMERA PERSONA CON CADA OBJETO
// ==========================================
// Creamos un modelo de brazo humano estilizado (antebrazo + muñeca + mano)
const playerRig = new THREE.Group();

const skinMat = new THREE.MeshStandardMaterial({
  color: 0xdfab84,
  roughness: 0.65,
  metalness: 0.05
});

// Antebrazo derecho
const armGeo = new THREE.CylinderGeometry(0.065, 0.08, 0.65, 10);
armGeo.rotateZ(Math.PI / 12);
armGeo.rotateX(Math.PI / 5);
const armMesh = new THREE.Mesh(armGeo, skinMat);
armMesh.position.set(0.24, -0.28, -0.4);
playerRig.add(armMesh);

// Muñeca y Mano
const handGroup = new THREE.Group();
handGroup.position.set(0.18, -0.15, -0.55);

const palmGeo = new THREE.BoxGeometry(0.08, 0.05, 0.1);
const palmMesh = new THREE.Mesh(palmGeo, skinMat);
handGroup.add(palmMesh);

// Dedos envueltos
for (let f = 0; f < 4; f++) {
  const fingerGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.06, 6);
  const finger = new THREE.Mesh(fingerGeo, skinMat);
  finger.position.set(-0.03 + f * 0.02, 0.02, 0.05);
  finger.rotation.x = Math.PI / 3;
  handGroup.add(finger);
}

// Pulgar
const thumbGeo = new THREE.CylinderGeometry(0.014, 0.014, 0.05, 6);
const thumb = new THREE.Mesh(thumbGeo, skinMat);
thumb.position.set(-0.045, 0.01, 0.01);
thumb.rotation.z = Math.PI / 4;
handGroup.add(thumb);

playerRig.add(handGroup);

// Contenedores para las distintas herramientas sujetadas por la mano
const itemSlotModels = {
  1: new THREE.Group(), // Gancho (Hook)
  2: new THREE.Group(), // Coco (Coconut)
  3: new THREE.Group(), // Martillo / Plataforma
  4: new THREE.Group(), // Antorcha / Hoguera
  5: new THREE.Group()  // Lanza / Pared
};

// --- Modelo Slot 1: Gancho de Chatarra (Scrap Hook) ---
(function buildHook() {
  const hookG = itemSlotModels[1];
  const woodShaft = new THREE.Mesh(
    new THREE.CylinderGeometry(0.03, 0.035, 0.65, 8),
    new THREE.MeshStandardMaterial({ color: 0x5c3a21, roughness: 0.85 })
  );
  woodShaft.rotation.x = Math.PI / 4;
  hookG.add(woodShaft);

  // Cuerda atada
  const ropeTorus = new THREE.Mesh(
    new THREE.TorusGeometry(0.05, 0.02, 6, 10),
    new THREE.MeshStandardMaterial({ color: 0xd2b48c, roughness: 0.9 })
  );
  ropeTorus.position.set(0, -0.1, -0.1);
  ropeTorus.rotation.x = Math.PI / 4;
  hookG.add(ropeTorus);

  // 3 ganchos metálicos curvados
  const prongMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.3, metalness: 0.8 });
  for (let p = 0; p < 3; p++) {
    const prong = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.025, 0.3, 6), prongMat);
    const pAngle = (p / 3) * Math.PI * 2;
    prong.position.set(Math.cos(pAngle) * 0.07, 0.28, -0.22 + Math.sin(pAngle) * 0.07);
    prong.rotation.x = -Math.PI / 3;
    prong.rotation.z = Math.cos(pAngle) * 0.5;
    hookG.add(prong);
  }
  hookG.position.set(0, 0, 0.02);
  handGroup.add(hookG);
})();

// --- Modelo Slot 2: Coco Tropical Partido ---
(function buildCoconut() {
  const cocoG = itemSlotModels[2];
  // Cáscara exterior
  const shell = new THREE.Mesh(
    new THREE.DodecahedronGeometry(0.12, 1),
    new THREE.MeshStandardMaterial({ color: 0x4a2e18, roughness: 0.9 })
  );
  // Interior pulpa blanca
  const flesh = new THREE.Mesh(
    new THREE.CylinderGeometry(0.09, 0.09, 0.03, 10),
    new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.4 })
  );
  flesh.position.y = 0.06;
  cocoG.add(shell);
  cocoG.add(flesh);
  cocoG.position.set(0, 0.05, 0.06);
  cocoG.visible = false;
  handGroup.add(cocoG);
})();

// --- Modelo Slot 3: Martillo de Construcción ---
(function buildMallet() {
  const malletG = itemSlotModels[3];
  const handle = new THREE.Mesh(
    new THREE.CylinderGeometry(0.025, 0.025, 0.5, 6),
    new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.8 })
  );
  handle.rotation.x = Math.PI / 3;
  const head = new THREE.Mesh(
    new THREE.BoxGeometry(0.12, 0.12, 0.22),
    new THREE.MeshStandardMaterial({ color: 0x451a03, roughness: 0.9 })
  );
  head.position.set(0, 0.22, -0.15);
  malletG.add(handle);
  malletG.add(head);
  malletG.position.set(0, 0, 0.02);
  malletG.visible = false;
  handGroup.add(malletG);
})();

// --- Modelo Slot 4: Antorcha de Fuego ---
let torchFlameLight = null;
(function buildTorch() {
  const torchG = itemSlotModels[4];
  const woodTorch = new THREE.Mesh(
    new THREE.CylinderGeometry(0.035, 0.04, 0.55, 8),
    new THREE.MeshStandardMaterial({ color: 0x5c3a21, roughness: 0.9 })
  );
  woodTorch.rotation.x = Math.PI / 4;
  torchG.add(woodTorch);

  // Llama
  const flame = new THREE.Mesh(
    new THREE.ConeGeometry(0.08, 0.2, 6),
    new THREE.MeshBasicMaterial({ color: 0xffaa00 })
  );
  flame.position.set(0, 0.25, -0.18);
  torchG.add(flame);

  // Luz dinámica de la antorcha
  torchFlameLight = new THREE.PointLight(0xff7700, 2.2, 16);
  torchFlameLight.position.set(0, 0.28, -0.18);
  torchG.add(torchFlameLight);

  torchG.position.set(0, 0, 0.02);
  torchG.visible = false;
  handGroup.add(torchG);
})();

// --- Modelo Slot 5: Lanza de Madera ---
(function buildSpear() {
  const spearG = itemSlotModels[5];
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(0.022, 0.025, 1.2, 6),
    new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.85 })
  );
  shaft.rotation.x = Math.PI / 3;
  const tip = new THREE.Mesh(
    new THREE.ConeGeometry(0.04, 0.22, 6),
    new THREE.MeshStandardMaterial({ color: 0xd4d4d8, roughness: 0.4, metalness: 0.7 })
  );
  tip.position.set(0, 0.52, -0.32);
  tip.rotation.x = Math.PI / 3;
  spearG.add(shaft);
  spearG.add(tip);
  spearG.position.set(0, 0, 0.02);
  spearG.visible = false;
  handGroup.add(spearG);
})();

camera.add(playerRig);
scene.add(camera);

// Cambiar qué objeto se muestra en la mano
function updateVisibleHandItem(slotNum) {
  for (let s in itemSlotModels) {
    itemSlotModels[s].visible = (parseInt(s) === slotNum);
  }
}

// Estados de animación del brazo y herramientas
const armAnim = {
  isSwinging: false,
  swingProgress: 0,
  isEating: false,
  eatProgress: 0,
  isThrowingHook: false,
  hookThrownMesh: null,
  hookLine: null,
  hookReturn: false
};

// ==========================================
// 13. CINEMÁTICA INICIAL ELEGANTE
// ==========================================
const cinematicBars = document.getElementById('cinematic-bars');
const cineTitleBox = document.getElementById('cinematic-title-box');

// Puntos de la trayectoria cinematográfica
const cineCurve = new THREE.CatmullRomCurve3([
  new THREE.Vector3(0, 75, 160),     // Plano aéreo alto sobre el océano
  new THREE.Vector3(70, 38, 90),     // Bajada rápida sobre las olas y arrecifes
  new THREE.Vector3(45, 14, 45),     // Sobrevolando cerca de la balsa y palmeras
  new THREE.Vector3(26, 4.5, 26),    // Acercamiento suave a la playa
  new THREE.Vector3(22, 2.8, 22)     // Posición final de los ojos del jugador
]);

function startIntroCinematic() {
  state.inCinematic = true;
  state.cinematicProgress = 0;
  cinematicBars.classList.remove('hidden');
  cineTitleBox.style.opacity = '1';
  playerRig.visible = false; // Ocultar brazo durante la vista aérea

  // Sonido ambiental de bienvenida
  sfx.init();
}

function finishCinematic() {
  if (!state.inCinematic) return;
  state.inCinematic = false;
  cinematicBars.classList.add('hidden');
  playerRig.visible = true; // Mostrar brazo del jugador
  camera.position.set(22, 2.8, 22);
  euler.set(0, Math.PI / 4, 0, 'YXZ');
  camera.quaternion.setFromEuler(euler);
  showNotification("Has despertado en la isla. Usa el gancho para pescar provisiones.");
}

// Saltar cinemática con barra espaciadora
window.addEventListener('keydown', (e) => {
  if (state.inCinematic && e.code === 'Space') {
    finishCinematic();
  }
});

// ==========================================
// 14. CONTROLES Y FÍSICA FLUIDA EN PRIMERA PERSONA
// ==========================================
const keys = { w: false, a: false, s: false, d: false, space: false, shift: false };
const playerVelocity = new THREE.Vector3();
let isGrounded = false;
let isPointerLocked = false;
let euler = new THREE.Euler(0, 0, 0, 'YXZ');

const blocker = document.getElementById('blocker');
const playButton = document.getElementById('play-button');

function initPointerLock() {
  playButton.addEventListener('click', () => {
    document.body.requestPointerLock();
    startIntroCinematic();
  });

  document.addEventListener('pointerlockchange', () => {
    if (document.pointerLockElement === document.body) {
      isPointerLocked = true;
      blocker.style.display = 'none';
    } else {
      isPointerLocked = false;
      if (!state.isCraftingOpen && !state.inCinematic) {
        blocker.style.display = 'flex';
      }
    }
  });

  document.addEventListener('mousemove', (event) => {
    if (!isPointerLocked || state.inCinematic) return;
    const movementX = event.movementX || 0;
    const movementY = event.movementY || 0;

    euler.setFromQuaternion(camera.quaternion);
    euler.y -= movementX * CONFIG.MOUSE_SENSITIVITY;
    euler.x -= movementY * CONFIG.MOUSE_SENSITIVITY;
    euler.x = Math.max(-Math.PI / 2.15, Math.min(Math.PI / 2.15, euler.x));
    camera.quaternion.setFromEuler(euler);
  });
}
initPointerLock();

// Teclado
window.addEventListener('keydown', (e) => {
  if (state.inCinematic) return;
  const k = e.key.toLowerCase();
  if (k === 'w') keys.w = true;
  if (k === 'a') keys.a = true;
  if (k === 's') keys.s = true;
  if (k === 'd') keys.d = true;
  if (e.code === 'Space') keys.space = true;
  if (e.key === 'Shift') keys.shift = true;

  if (['1', '2', '3', '4', '5'].includes(k)) {
    setActiveSlot(parseInt(k));
  }
  if (k === 'e') {
    handleInteract();
  }
  if (k === 'c' || k === 'tab') {
    e.preventDefault();
    toggleCraftingMenu();
  }
  if (k === 'l') {
    cycleTimeOfDay();
  }
  if (k === 'b') {
    if (state.buildMode) {
      exitBuildMode();
    } else {
      enterBuildMode('foundation');
    }
  }
});

window.addEventListener('keyup', (e) => {
  const k = e.key.toLowerCase();
  if (k === 'w') keys.w = false;
  if (k === 'a') keys.a = false;
  if (k === 's') keys.s = false;
  if (k === 'd') keys.d = false;
  if (e.code === 'Space') keys.space = false;
  if (e.key === 'Shift') keys.shift = false;
});

// Clic de Acción
window.addEventListener('mousedown', (e) => {
  if (!isPointerLocked || state.inCinematic) return;
  if (e.button === 0) {
    if (state.buildMode) {
      placeBuiltStructure();
    } else if (state.activeSlot === 1) {
      triggerHookAction();
    } else if (state.activeSlot === 2) {
      eatCoconut();
    } else if ([3, 4, 5].includes(state.activeSlot)) {
      triggerToolSwing();
    }
  }
});

// ==========================================
// 15. ACCIONES CON HERRAMIENTAS Y LANZAMIENTO DEL GANCHO
// ==========================================
const raycaster = new THREE.Raycaster();
const screenCenter = new THREE.Vector2(0, 0);

function triggerToolSwing() {
  if (armAnim.isSwinging) return;
  armAnim.isSwinging = true;
  armAnim.swingProgress = 0;
  sfx.playBuild();
}

function triggerHookAction() {
  if (armAnim.isSwinging || armAnim.isThrowingHook) return;

  raycaster.setFromCamera(screenCenter, camera);
  const hits = raycaster.intersectObjects(scene.children, true);

  let targetObj = null;
  for (let hit of hits) {
    if (hit.distance <= 4.2) {
      let curr = hit.object;
      while (curr && curr !== scene) {
        if (curr.userData && (curr.userData.type || curr.userData.resourceType)) {
          targetObj = { obj: curr, hitPoint: hit.point };
          break;
        }
        curr = curr.parent;
      }
      if (targetObj) break;
    }
  }

  if (targetObj) {
    performMeleeSwing(targetObj);
  } else {
    throwHookLine();
  }
}

function performMeleeSwing(target) {
  armAnim.isSwinging = true;
  armAnim.swingProgress = 0;

  const uData = target.obj.userData;
  if (uData.type === 'palmTree') {
    sfx.playChopWood();
    createHitParticles(target.hitPoint, 0x8b5a2b);
    state.resources.wood += 2;
    state.resources.leaves += 1;
    if (Math.random() > 0.4) {
      state.resources.coconut += 1;
      showNotification("Cayó un coco fresco de la palmera");
    }
    showNotification("+2 Madera recolectada");
    updateUI();
  } else if (uData.type === 'rock') {
    sfx.playChopWood();
    createHitParticles(target.hitPoint, 0x71717a);
    state.resources.stone += 2;
    showNotification("+2 Piedra extraída de la roca");
    updateUI();
  } else if (uData.resourceType) {
    collectDebris(target.obj);
  }
}

function createHitParticles(pos, colorHex) {
  const pCount = 7;
  const pGeo = new THREE.DodecahedronGeometry(0.08, 0);
  const pMat = new THREE.MeshBasicMaterial({ color: colorHex });
  for (let i = 0; i < pCount; i++) {
    const pMesh = new THREE.Mesh(pGeo, pMat);
    pMesh.position.copy(pos);
    scene.add(pMesh);
    const vel = new THREE.Vector3(
      (Math.random() - 0.5) * 4,
      Math.random() * 3 + 1,
      (Math.random() - 0.5) * 4
    );
    let life = 0;
    const interval = setInterval(() => {
      pMesh.position.addScaledVector(vel, 0.03);
      vel.y -= 0.15;
      life++;
      if (life > 20) {
        clearInterval(interval);
        scene.remove(pMesh);
      }
    }, 25);
  }
}

function throwHookLine() {
  sfx.playHookThrow();
  armAnim.isThrowingHook = true;
  armAnim.hookReturn = false;

  const hookHead = new THREE.Mesh(
    new THREE.DodecahedronGeometry(0.18, 1),
    new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.3, metalness: 0.8 })
  );

  const startPos = new THREE.Vector3();
  camera.getWorldPosition(startPos);
  const forwardDir = new THREE.Vector3();
  camera.getWorldDirection(forwardDir);

  hookHead.position.copy(startPos).addScaledVector(forwardDir, 1);
  scene.add(hookHead);
  armAnim.hookThrownMesh = hookHead;

  const lineMat = new THREE.LineBasicMaterial({ color: 0xd2b48c, linewidth: 2 });
  const lineGeo = new THREE.BufferGeometry().setFromPoints([startPos, hookHead.position]);
  const ropeLine = new THREE.Line(lineGeo, lineMat);
  scene.add(ropeLine);
  armAnim.hookLine = ropeLine;

  const throwVelocity = forwardDir.clone().multiplyScalar(32);
  let timer = 0;
  let hookedItem = null;

  const flyInterval = setInterval(() => {
    timer += 0.03;
    if (!armAnim.hookReturn) {
      hookHead.position.addScaledVector(throwVelocity, 0.03);
      throwVelocity.y -= 0.4;

      for (let debris of debrisList) {
        if (hookHead.position.distanceTo(debris.position) < 2.5) {
          hookedItem = debris;
          armAnim.hookReturn = true;
          sfx.playPickup();
          showNotification(`Enganchado: ${debris.userData.name}`);
          break;
        }
      }

      if (hookHead.position.y <= CONFIG.WATER_LEVEL || timer > 1.2) {
        armAnim.hookReturn = true;
      }
    } else {
      const playerPos = new THREE.Vector3();
      camera.getWorldPosition(playerPos);
      playerPos.y -= 0.3;

      const returnDir = new THREE.Vector3().subVectors(playerPos, hookHead.position);
      const dist = returnDir.length();
      if (dist < 1.4) {
        clearInterval(flyInterval);
        scene.remove(hookHead);
        scene.remove(ropeLine);
        armAnim.isThrowingHook = false;
        if (hookedItem) {
          collectDebris(hookedItem);
        }
        return;
      }
      returnDir.normalize();
      hookHead.position.addScaledVector(returnDir, 28 * 0.03);

      if (hookedItem) {
        hookedItem.position.copy(hookHead.position);
      }
    }

    const camPos = new THREE.Vector3();
    camera.getWorldPosition(camPos);
    camPos.y -= 0.2;
    ropeLine.geometry.setFromPoints([camPos, hookHead.position]);
  }, 25);
}

function collectDebris(mesh) {
  const resType = mesh.userData.resourceType;
  sfx.playPickup();
  if (resType === 'wood') {
    state.resources.wood += 2;
    showNotification("+2 Madera recolectada del océano");
  } else if (resType === 'plastic') {
    state.resources.plastic += 2;
    showNotification("+2 Plástico recolectado");
  } else if (resType === 'leaves') {
    state.resources.leaves += 2;
    showNotification("+2 Hojas recolectadas");
  }
  updateUI();

  const idx = debrisList.indexOf(mesh);
  if (idx !== -1) debrisList.splice(idx, 1);
  scene.remove(mesh);
}

// ==========================================
// 16. CONSTRUCCIÓN HOLOGRÁFICA
// ==========================================
let ghostPreviewMesh = null;

function enterBuildMode(structureType) {
  state.buildMode = structureType;
  if (ghostPreviewMesh) scene.remove(ghostPreviewMesh);

  const ghostMat = new THREE.MeshBasicMaterial({
    color: 0x38bdf8,
    transparent: true,
    opacity: 0.45,
    wireframe: true
  });

  if (structureType === 'foundation') {
    ghostPreviewMesh = new THREE.Mesh(new THREE.BoxGeometry(3, 0.4, 3), ghostMat);
  } else if (structureType === 'campfire') {
    ghostPreviewMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 1, 0.6, 8), ghostMat);
  } else if (structureType === 'wall') {
    ghostPreviewMesh = new THREE.Mesh(new THREE.BoxGeometry(3, 2.4, 0.3), ghostMat);
  }

  scene.add(ghostPreviewMesh);
  showNotification(`Modo Construcción: ${structureType.toUpperCase()} (Clic para colocar)`);
}

function exitBuildMode() {
  state.buildMode = null;
  if (ghostPreviewMesh) {
    scene.remove(ghostPreviewMesh);
    ghostPreviewMesh = null;
  }
}

function updateGhostPlacement() {
  if (!ghostPreviewMesh || !state.buildMode) return;

  const camPos = new THREE.Vector3();
  camera.getWorldPosition(camPos);
  const lookDir = new THREE.Vector3();
  camera.getWorldDirection(lookDir);

  const targetX = camPos.x + lookDir.x * 5;
  const targetZ = camPos.z + lookDir.z * 5;
  let targetY = getTerrainHeight(targetX, targetZ);

  if (targetY < CONFIG.WATER_LEVEL) {
    targetY = CONFIG.WATER_LEVEL + 0.1;
  }

  ghostPreviewMesh.position.set(targetX, targetY + (state.buildMode === 'wall' ? 1.2 : 0.2), targetZ);
  ghostPreviewMesh.rotation.y = euler.y;
}

function placeBuiltStructure() {
  if (!state.buildMode || !ghostPreviewMesh) return;

  const costs = {
    foundation: { wood: 4, plastic: 2 },
    campfire: { wood: 4, stone: 4 },
    wall: { wood: 3, leaves: 1 }
  };

  const req = costs[state.buildMode];
  if (req) {
    for (let r in req) {
      if (state.resources[r] < req[r]) {
        showNotification("Recursos insuficientes para construir");
        return;
      }
    }
    for (let r in req) {
      state.resources[r] -= req[r];
    }
  }

  sfx.playBuild();
  const posX = ghostPreviewMesh.position.x;
  const posY = ghostPreviewMesh.position.y;
  const posZ = ghostPreviewMesh.position.z;
  const rotY = ghostPreviewMesh.rotation.y;

  if (state.buildMode === 'foundation') {
    const fMesh = new THREE.Mesh(
      new THREE.BoxGeometry(3, 0.4, 3),
      new THREE.MeshStandardMaterial({ color: 0x92613b, roughness: 0.9 })
    );
    fMesh.position.set(posX, posY, posZ);
    fMesh.rotation.y = rotY;
    fMesh.castShadow = true;
    fMesh.receiveShadow = true;
    scene.add(fMesh);
    state.placedStructures.push(fMesh);
    showNotification("Plataforma de madera colocada");
  } else if (state.buildMode === 'campfire') {
    const campGroup = new THREE.Group();
    for (let s = 0; s < 8; s++) {
      const sMesh = new THREE.Mesh(
        new THREE.DodecahedronGeometry(0.25, 0),
        new THREE.MeshStandardMaterial({ color: 0x555555, roughness: 0.9 })
      );
      const angle = (s / 8) * Math.PI * 2;
      sMesh.position.set(Math.cos(angle) * 0.7, 0.15, Math.sin(angle) * 0.7);
      campGroup.add(sMesh);
    }
    const woodLog = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.12, 1.1, 6),
      new THREE.MeshStandardMaterial({ color: 0x4a2e18 })
    );
    woodLog.rotation.z = Math.PI / 4;
    campGroup.add(woodLog);

    const fireLight = new THREE.PointLight(0xff7700, 2.5, 18);
    fireLight.position.set(0, 0.8, 0);
    fireLight.castShadow = true;
    campGroup.add(fireLight);

    const flameMesh = new THREE.Mesh(
      new THREE.ConeGeometry(0.35, 0.8, 6),
      new THREE.MeshBasicMaterial({ color: 0xffaa00 })
    );
    flameMesh.position.set(0, 0.5, 0);
    campGroup.add(flameMesh);

    campGroup.position.set(posX, posY, posZ);
    scene.add(campGroup);
    state.placedStructures.push(campGroup);
    showNotification("Hoguera encendida");
  } else if (state.buildMode === 'wall') {
    const wMesh = new THREE.Mesh(
      new THREE.BoxGeometry(3, 2.4, 0.3),
      new THREE.MeshStandardMaterial({ color: 0x7c4f2c, roughness: 0.9 })
    );
    wMesh.position.set(posX, posY, posZ);
    wMesh.rotation.y = rotY;
    wMesh.castShadow = true;
    wMesh.receiveShadow = true;
    scene.add(wMesh);
    state.placedStructures.push(wMesh);
    showNotification("Pared colocada");
  }

  updateUI();
  exitBuildMode();
}

// ==========================================
// 17. SUPERVIVENCIA Y CONSUMO DE COCOS
// ==========================================
function eatCoconut() {
  if (state.resources.coconut > 0 && !armAnim.isEating) {
    state.resources.coconut--;
    armAnim.isEating = true;
    armAnim.eatProgress = 0;
    state.hunger = Math.min(100, state.hunger + 25);
    state.thirst = Math.min(100, state.thirst + 35);
    sfx.playEat();
    showNotification("+25 Hambre, +35 Sed recuperados");
    updateUI();
  } else if (state.resources.coconut <= 0) {
    showNotification("No te quedan cocos. Tala una palmera.");
  }
}

setInterval(() => {
  if (!isPointerLocked || state.inCinematic) return;
  state.hunger = Math.max(0, state.hunger - 1);
  state.thirst = Math.max(0, state.thirst - 1.5);

  if (state.hunger <= 0 || state.thirst <= 0) {
    state.health = Math.max(0, state.health - 2);
    if (state.health <= 0) {
      showNotification("Desmayo por agotamiento. Reapareciendo...");
      state.health = 100;
      state.hunger = 80;
      state.thirst = 80;
      camera.position.set(22, 2.8, 22);
    }
  }
  updateUI();
}, 4500);

// ==========================================
// 18. CICLO DE ILUMINACIÓN Y HORA DEL DÍA
// ==========================================
function cycleTimeOfDay() {
  state.timePresetIndex = (state.timePresetIndex + 1) % skyPresets.length;
  applyTimePreset(state.timePresetIndex);
}

function applyTimePreset(index) {
  const p = skyPresets[index];
  scene.fog.color.setHex(p.fog);
  skyMat.color.setHex(p.sky);
  hemiLight.color.setHex(p.hemi);
  hemiLight.groundColor.setHex(p.ground);
  sunLight.color.setHex(p.sun);

  if (index === 0) {
    sunLight.position.set(120, 180, 90);
    sunLight.intensity = 1.4;
    renderer.toneMappingExposure = 1.15;
  } else if (index === 1) {
    sunLight.position.set(160, 45, -80);
    sunLight.intensity = 1.7;
    renderer.toneMappingExposure = 1.25;
  } else if (index === 2) {
    sunLight.position.set(-60, 100, 60);
    sunLight.intensity = 0.25;
    renderer.toneMappingExposure = 0.75;
  } else if (index === 3) {
    sunLight.position.set(-160, 50, 40);
    sunLight.intensity = 1.5;
    renderer.toneMappingExposure = 1.2;
  }

  document.getElementById('time-text').innerText = p.name;
  showNotification(`Hora: ${p.name}`);
}

// ==========================================
// 19. INTERFAZ DE USUARIO Y CRAFTEO
// ==========================================
function setActiveSlot(slotNum) {
  state.activeSlot = slotNum;
  document.querySelectorAll('.hotbar-slot').forEach(slot => {
    slot.classList.toggle('active', parseInt(slot.dataset.slot) === slotNum);
  });

  updateVisibleHandItem(slotNum);

  if ([3, 4, 5].includes(slotNum)) {
    const modeMap = { 3: 'foundation', 4: 'campfire', 5: 'wall' };
    enterBuildMode(modeMap[slotNum]);
  } else {
    exitBuildMode();
  }
}

document.querySelectorAll('.hotbar-slot').forEach(slot => {
  slot.addEventListener('click', () => {
    setActiveSlot(parseInt(slot.dataset.slot));
  });
});

function updateUI() {
  document.getElementById('health-bar').style.width = `${state.health}%`;
  document.getElementById('health-val').innerText = Math.round(state.health);

  document.getElementById('hunger-bar').style.width = `${state.hunger}%`;
  document.getElementById('hunger-val').innerText = Math.round(state.hunger);

  document.getElementById('thirst-bar').style.width = `${state.thirst}%`;
  document.getElementById('thirst-val').innerText = Math.round(state.thirst);

  document.getElementById('res-wood').innerText = state.resources.wood;
  document.getElementById('res-plastic').innerText = state.resources.plastic;
  document.getElementById('res-stone').innerText = state.resources.stone;
  document.getElementById('res-coconut').innerText = state.resources.coconut;
  document.getElementById('res-leaves').innerText = state.resources.leaves;
}
updateUI();

function showNotification(text) {
  const box = document.getElementById('notification-box');
  const notif = document.createElement('div');
  notif.className = 'notification';
  notif.innerText = text;
  box.appendChild(notif);
  setTimeout(() => {
    notif.style.opacity = '0';
    setTimeout(() => notif.remove(), 400);
  }, 2600);
}

const craftingOverlay = document.getElementById('crafting-overlay');
const closeCraftingBtn = document.getElementById('close-crafting-btn');

function toggleCraftingMenu() {
  state.isCraftingOpen = !state.isCraftingOpen;
  craftingOverlay.classList.toggle('hidden', !state.isCraftingOpen);

  if (state.isCraftingOpen) {
    document.exitPointerLock();
  } else {
    document.body.requestPointerLock();
  }
}

closeCraftingBtn.addEventListener('click', toggleCraftingMenu);

window.craftItem = function(recipe) {
  sfx.playPickup();
  if (recipe === 'foundation') {
    if (state.resources.wood >= 4 && state.resources.plastic >= 2) {
      state.resources.wood -= 4;
      state.resources.plastic -= 2;
      showNotification("Plataforma fabricada. Seleccionada en ranura 3");
      setActiveSlot(3);
      toggleCraftingMenu();
    } else {
      showNotification("Recursos insuficientes (4 Madera, 2 Plástico)");
    }
  } else if (recipe === 'campfire') {
    if (state.resources.wood >= 4 && state.resources.stone >= 4) {
      state.resources.wood -= 4;
      state.resources.stone -= 4;
      showNotification("Hoguera lista. Seleccionada en ranura 4");
      setActiveSlot(4);
      toggleCraftingMenu();
    } else {
      showNotification("Recursos insuficientes (4 Madera, 4 Piedra)");
    }
  } else if (recipe === 'wall') {
    if (state.resources.wood >= 3 && state.resources.leaves >= 1) {
      state.resources.wood -= 3;
      state.resources.leaves -= 1;
      showNotification("Pared lista. Seleccionada en ranura 5");
      setActiveSlot(5);
      toggleCraftingMenu();
    } else {
      showNotification("Recursos insuficientes (3 Madera, 1 Hojas)");
    }
  } else if (recipe === 'spear') {
    if (state.resources.wood >= 5) {
      state.resources.wood -= 5;
      showNotification("Lanza de madera fabricada con éxito");
      toggleCraftingMenu();
    } else {
      showNotification("Recursos insuficientes (5 Madera)");
    }
  }
  updateUI();
};

function handleInteract() {
  raycaster.setFromCamera(screenCenter, camera);
  const hits = raycaster.intersectObjects(scene.children, true);
  for (let hit of hits) {
    if (hit.distance < 4.2) {
      let cur = hit.object;
      while (cur && cur !== scene) {
        if (cur.userData && cur.userData.resourceType) {
          collectDebris(cur);
          return;
        }
        cur = cur.parent;
      }
    }
  }
}

// ==========================================
// 20. BUCLE DE RENDER Y FÍSICA FLUIDA
// ==========================================
const clock = new THREE.Clock();
const underwaterOverlay = document.getElementById('underwater-overlay');
const crosshair = document.getElementById('crosshair');
const promptEl = document.getElementById('interaction-prompt');
const promptLabel = document.getElementById('prompt-label');

let stepSoundCooldown = 0;

function animate() {
  requestAnimationFrame(animate);

  const delta = Math.min(clock.getDelta(), 0.08);
  const time = clock.getElapsedTime();

  // 1. Cinemática Inicial
  if (state.inCinematic) {
    state.cinematicProgress += delta * 0.12; // Dura ~8.5 segundos
    if (state.cinematicProgress >= 1.0) {
      finishCinematic();
    } else {
      const pos = cineCurve.getPoint(state.cinematicProgress);
      camera.position.copy(pos);
      
      // Orientar hacia el centro de la isla durante el vuelo
      const lookTarget = new THREE.Vector3(15, 2, 15);
      camera.lookAt(lookTarget);

      // Desvanecer el título a mitad de cinemática
      if (state.cinematicProgress > 0.5) {
        cineTitleBox.style.opacity = `${(1.0 - state.cinematicProgress) * 2}`;
      }
    }
    renderer.render(scene, camera);
    return;
  }

  // 2. Animación de olas
  const pos = waterGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const u = waterBasePositions.getX(i);
    const v = waterBasePositions.getZ(i);
    const wave = Math.sin(u * 0.08 + time * 2.2) * 0.35 +
                 Math.cos(v * 0.06 + time * 1.8) * 0.25;
    pos.setY(i, wave);
  }
  pos.needsUpdate = true;
  waterGeo.computeVertexNormals();

  // 3. Basura Flotante
  debrisList.forEach(mesh => {
    mesh.position.x += mesh.userData.speedX;
    mesh.position.z += mesh.userData.speedZ;
    mesh.rotation.y += mesh.userData.rotSpeed;
    mesh.position.y = CONFIG.WATER_LEVEL + Math.sin(time * 2 + mesh.position.x) * 0.18;
  });

  // 4. Balsa y Gaviotas
  raftGroup.position.y = CONFIG.WATER_LEVEL + 0.15 + Math.sin(time * 1.8) * 0.12;
  raftGroup.rotation.z = Math.sin(time * 1.5) * 0.03;
  raftGroup.rotation.x = Math.cos(time * 1.4) * 0.02;

  seagulls.forEach(bird => {
    bird.userData.angle += bird.userData.speed;
    bird.position.set(
      Math.cos(bird.userData.angle) * bird.userData.radius,
      bird.userData.height + Math.sin(time * 2 + bird.userData.radius) * 1.5,
      Math.sin(bird.userData.angle) * bird.userData.radius
    );
    bird.rotation.y = -bird.userData.angle - Math.PI / 2;
    const flap = Math.sin(time * 12) * 0.45;
    bird.userData.wingLeft.rotation.z = flap;
    bird.userData.wingRight.rotation.z = -flap;
  });

  // 5. Parpadeo de la antorcha en mano
  if (torchFlameLight && state.activeSlot === 4) {
    torchFlameLight.intensity = 2.0 + Math.sin(time * 18) * 0.35 + Math.cos(time * 11) * 0.2;
  }

  // 6. Movimiento del Jugador y Física Fluida
  if (isPointerLocked) {
    const terrainHeight = getTerrainHeight(camera.position.x, camera.position.z);
    const inWater = camera.position.y < CONFIG.WATER_LEVEL + 1.2;

    const headUnderwater = camera.position.y < CONFIG.WATER_LEVEL;
    if (headUnderwater !== state.isUnderwater) {
      state.isUnderwater = headUnderwater;
      underwaterOverlay.classList.toggle('active', state.isUnderwater);
    }

    const moveDir = new THREE.Vector3();
    if (keys.w) moveDir.z -= 1;
    if (keys.s) moveDir.z += 1;
    if (keys.a) moveDir.x -= 1;
    if (keys.d) moveDir.x += 1;
    moveDir.normalize();

    const forward = new THREE.Vector3(0, 0, -1).applyAxisAngle(new THREE.Vector3(0, 1, 0), euler.y);
    const right = new THREE.Vector3(1, 0, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), euler.y);

    const targetSpeed = inWater
      ? CONFIG.SWIM_SPEED
      : (keys.shift ? CONFIG.RUN_SPEED : CONFIG.WALK_SPEED);

    const wishVel = new THREE.Vector3();
    wishVel.addScaledVector(forward, -moveDir.z * targetSpeed);
    wishVel.addScaledVector(right, moveDir.x * targetSpeed);

    // Amortiguación y aceleración suave (sin resbalones)
    playerVelocity.x += (wishVel.x - playerVelocity.x) * (inWater ? 7 : 14) * delta;
    playerVelocity.z += (wishVel.z - playerVelocity.z) * (inWater ? 7 : 14) * delta;

    if (inWater) {
      if (keys.space) {
        playerVelocity.y = 4.2;
      } else if (keys.s && camera.rotation.x > 0.3) {
        playerVelocity.y = -3.2;
      } else {
        const depth = CONFIG.WATER_LEVEL + 1.1 - camera.position.y;
        playerVelocity.y = Math.min(2.5, depth * 2.8);
      }
    } else {
      if (keys.space && isGrounded) {
        playerVelocity.y = CONFIG.JUMP_FORCE;
        isGrounded = false;
        sfx.playStep(false);
      }
      playerVelocity.y -= CONFIG.GRAVITY * delta;
    }

    camera.position.x += playerVelocity.x * delta;
    camera.position.z += playerVelocity.z * delta;
    camera.position.y += playerVelocity.y * delta;

    // Colisión de suelo suave
    const eyeHeight = 1.8;
    const minHeight = terrainHeight + eyeHeight;
    if (camera.position.y < minHeight) {
      camera.position.y = minHeight;
      playerVelocity.y = 0;
      isGrounded = true;
    } else {
      isGrounded = false;
    }

    // Sonidos de pasos periódicos
    if ((moveDir.x !== 0 || moveDir.z !== 0) && (isGrounded || inWater)) {
      stepSoundCooldown += delta;
      const stepRate = keys.shift ? 0.3 : 0.46;
      if (stepSoundCooldown > stepRate) {
        stepSoundCooldown = 0;
        sfx.playStep(inWater);
      }
    }

    // 7. Animaciones del Brazo y Mano en 1ª Persona
    const isMoving = moveDir.length() > 0;
    const bobFreq = keys.shift ? 14 : 9;
    const bobAmpX = isMoving ? 0.02 : 0.004;
    const bobAmpY = isMoving ? 0.015 : 0.003;
    const walkBobX = Math.sin(time * bobFreq) * bobAmpX;
    const walkBobY = Math.cos(time * (bobFreq * 2)) * bobAmpY;

    if (armAnim.isSwinging) {
      armAnim.swingProgress += delta * 6.5;
      const swingAngle = Math.sin(armAnim.swingProgress * Math.PI);
      playerRig.position.set(0.04 - swingAngle * 0.1, -0.05 + swingAngle * 0.1, -0.15 - swingAngle * 0.2);
      playerRig.rotation.x = -swingAngle * 0.7;
      playerRig.rotation.y = swingAngle * 0.4;
      if (armAnim.swingProgress >= 1) {
        armAnim.isSwinging = false;
        playerRig.rotation.set(0, 0, 0);
      }
    } else if (armAnim.isEating) {
      armAnim.eatProgress += delta * 3.5;
      const eatAngle = Math.sin(armAnim.eatProgress * Math.PI);
      playerRig.position.set(-eatAngle * 0.12, 0.15 * eatAngle, -eatAngle * 0.2);
      playerRig.rotation.x = eatAngle * 0.5;
      if (armAnim.eatProgress >= 1) {
        armAnim.isEating = false;
        playerRig.rotation.set(0, 0, 0);
      }
    } else {
      // Balanceo natural de respiración y paso
      playerRig.position.set(walkBobX, walkBobY, 0);
      playerRig.rotation.set(0, 0, walkBobX * 0.8);
    }

    // 8. Detección Contextual para la Mira
    raycaster.setFromCamera(screenCenter, camera);
    const hitCandidates = raycaster.intersectObjects(scene.children, true);
    let foundInteractable = false;
    for (let h of hitCandidates) {
      if (h.distance < 4.5) {
        let cur = h.object;
        while (cur && cur !== scene) {
          if (cur.userData && (cur.userData.resourceType || cur.userData.type)) {
            foundInteractable = true;
            crosshair.classList.add('interact');
            promptEl.style.display = 'flex';
            if (cur.userData.resourceType) {
              promptLabel.innerText = `Recoger ${cur.userData.name}`;
            } else if (cur.userData.type === 'palmTree') {
              promptLabel.innerText = `Talar palmera`;
            } else if (cur.userData.type === 'rock') {
              promptLabel.innerText = `Picar roca`;
            }
            break;
          }
          cur = cur.parent;
        }
        if (foundInteractable) break;
      }
    }

    if (!foundInteractable) {
      crosshair.classList.remove('interact');
      promptEl.style.display = 'none';
    }

    updateGhostPlacement();
  }

  // 9. Actualizar sombras del sol siguiendo al jugador
  sunLight.position.x = camera.position.x + 90;
  sunLight.position.z = camera.position.z + 80;
  sunLight.target.position.copy(camera.position);
  sunLight.target.updateMatrixWorld();

  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// Inicializar ítem de la mano al empezar (ranura 1)
updateVisibleHandItem(1);

animate();
