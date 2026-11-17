// Textures are plain PNG files in public/logo (v0 graphite ouroboros, owner-approved 2026-11-17), not base64 in the bundle.
const base = import.meta.env.BASE_URL;
const [skinTexture, headTexture, profileTexture, phaseTexture] = ['skin', 'head', 'profile', 'phase'].map(name => `${base}logo/ouroboros-${name}.png`);

const vertexSource = `
attribute vec2 a_position;
varying vec2 v_uv;
void main() { v_uv = a_position * .5 + .5; gl_Position = vec4(a_position, 0., 1.); }
`;

const fragmentSource = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_skin;
uniform sampler2D u_head;
uniform sampler2D u_profile;
uniform sampler2D u_phase;
uniform float u_time;
uniform vec3 u_color;
const float PI = 3.14159265359;
const float TAU = 6.28318530718;
mat2 turn(float a) { return mat2(cos(a), sin(a), -sin(a), cos(a)); }
float feather(float lo, float hi, float value) {
  float t = clamp((value - lo) / (hi - lo), 0., 1.);
  return t * t * t * (t * (6. * t - 15.) + 10.);
}
void main() {
  vec2 p = (vec2(v_uv.x, 1. - v_uv.y) - .5) * 1024.;
  p = turn(.38) * p;
  float sector = mod(atan(p.y, p.x) + TAU, TAU);
  float headWeight = feather(radians(213.), radians(245.), sector)
    * (1. - feather(radians(294.), radians(319.), sector));
  vec2 hp = p + vec2(512.);
  vec2 hinge = vec2(405., 226.);
  float breath = sin(u_time * .8);
  float bite = pow(max(0., breath), 3.);
  vec2 nod = turn(-.003 * breath) * (hp - hinge) + hinge - hp;
  hp += nod * headWeight;
  float jaw = exp(-pow((hp.x - 542.) / 83., 2.) - pow((hp.y - 198.) / 14., 2.));
  hp.y -= 3. * bite * jaw * headWeight;
  p = hp - vec2(512.);
  float theta = atan(p.y, p.x);
  float radius = length(p);
  float u = fract(theta / TAU + 1.);
  vec2 profile = texture2D(u_profile, vec2(u, .5)).rg;
  float neck = (1. - headWeight) * (1. - headWeight);
  float wave = 2.4 * sin(theta * 3. + u_time * .85) + .75 * sin(theta * 5. - u_time * .43);
  float swallow = pow(.5 + .5 * cos(theta + 1.78 + u_time * .8), 14.);
  float center = 256. + profile.r * 192. + wave * neck;
  float halfWidth = profile.g * 128. + (3.8 * swallow + 1.1 * sin(theta * 3. + u_time)) * neck;
  float across = (radius - center) / max(halfWidth, 1.);
  float edge = 1. - smoothstep(.955, 1.015, abs(across));
  float travel = u_time * .0075 + .0018 * sin(u_time * .8);
  vec2 encodedPhase = texture2D(u_phase, vec2(u, .5)).rg;
  float skinPhase = (encodedPhase.r * 65280. + encodedPhase.g * 255.) / 65535.;
  float skin = texture2D(u_skin, vec2(fract(skinPhase + travel), clamp(across * .5 + .5, .005, .995))).r;
  float body = skin * edge;

  float anatomy = texture2D(u_head, clamp(hp / 1024., 0., 1.)).r;
  float alpha = clamp(mix(body, anatomy, headWeight), 0., 1.);
  gl_FragColor = vec4(u_color * alpha, alpha);
}
`;

type Particle = { x: number; y: number; radius: number; phase: number; size: number; opacity: number; drift: number };
export type OuroborosRenderer = { setRunning(value: boolean): void; setSpeed(value: number): void; destroy(): void };

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('The emblem texture could not be decoded.'));
    image.src = src;
  });
}

function random(n: number) {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

export async function createOuroborosRenderer(canvas: HTMLCanvasElement, dust: HTMLCanvasElement): Promise<OuroborosRenderer> {
  const images = await Promise.all([skinTexture, headTexture, profileTexture, phaseTexture].map(loadImage));
  const gl = canvas.getContext('webgl', { alpha: true, antialias: false, depth: false, premultipliedAlpha: true, preserveDrawingBuffer: true, powerPreference: 'low-power' });
  const ctx = dust.getContext('2d');
  if (!gl || !ctx) throw new Error('Animated rendering is unavailable; the static emblem is shown.');
  const shaders: WebGLShader[] = [];
  function compile(type: number, source: string) {
    const shader = gl!.createShader(type);
    if (!shader) throw new Error('Shader allocation failed.');
    shaders.push(shader);
    gl!.shaderSource(shader, source);
    gl!.compileShader(shader);
    if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) throw new Error(gl!.getShaderInfoLog(shader) || 'Shader compilation failed.');
    return shader;
  }
  const program = gl.createProgram();
  if (!program) throw new Error('Renderer allocation failed.');
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'Renderer linking failed.');
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'a_position');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  const textures = images.map((image, i) => {
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + i);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, i === 0 ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.uniform1i(gl.getUniformLocation(program, ['u_skin', 'u_head', 'u_profile', 'u_phase'][i]), i);
    return texture;
  });
  const timeUniform = gl.getUniformLocation(program, 'u_time');
  const colorUniform = gl.getUniformLocation(program, 'u_color');
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const particles: Particle[] = Array.from({ length: 118 }, (_, i) => {
    const angle = random(i + 7) * Math.PI * 2;
    const radius = i % 5 === 0 ? 170 + random(i + 22) * 110 : 408 + random(i + 11) * 64;
    return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, radius, phase: random(i + 37) * 20, size: .5 + random(i + 51) ** 3 * 2.1, opacity: .12 + random(i + 71) * .4, drift: .55 + random(i + 89) * .9 };
  });
  let frame = 0;
  let running = false;
  let visible = true;
  let disposed = false;
  let contextLost = false;
  let time = 0;
  let lastTime = 0;
  let speed = 1;
  let ink = 'rgb(15, 12, 8)';
  let size = 0;

  function draw(dt: number) {
    if (disposed || contextLost || size === 0) return;
    gl!.useProgram(program);
    gl!.clearColor(0, 0, 0, 0);
    gl!.clear(gl!.COLOR_BUFFER_BIT);
    gl!.uniform1f(timeUniform, time);
    gl!.drawArrays(gl!.TRIANGLES, 0, 6);
    ctx!.setTransform(1, 0, 0, 1, 0, 0);
    ctx!.clearRect(0, 0, dust.width, dust.height);
    const scale = dust.width / 1024;
    ctx!.setTransform(scale, 0, 0, scale, dust.width / 2, dust.height / 2);
    ctx!.fillStyle = ink;
    for (const p of particles) {
      if (dt > 0) {
        const r = Math.hypot(p.x, p.y);
        const tangent = (9 + 5 * Math.sin(time * .27 + p.phase)) * p.drift;
        const radial = (p.radius - r) * .11 + 2.8 * Math.sin(time * .61 + p.phase);
        const windX = 2 * Math.sin(p.y * .014 + time * .47);
        const windY = 2 * Math.cos(p.x * .016 - time * .39);
        p.x += (-p.y / r * tangent + p.x / r * radial + windX) * dt;
        p.y += (p.x / r * tangent + p.y / r * radial + windY) * dt;
      }
      const edge = Math.min(1, Math.max(0, (500 - Math.hypot(p.x, p.y)) / 25));
      ctx!.globalAlpha = p.opacity * edge * (.76 + .24 * Math.sin(time * .21 + p.phase));
      ctx!.beginPath();
      ctx!.ellipse(p.x, p.y, p.size, p.size * .68, p.phase + time * .08, 0, Math.PI * 2);
      ctx!.fill();
    }
    ctx!.globalAlpha = 1;
    ctx!.setTransform(1, 0, 0, 1, 0, 0);
    canvas.dataset.motionTime = time.toFixed(3);
  }

  function shouldRun() { return running && visible && !document.hidden && !media.matches && !disposed && !contextLost; }
  function tick(now: number) {
    frame = 0;
    if (!shouldRun()) return;
    const dt = Math.min((now - lastTime) / 1000, .04) * speed;
    lastTime = now;
    time += dt;
    draw(dt);
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    draw(0);
    if (shouldRun()) { lastTime = performance.now(); frame = requestAnimationFrame(tick); }
  }
  function resize() {
    const bounds = canvas.getBoundingClientRect();
    size = bounds.width;
    const pixels = Math.max(1, Math.round(size * Math.min(devicePixelRatio || 1, 2)));
    canvas.width = canvas.height = pixels;
    dust.width = dust.height = pixels;
    gl!.viewport(0, 0, pixels, pixels);
    ink = getComputedStyle(canvas).color;
    const values = ink.match(/[\d.]+/g)?.map(Number) || [15, 12, 8];
    gl!.uniform3f(colorUniform, values[0] / 255, values[1] / 255, values[2] / 255);
    draw(0);
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas);
  const intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); });
  intersectionObserver.observe(canvas);
  const onVisibility = () => sync();
  const onContextLost = (event: Event) => {
    event.preventDefault(); contextLost = true; sync();
    canvas.dataset.failed = 'true';
    canvas.dispatchEvent(new CustomEvent('ouroboros-renderer-failed'));
  };
  document.addEventListener('visibilitychange', onVisibility);
  media.addEventListener('change', sync);
  canvas.addEventListener('webglcontextlost', onContextLost);
  resize();
  return {
    setRunning(value) { running = value; sync(); },
    setSpeed(value) { speed = Math.min(1.8, Math.max(.35, value)); },
    destroy() {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      resizeObserver.disconnect(); intersectionObserver.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      media.removeEventListener('change', sync);
      canvas.removeEventListener('webglcontextlost', onContextLost);
      textures.forEach(texture => gl.deleteTexture(texture));
      shaders.forEach(shader => gl.deleteShader(shader));
      gl.deleteBuffer(buffer); gl.deleteProgram(program);
    },
  };
}
