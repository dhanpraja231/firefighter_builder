export const flameVertex = /* glsl */ `
  uniform float uTime;
  uniform float uIntensity;
  uniform float uPhase;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vec3 pos = position;
    float tip = uv.y;
    pos.x += sin(uTime * 6.0 + uPhase + position.y * 9.0) * 0.07 * tip * (0.65 + uIntensity);
    pos.z += cos(uTime * 5.0 + uPhase * 1.7 + position.y * 7.0) * 0.07 * tip * (0.65 + uIntensity);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

export const flameFragment = /* glsl */ `
  uniform float uTime;
  uniform float uIntensity;
  uniform float uPhase;
  varying vec2 vUv;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
  }

  void main() {
    float tip = vUv.y;
    float n = noise(vec2(vUv.x * 4.0 + uPhase, vUv.y * 6.0 - uTime * (1.8 + uIntensity)));
    float alpha = smoothstep(0.18, 0.62, n + (1.0 - tip) * 0.55);
    alpha *= 1.0 - smoothstep(0.62, 1.0, tip);
    alpha *= 0.35 + 0.65 * uIntensity;
    if (alpha < 0.04) discard;
    vec3 color = mix(vec3(1.0, 0.96, 0.78), vec3(1.0, 0.42, 0.05), smoothstep(0.02, 0.55, tip));
    color = mix(color, vec3(0.55, 0.08, 0.01), smoothstep(0.45, 0.95, tip));
    gl_FragColor = vec4(color, alpha);
  }
`;

export const pointVertex = /* glsl */ `
  attribute float aAlpha;
  uniform float uSize;
  varying float vAlpha;
  void main() {
    vAlpha = aAlpha;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uSize * (320.0 / max(1.0, -mv.z));
    gl_Position = projectionMatrix * mv;
  }
`;

export const pointFragment = /* glsl */ `
  uniform sampler2D uMap;
  uniform vec3 uColor;
  varying float vAlpha;
  void main() {
    float mask = texture2D(uMap, gl_PointCoord).a;
    float alpha = mask * vAlpha;
    if (alpha < 0.03) discard;
    gl_FragColor = vec4(uColor, alpha);
  }
`;
