"""FastWan 2.2 (DMD-distilled Wan 2.2 TI2V-5B, Apache-2.0) on mlx-video: 3 denoise steps, no CFG.

mlx-video has no DMD sampler, so this swaps its Euler scheduler for the DMD one (predict the clean video,
re-noise it to the next sigma) and runs its normal Wan pipeline. Text or text+image (first frame).

    python -m studio.wan_fast --model-dir DIR --prompt "..." --width 832 --height 480 --num-frames 121 \
        --seed 42 --output-path out.mp4 [--image first_frame.png]
"""
import argparse, json, os

import mlx.core as mx
import numpy as np

DMD_SIGMAS = [1.0, 0.757, 0.522, 0.0]


class DMDScheduler:
    """x0 = x_t - sigma * v, then x_next = (1 - s') x0 + s' * fresh noise (renoise); the last step returns x0."""

    sigmas = DMD_SIGMAS

    def __init__(self, num_train_timesteps=1000):
        self.n = num_train_timesteps

    def set_timesteps(self, num_steps=3, shift=1.0):
        s = np.array(self.sigmas, dtype=np.float32)
        self.timesteps = mx.array((s[:-1] * self.n).astype(np.int64).astype(np.float32))
        self._i = 0

    def step(self, model_output, timestep, sample):
        s, s_next = self.sigmas[self._i], self.sigmas[self._i + 1]
        x0 = sample - s * model_output
        self._i += 1
        return x0 if s_next == 0 else (1 - s_next) * x0 + s_next * mx.random.normal(sample.shape)

    def reset(self):
        self._i = 0


def generate(model_dir, prompt, width, height, num_frames, seed, output_path, image=None, tiling="temporal"):
    from mlx_video.models.wan_2 import generate as G, scheduler as S
    cfg = json.load(open(os.path.join(model_dir, "config.json")))
    DMDScheduler.sigmas = (cfg.get("fastwan_dmd") or {}).get("sigmas", DMD_SIGMAS)
    S.FlowMatchEulerScheduler = DMDScheduler          # generate_video imports it from this module at call time
    G.generate_video(model_dir=model_dir, prompt=prompt, image=image, width=width, height=height, num_frames=num_frames,
                     steps=len(DMDScheduler.sigmas) - 1, guide_scale=1.0, shift=1.0, seed=seed, output_path=output_path,
                     scheduler="euler", negative_prompt="", tiling=tiling)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--model-dir", required=True); a.add_argument("--prompt", required=True); a.add_argument("--image")
    a.add_argument("--width", type=int, default=832); a.add_argument("--height", type=int, default=480)
    a.add_argument("--num-frames", type=int, default=121); a.add_argument("--seed", type=int, default=42)
    a.add_argument("--output-path", required=True); a.add_argument("--tiling", default="temporal")   # temporal tiles decode fastest on a 64 GB Mac (130 s vs 168 s auto, 454 s none, for 5 s)
    o = a.parse_args()
    generate(o.model_dir, o.prompt, o.width, o.height, o.num_frames, o.seed, o.output_path, o.image, o.tiling)
