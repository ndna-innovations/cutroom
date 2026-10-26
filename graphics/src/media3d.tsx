// Lottie animations (thousands of free animated icons) and a 3D device mock-up (your screen recording on a laptop/phone).
import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, OffthreadVideo, Img } from "remotion";
import { Lottie, LottieAnimationData } from "@remotion/lottie";
import { Base, ease, sp, useT } from "./lib";

/** A Lottie animation (.json from LottieFiles etc.): {src: "file:///…json", x, y, size (0-1 of height), loop, speed, at} */
export const LottieClip: React.FC<Base & { src: string; x?: number; y?: number; size?: number; loop?: boolean; speed?: number; at?: number }> = (p) => {
  const { t, fps, W, H } = useT();
  const [data, setData] = useState<LottieAnimationData | null>(null);
  const [handle] = useState(() => delayRender("lottie " + p.src));
  useEffect(() => { fetch(p.src).then((r) => r.json()).then((j) => { setData(j); continueRender(handle); }).catch(() => continueRender(handle)); }, [p.src, handle]);
  const k = sp(t, p.at ?? 0, fps, { damping: 14 }); const s = (p.size ?? 0.4) * H;
  if (!data || t < (p.at ?? 0)) return null;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: (p.x ?? 0.5) * W - s / 2, top: (p.y ?? 0.5) * H - s / 2, width: s, height: s, transform: `scale(${k})` }}>
        <Lottie animationData={data} loop={p.loop ?? true} playbackRate={p.speed ?? 1} style={{ width: s, height: s }} />
      </div>
    </AbsoluteFill>
  );
};

/** Photo -> 2.5D parallax: the picture split into depth layers (from the engine: a depth map), the camera drifts and
 * pushes in so near parts move more than far ones. {image, depth (grey PNG, white = near), push, drift, at} */
export const Parallax: React.FC<Base & { image: string; depth?: string; layers?: string[]; push?: number; drift?: number; dir?: number }> = (p) => {
  const { t, W, H, D } = useT();
  const u = ease(t, 0, Math.max(0.1, D)); const dir = p.dir ?? 1;
  const ls = p.layers && p.layers.length ? p.layers : [p.image];
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {ls.map((src, i) => {
        const z = ls.length > 1 ? i / (ls.length - 1) : 0;           // 0 = far, 1 = near
        const sc = 1.08 + (p.push ?? 0.08) * u * (0.4 + z);
        const dx = dir * (p.drift ?? 0.03) * W * u * (z - 0.3);
        return <Img key={i} src={src} style={{ position: "absolute", left: 0, top: 0, width: W, height: H, objectFit: "cover",
          transform: `translateX(${dx}px) scale(${sc})`, transformOrigin: "50% 55%" }} />;
      })}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ real 3D: a laptop or phone playing his screen recording
import { ThreeCanvas, useOffthreadVideoTexture } from "@remotion/three";
import * as THREE from "three";
import { useVideoConfig } from "remotion";
import { useThree } from "@react-three/fiber";

const LookAt: React.FC<{ y: number }> = ({ y }) => { const { camera } = useThree(); camera.lookAt(0, y, 0); return null; };
import { interpolate, Easing } from "remotion";

const Screen: React.FC<{ src?: string; image?: string; w: number; h: number }> = ({ src, image, w, h }) => {
  const tex = src ? useOffthreadVideoTexture({ src }) : null;
  const [imgTex, setImgTex] = useState<THREE.Texture | null>(null);
  const [handle] = useState(() => (image ? delayRender("tex " + image) : null));
  useEffect(() => { if (!image) return; new THREE.TextureLoader().load(image, (t) => { t.colorSpace = THREE.SRGBColorSpace; setImgTex(t); handle && continueRender(handle); }, undefined, () => handle && continueRender(handle)); }, [image, handle]);
  const map = tex || imgTex; if (tex) tex.colorSpace = THREE.SRGBColorSpace;
  // a new material when the picture arrives (three only adds a texture to a material when it is (re)built)
  return <mesh position={[0, 0, 0.011]}><planeGeometry args={[w, h]} />
    {map ? <meshBasicMaterial key={"m" + (map as any).uuid} map={map} toneMapped={false} /> : <meshBasicMaterial key="n" color="#111" />}</mesh>;
};

/** A real 3D laptop or phone showing a screen recording (or image), lit, with a camera move.
 * {kind: laptop|phone, video: "file:///clip.mp4", image, turn: [fromDeg, toDeg], tilt, push, open: hinge opening at start, color} */
export const Device3D: React.FC<Base & { kind?: string; video?: string; image?: string; turn?: [number, number]; tilt?: number; push?: number; open?: boolean; color?: string; transparent?: boolean }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, D, fps } = useT();
  const u = interpolate(t, [0, D], [0, 1], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const [a0, a1] = p.turn ?? [-28, 12]; const yaw = THREE.MathUtils.degToRad(a0 + (a1 - a0) * u);
  const tilt = THREE.MathUtils.degToRad(p.tilt ?? -8); const z = 8.2 - (p.push ?? 1.4) * u;
  const hinge = p.open === false ? 1 : sp(t, 0.1, fps, { damping: 16, stiffness: 90 });
  const body = p.color === "silver" ? "#c9ccd2" : "#2b2d33";
  const phone = p.kind === "phone";
  return (
    <AbsoluteFill style={{ background: p.transparent ? undefined : "radial-gradient(ellipse at 50% 40%, #1d2340 0%, #07080f 70%)" }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 30, position: [0, 1.2, z] }} gl={{ antialias: true }}>
        <LookAt y={p.kind === "phone" ? 0 : 0.55} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[3, 4, 5]} intensity={1.6} />
        <directionalLight position={[-4, 2, -3]} intensity={0.8} color="#7aa0ff" />
        <group rotation={[tilt, yaw, 0]} position={[0, phone ? 0 : -0.35, 0]}>
          {phone ? (
            <group>
              <mesh><boxGeometry args={[1.25, 2.6, 0.1]} /><meshStandardMaterial color={body} metalness={0.35} roughness={0.4} /></mesh>
              <group position={[0, 0, 0.045]}><Screen src={p.video} image={p.image} w={1.13} h={2.45} /></group>
            </group>
          ) : (
            <group>
              <mesh position={[0, -0.04, 0.85]}><boxGeometry args={[3.3, 0.08, 2.2]} /><meshStandardMaterial color={body} metalness={0.35} roughness={0.45} /></mesh>
              <group position={[0, 0, -0.25]} rotation={[-THREE.MathUtils.degToRad(100) * (1 - hinge) + THREE.MathUtils.degToRad(-12) * hinge, 0, 0]}>
                <group position={[0, 1.05, 0]}>
                  <mesh><boxGeometry args={[3.3, 2.1, 0.05]} /><meshStandardMaterial color={body} metalness={0.35} roughness={0.45} /></mesh>
                  <group position={[0, 0, 0.016]}><Screen src={p.video} image={p.image} w={3.1} h={1.94} /></group>
                </group>
              </group>
            </group>
          )}
        </group>
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
