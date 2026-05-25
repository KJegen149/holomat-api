/* Phase 13 dashboard renderers + mode switcher.
   Three concepts, swappable at runtime so the mockup viewer can compare:
     1. Particle sphere  (canvas 2D, audio-reactive idle/listening/speaking)
     2. Concentric rings (SVG, lighter weight)
     3. Conversation hybrid (smaller core + transcript + suggestion chips)

   Each renderer paints inside the element passed to mount(). Topbar / nav
   chrome is owned by the host page; this module only owns the dashboard area.
*/

const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',     icon: 'dashboard' },
  { id: 'scanner',    label: 'Scanner',       icon: 'scan' },
  { id: 'gallery',    label: 'Gallery',       icon: 'image' },
  { id: 'models',     label: 'Models',        icon: 'box' },
  { id: 'print',      label: 'Print',         icon: 'printer' },
  { id: 'ha',         label: 'Home Assistant', icon: 'home' },
  { id: 'settings',   label: 'Settings',      icon: 'gear' },
];

const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  scan:      '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="3" y1="12" x2="21" y2="12"/>',
  image:     '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="9" cy="9" r="1.6"/><path d="m21 15-5-5L5 21"/>',
  box:       '<path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7 12 12l8.7-5"/><path d="M12 22V12"/>',
  printer:   '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
  home:      '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  gear:      '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .32 1.76l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.6 1.6 0 0 0-1.76-.32 1.6 1.6 0 0 0-1 1.46V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.46 1.6 1.6 0 0 0-1.76.32l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.6 1.6 0 0 0 .32-1.76 1.6 1.6 0 0 0-1.46-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.46-1 1.6 1.6 0 0 0-.32-1.76l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.6 1.6 0 0 0 1.76.32H9a1.6 1.6 0 0 0 1-1.46V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.46 1.6 1.6 0 0 0 1.76-.32l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.6 1.6 0 0 0-.32 1.76V9a1.6 1.6 0 0 0 1.46 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.46 1z"/>',
  mic:       '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
  send:      '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
};

