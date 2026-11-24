import { useMemo } from "react";
import * as THREE from "three";

/** Windows texture: a dark facade with a random scatter of warm lit windows. */
function makeWindowTexture(seed: number): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#0b0e16";
  g.fillRect(0, 0, c.width, c.height);
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let y = 4; y < c.height - 4; y += 8) {
    for (let x = 4; x < c.width - 4; x += 8) {
      if (rnd() < 0.32) {
        const warm = rnd();
        g.fillStyle = warm < 0.7 ? "#f2c879" : warm < 0.9 ? "#d9e4f5" : "#8fb3e8";
        g.globalAlpha = 0.55 + rnd() * 0.45;
        g.fillRect(x, y, 4, 5);
      }
    }
  }
  g.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * A ring of distant city blocks around the scene, so every camera shot has a skyline behind
 * the building. Purely decorative; kept 70-150 m out so it never blocks a shot.
 */
export function CityBackdrop() {
  const blocks = useMemo(() => {
    let s = 7;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    const out: { pos: [number, number, number]; size: [number, number, number]; tex: number }[] = [];
    for (let i = 0; i < 90; i++) {
      const angle = rnd() * Math.PI * 2;
      const r = 70 + rnd() * 80;
      const w = 8 + rnd() * 14;
      const d = 8 + rnd() * 14;
      const h = 12 + Math.pow(rnd(), 1.6) * 60;
      out.push({ pos: [8 + Math.cos(angle) * r, h / 2, 6 + Math.sin(angle) * r], size: [w, h, d], tex: i % 4 });
    }
    return out;
  }, []);
  const materials = useMemo(
    () =>
      [11, 23, 37, 51].map((seed) => {
        const map = makeWindowTexture(seed);
        return new THREE.MeshStandardMaterial({ color: "#151a26", emissive: "#ffffff", emissiveMap: map, emissiveIntensity: 0.55, roughness: 0.9 });
      }),
    [],
  );
  return (
    <group name="city-backdrop">
      {blocks.map((b, i) => {
        const m = materials[b.tex].clone();
        m.emissiveMap = m.emissiveMap!.clone();
        m.emissiveMap.repeat.set(Math.max(1, Math.round(b.size[0] / 8)), Math.max(1, Math.round(b.size[1] / 16)));
        m.emissiveMap.needsUpdate = true;
        return (
          <mesh key={i} position={b.pos} material={m}>
            <boxGeometry args={b.size} />
          </mesh>
        );
      })}
    </group>
  );
}