function icon(id, size = 22) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[id] || ''}</svg>`;
}

/* ───────────────────────── Particle sphere ───────────────────────── */
class ParticleSphereDashboard {
  constructor(root) {
    this.root = root;
    this.root.innerHTML = `
      <canvas class="ps-canvas" style="position:absolute;inset:0;width:100%;height:100%;"></canvas>
      <div class="ps-hud" style="position:absolute;inset:0;pointer-events:none;"></div>
      <div class="ps-greet" style="position:absolute;left:50%;bottom:13%;transform:translateX(-50%);text-align:center;pointer-events:none;">
        <div class="cap dim" style="font-size:10px;letter-spacing:0.3em;margin-bottom:8px;">JARVIS · READY</div>
        <div style="font-size:18px;color:var(--text);font-weight:300;letter-spacing:0.04em;max-width:520px;">
          Good afternoon, Kyle. Standing by.
        </div>
      </div>
    `;
    this.canvas = root.querySelector('.ps-canvas');
    this.hud = root.querySelector('.ps-hud');
    this.greet = root.querySelector('.ps-greet');
    this.ctx = this.canvas.getContext('2d');
    this.particles = [];
    this.audioLevel = 0;
    this.mode = 'idle'; // idle | listening | speaking
    this.t0 = performance.now();
    this.frame = 0;
    this.placeHudCards();
    this.initParticles();
    this.resize();
    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
    this.loop();
  }

  placeHudCards() {
    const cards = [
      { top: '8%',  left: '4%',  label: 'Weather',  value: '68°F', sub: 'Clear · light wind' },
      { top: '8%',  right: '4%', label: 'Print Q',  value: '1 active', sub: 'iPhone case · 42%' },
      { bottom: '8%', left: '4%', label: 'Lights',  value: '6 on', sub: 'Office · Living' },
      { bottom: '8%', right: '4%', label: 'Models', value: '23', sub: '4 ready to slice' },
    ];
    this.hud.innerHTML = cards.map(c => {
      const pos = Object.entries(c).filter(([k]) => ['top','bottom','left','right'].includes(k))
        .map(([k,v]) => `${k}:${v}`).join(';');
      return `<div class="hud-card" style="${pos}">
        <div class="label">${c.label}</div>
        <div class="value">${c.value}</div>
        <div class="sub">${c.sub}</div>
      </div>`;
    }).join('');
  }

  initParticles() {
    const N = 750;
    this.particles = [];
    for (let i = 0; i < N; i++) {
      const phi = Math.acos(1 - 2 * (i + 0.5) / N);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);
      this.particles.push({
        ox: Math.sin(phi) * Math.cos(theta),
        oy: Math.sin(phi) * Math.sin(theta),
        oz: Math.cos(phi),
        halo: Math.random() * 1.0 + 0.6,
        seed: Math.random() * Math.PI * 2,
      });
    }
    // Outer drifting halo points
    this.outer = [];
    for (let i = 0; i < 220; i++) {
      this.outer.push({
        r: 1.05 + Math.random() * 0.6,
        a: Math.random() * Math.PI * 2,
        b: (Math.random() - 0.5) * Math.PI,
        s: 0.6 + Math.random() * 0.5,
        speed: 0.0002 + Math.random() * 0.0004,
      });
    }
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = this.root.getBoundingClientRect();
    this.canvas.width = r.width * dpr;
    this.canvas.height = r.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = r.width; this.h = r.height;
  }

  setMode(m) {
    this.mode = m;
    if (m === 'speaking') {
      this.targetLevel = 0.6;
    } else if (m === 'listening') {
      this.targetLevel = 0.25;
    } else {
      this.targetLevel = 0;
    }
  }

  render(t) {
    const { ctx, w, h, particles } = this;
    if (!w) return;
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2;
    const baseR = Math.min(w, h) * 0.26;

    // Audio amp simulation if speaking
    if (this.mode === 'speaking') {
      const env = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * 0.012));
      const flicker = 0.7 + 0.3 * Math.sin(t * 0.04 + Math.sin(t * 0.018) * 4);
      this.audioLevel = env * flicker;
    } else if (this.mode === 'listening') {
      this.audioLevel = 0.15 + 0.1 * Math.sin(t * 0.008);
    } else {
      this.audioLevel *= 0.95;
    }

    const breath = 1 + Math.sin(t * 0.0008) * 0.035 + this.audioLevel * 0.18;
    const pulse = baseR * breath;

    const ry = t * 0.00025;
    const rx = Math.sin(t * 0.00018) * 0.35;
    const cosY = Math.cos(ry), sinY = Math.sin(ry);
    const cosX = Math.cos(rx), sinX = Math.sin(rx);

    // Center halo
    const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, pulse * 1.5);
    halo.addColorStop(0,   `rgba(0, 220, 255, ${0.28 + this.audioLevel * 0.25})`);
    halo.addColorStop(0.35,`rgba(80, 130, 220, ${0.12 + this.audioLevel * 0.12})`);
    halo.addColorStop(1,   'rgba(0, 0, 0, 0)');
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, w, h);

    // Outer drifting points
    for (const p of this.outer) {
      p.a += p.speed;
      const x = Math.cos(p.a) * Math.cos(p.b) * pulse * p.r;
      const y = Math.sin(p.b) * pulse * p.r;
      const z = Math.sin(p.a) * Math.cos(p.b);
      const depth = (z + 1) / 2;
      ctx.fillStyle = `rgba(0, ${180 + depth * 50 | 0}, ${230 + depth * 25 | 0}, ${0.15 + depth * 0.25})`;
      ctx.beginPath();
      ctx.arc(cx + x, cy + y, p.s, 0, Math.PI * 2);
      ctx.fill();
    }

    // Sphere points
    const out = [];
    for (const p of particles) {
      let x = p.ox * cosY + p.oz * sinY;
      let z = -p.ox * sinY + p.oz * cosY;
      let y = p.oy;
      const y2 = y * cosX - z * sinX;
      const z2 = y * sinX + z * cosX;
      const wobble = 1 + Math.sin(t * 0.001 + p.seed) * 0.018 + this.audioLevel * 0.08 * Math.sin(p.seed + t * 0.004);
      const r = pulse * wobble;
      out.push({ sx: cx + x * r, sy: cy + y2 * r, sz: z2, halo: p.halo });
    }
    out.sort((a, b) => a.sz - b.sz);
    for (const pt of out) {
      const depth = (pt.sz + 1) / 2;
      const size = 0.5 + depth * 1.7 * pt.halo;
      const violetMix = 1 - depth;
      const r = (0   + violetMix * 80) | 0;
      const g = (180 + depth * 75) | 0;
      const b = (220 + depth * 35) | 0;
      const a = 0.18 + depth * 0.7;
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a})`;
      ctx.beginPath();
      ctx.arc(pt.sx, pt.sy, size, 0, Math.PI * 2);
      ctx.fill();
    }

    // Speaking ripples
    if (this.mode === 'speaking') {
      const rippleCount = 3;
      for (let i = 0; i < rippleCount; i++) {
        const phase = (t * 0.0008 + i / rippleCount) % 1;
        const rr = pulse * (1 + phase * 1.6);
        const aa = (1 - phase) * 0.35;
        ctx.strokeStyle = `rgba(0, 220, 255, ${aa})`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(cx, cy, rr, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  loop = () => {
    const t = performance.now() - this.t0;
    this.render(t);
    this.frame = requestAnimationFrame(this.loop);
  }

  destroy() {
    cancelAnimationFrame(this.frame);
    window.removeEventListener('resize', this._onResize);
    this.root.innerHTML = '';
  }
}

/* ───────────────────────── Concentric rings ───────────────────────── */
class RingsDashboard {
  constructor(root) {
    this.root = root;
    this.root.innerHTML = `
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">
        <svg viewBox="-200 -200 400 400" style="width:min(72vh,72vw);height:min(72vh,72vw);overflow:visible;">
          <defs>
            <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stop-color="rgba(0, 220, 255, 0.85)"/>
              <stop offset="40%"  stop-color="rgba(0, 180, 220, 0.35)"/>
              <stop offset="100%" stop-color="rgba(0, 220, 255, 0)"/>
            </radialGradient>
            <linearGradient id="ringGrad" x1="0" x2="1">
              <stop offset="0%"   stop-color="rgba(0, 220, 255, 0.95)"/>
              <stop offset="50%"  stop-color="rgba(140, 110, 255, 0.55)"/>
              <stop offset="100%" stop-color="rgba(0, 220, 255, 0)"/>
            </linearGradient>
          </defs>

          <!-- outer slow ring with tick segments -->
          <g class="ring-outer">
            <circle r="180" fill="none" stroke="rgba(0,220,255,0.08)" stroke-width="0.6"/>
            <circle r="180" fill="none" stroke="url(#ringGrad)" stroke-width="1.2"
                    stroke-dasharray="14 6" />
          </g>

          <!-- mid ring -->
          <g class="ring-mid">
            <circle r="140" fill="none" stroke="rgba(140,110,255,0.18)" stroke-width="0.8"/>
            <circle r="140" fill="none" stroke="rgba(0,220,255,0.55)" stroke-width="1"
                    stroke-dasharray="60 200" />
            <circle r="140" fill="none" stroke="rgba(0,220,255,0.4)" stroke-width="0.8"
                    stroke-dasharray="2 12" />
          </g>

          <!-- inner ring -->
          <g class="ring-inner">
            <circle r="100" fill="none" stroke="rgba(0,220,255,0.45)" stroke-width="1.4"
                    stroke-dasharray="30 8 6 8" />
          </g>

          <!-- tick marks ring (very inner) -->
          <g class="ring-ticks">
            ${Array.from({length:60}, (_, i) => {
              const a = (i / 60) * Math.PI * 2;
              const r1 = 78, r2 = 84;
              const x1 = Math.cos(a) * r1, y1 = Math.sin(a) * r1;
              const x2 = Math.cos(a) * r2, y2 = Math.sin(a) * r2;
              const long = i % 5 === 0;
              return `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${(Math.cos(a)*(long?86:84)).toFixed(2)}" y2="${(Math.sin(a)*(long?86:84)).toFixed(2)}"
                stroke="rgba(0,220,255,${long?0.7:0.3})" stroke-width="${long?1.4:0.6}"/>`;
            }).join('')}
          </g>

          <!-- core -->
          <circle r="70" fill="url(#coreGlow)">
            <animate attributeName="r" values="65;78;65" dur="3s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.7;1;0.7" dur="3s" repeatCount="indefinite"/>
          </circle>
          <circle r="40" fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="1">
            <animate attributeName="r" values="38;48;38" dur="2.2s" repeatCount="indefinite"/>
          </circle>

          <!-- waveform (visible only in speaking mode) -->
          <g class="wave" opacity="0">
            <polyline class="wave-line" points="" fill="none"
                      stroke="rgba(0,220,255,0.9)" stroke-width="1.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
          </g>
        </svg>
      </div>
      <div style="position:absolute;left:50%;bottom:8%;transform:translateX(-50%);text-align:center;pointer-events:none;">
        <div class="cap dim" style="font-size:10px;letter-spacing:0.3em;margin-bottom:6px;">JARVIS · IDLE</div>
        <div style="font-size:18px;font-weight:300;letter-spacing:0.04em;">All systems nominal.</div>
      </div>
    `;
    this.svg = root.querySelector('svg');
    this.outer = root.querySelector('.ring-outer');
    this.mid = root.querySelector('.ring-mid');
    this.inner = root.querySelector('.ring-inner');
    this.ticks = root.querySelector('.ring-ticks');
    this.wave = root.querySelector('.wave');
    this.waveLine = root.querySelector('.wave-line');
    this.t0 = performance.now();
    this.mode = 'idle';
    this.loop();
  }
  setMode(m) {
    this.mode = m;
    this.wave.style.opacity = (m === 'speaking') ? '1' : '0';
  }
  loop = () => {
    const t = (performance.now() - this.t0) / 1000;
    this.outer.setAttribute('transform', `rotate(${(t * 6).toFixed(2)})`);
    this.mid.setAttribute('transform', `rotate(${(-t * 14).toFixed(2)})`);
    this.inner.setAttribute('transform', `rotate(${(t * 24).toFixed(2)})`);
    if (this.mode === 'speaking') {
      const pts = [];
      for (let i = 0; i <= 60; i++) {
        const x = -80 + i * (160 / 60);
        const y = Math.sin(i * 0.6 + t * 9) * (8 + 6 * Math.sin(t * 4 + i)) +
                  Math.sin(i * 1.5 - t * 4) * 5;
        pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
      this.waveLine.setAttribute('points', pts.join(' '));
    }
    this.frame = requestAnimationFrame(this.loop);
  }
  destroy() {
    cancelAnimationFrame(this.frame);
    this.root.innerHTML = '';
  }
}

/* ───────────────────────── Conversation-first ───────────────────────── */
class ConversationDashboard {
  constructor(root) {
    this.root = root;
    this.root.innerHTML = `
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:5% 8% 8%;">
        <div class="conv-core" style="width:min(38vh,38vw);height:min(38vh,38vw);position:relative;flex-shrink:0;"></div>

        <div class="conv-last" style="margin-top:24px;max-width:780px;text-align:center;">
          <div class="cap dim" style="font-size:10px;letter-spacing:0.3em;margin-bottom:8px;">Jarvis</div>
          <div style="font-size:24px;font-weight:300;line-height:1.45;letter-spacing:0.01em;color:var(--text);">
            The iPhone case print is at 42 percent, sir. About 1 hour 12 minutes remaining.
            Living room lights have been dimmed for movie mode.
          </div>
        </div>

        <div class="conv-transcript" style="flex:1;width:100%;max-width:780px;margin-top:18px;
             overflow:hidden;mask-image:linear-gradient(180deg,black 30%,transparent);
             -webkit-mask-image:linear-gradient(180deg,black 30%,transparent);">
          <div class="transcript-row dim" style="font-size:13px;padding:6px 0;">
            <span style="color:var(--violet);">You · </span>start movie mode and check on the print
          </div>
          <div class="transcript-row dim" style="font-size:13px;padding:6px 0;opacity:0.7;">
            <span style="color:var(--cyan);">Jarvis · </span>understood — dimming living room
          </div>
          <div class="transcript-row dim" style="font-size:12px;padding:6px 0;opacity:0.5;">
            <span style="color:var(--violet);">You · </span>what's the weather looking like tomorrow
          </div>
          <div class="transcript-row dim" style="font-size:12px;padding:6px 0;opacity:0.3;">
            <span style="color:var(--cyan);">Jarvis · </span>72 and partly cloudy, a touch of rain in the evening
          </div>
        </div>

        <div class="conv-chips" style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:12px;">
          <button class="chip">Pause print</button>
          <button class="chip">Bedtime scene</button>
          <button class="chip">What's on the calendar?</button>
          <button class="chip">Check security</button>
        </div>
      </div>
    `;
    this.core = root.querySelector('.conv-core');
    this.sphere = new ParticleSphereDashboard(this.core);
    // Hide the sphere's HUD/greeting since we have our own surrounding chrome
    this.sphere.hud.style.display = 'none';
    this.sphere.greet.style.display = 'none';
  }
  setMode(m) { this.sphere.setMode(m); }
  destroy() { this.sphere.destroy(); this.root.innerHTML = ''; }
}

/* ───────────────────────── Mockup viewer harness ───────────────────────── */

const DASHBOARDS = {
  particles: { label: 'Particle Sphere',  ctor: ParticleSphereDashboard },
  rings:     { label: 'Rings + Orb',      ctor: RingsDashboard },
  convo:     { label: 'Conversation',     ctor: ConversationDashboard },
};

function mountTopbar(host) {
  const bar = document.createElement('div');
  bar.className = 'topbar';
  bar.innerHTML = `
    <div>
      <div class="brand-wordmark">JARVIS</div>
      <div class="brand-sub">Joint Automation · Robotics · Vision Intelligence</div>
    </div>
    <div class="spacer"></div>
    <div class="status-pill"><span class="dot"></span>Optimal</div>
    <div class="status-pill"><span class="dot"></span>Calibrated</div>
    <div class="clock" id="topbar-clock">--:--:--</div>
  `;
  host.appendChild(bar);
  const clock = bar.querySelector('#topbar-clock');
  const tick = () => { clock.textContent = new Date().toTimeString().slice(0, 8); };
  tick(); setInterval(tick, 1000);
}

function mountModeToggle(host, onChange) {
  const wrap = document.createElement('div');
  wrap.className = 'mode-toggle';
  const modes = ['idle', 'listening', 'speaking'];
  for (const m of modes) {
    const b = document.createElement('button');
    b.textContent = m;
    b.dataset.mode = m;
    if (m === 'idle') b.classList.add('active');
    b.onclick = () => {
      wrap.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      onChange(m);
    };
    wrap.appendChild(b);
  }
  host.appendChild(wrap);
}

function mountDashboardSwitcher(host, onChange) {
  const wrap = document.createElement('div');
  wrap.className = 'mode-toggle';
  wrap.style.right = '20px';
  wrap.style.top = '70px';
  wrap.style.left = '20px';
  wrap.style.width = 'fit-content';
  for (const [k, v] of Object.entries(DASHBOARDS)) {
    const b = document.createElement('button');
    b.textContent = v.label;
    b.dataset.key = k;
    if (k === 'particles') b.classList.add('active');
    b.onclick = () => {
      wrap.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      onChange(k);
    };
    wrap.appendChild(b);
  }
  host.appendChild(wrap);
}

function mountVariantLabel(host, text) {
  const el = document.createElement('div');
  el.className = 'variant-label';
  el.textContent = text;
  host.appendChild(el);
}

/* Public init for nav-X.html pages */
function initMockupPage(opts) {
  mountTopbar(document.body);

  const stage = document.createElement('div');
  stage.className = 'viewport';
  stage.id = 'stage';
  document.body.appendChild(stage);

  let current = null;
  let currentKey = 'particles';
  let currentMode = 'idle';

  const dashRoot = document.createElement('div');
  dashRoot.style.cssText = 'position:absolute;inset:0;';
  stage.appendChild(dashRoot);

  function setDashboard(key) {
    if (current) current.destroy();
    currentKey = key;
    current = new DASHBOARDS[key].ctor(dashRoot);
    current.setMode(currentMode);
  }
  function setMode(m) {
    currentMode = m;
    if (current) current.setMode(m);
  }

  setDashboard('particles');

  // Mount nav-specific chrome
  if (opts.mountNav) opts.mountNav(stage);

  mountDashboardSwitcher(document.body, setDashboard);
  mountModeToggle(document.body, setMode);
  if (opts.label) mountVariantLabel(document.body, opts.label);
}

window.HolomatMockup = {
  initMockupPage,
  NAV_ITEMS,
  icon,
};
