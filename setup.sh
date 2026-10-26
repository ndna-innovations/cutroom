#!/bin/bash
# Cutroom setup: tools, Python environment, graphics, macOS helper and models, then `cutroom doctor`.
# Safe to run again: anything already there is skipped.
#   ./setup.sh            everything (about 2.3 GB of models)
#   ./setup.sh --minimal  only what every edit needs (speech model + face model, about 1.6 GB)
set -euo pipefail
cd "$(dirname "$0")"
MIN=0; [ "${1:-}" = "--minimal" ] && MIN=1
M="$HOME/models"

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "Cutroom needs a Mac with Apple Silicon (M1 or newer)."; exit 1; }
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
xcode-select -p >/dev/null 2>&1 || { echo "Install Apple's command line tools first: xcode-select --install"; exit 1; }

echo "== tools"
need() { command -v "$1" >/dev/null && echo "have $1" || brew install "$2"; }   # only installs what is missing
need uv uv; need node node; need ffmpeg ffmpeg; need whisper-cli whisper-cpp
[ $MIN = 1 ] || [ -x "$(brew --prefix)/opt/ffmpeg-full/bin/ffmpeg" ] || brew install ffmpeg-full

echo "== Python environment"
[ -d .venv ] || uv venv --python 3.12 .venv
if [ $MIN = 1 ]; then uv pip install --python .venv/bin/python -e .; else uv pip install --python .venv/bin/python -e ".[masks]"; fi

echo "== graphics (Remotion)"
(cd graphics && npm install --no-audit --no-fund)

echo "== macOS helpers (Vision, screen takes)"
mkdir -p studio/bin
[ -x studio/bin/studio-vision ] || swiftc -O studio/native/vision.swift -o studio/bin/studio-vision
[ -x studio/bin/studio-autotake ] || swiftc -O studio/native/autotake.swift -o studio/bin/studio-autotake

get() {  # get URL FILE: download once
  [ -s "$2" ] && { echo "have $2"; return; }
  mkdir -p "$(dirname "$2")"; echo "downloading $2"
  curl -fL --progress-bar -o "$2.part" "$1" && mv "$2.part" "$2"
}
echo "== models"
get https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin "$M/whisper/ggml-large-v3-turbo.bin"
get https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task "$M/studio/face_landmarker.task"
if [ $MIN = 0 ]; then
  get https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt "$M/studio/sam2.1_hiera_small.pt"
  get https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-aarch64-apple-darwin "$M/studio/bin/deep-filter"
  chmod +x "$M/studio/bin/deep-filter"
  if [ ! -x "$M/studio/bin/rife-ncnn-vulkan" ]; then
    T=$(mktemp -d); get https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-macos.zip "$T/rife.zip"
    unzip -q "$T/rife.zip" -d "$T"; R="$T/rife-ncnn-vulkan-20221029-macos"
    mkdir -p "$M/studio/rife"; cp "$R/rife-ncnn-vulkan" "$M/studio/bin/"; cp -R "$R/rife-v4.6" "$M/studio/rife/"; rm -rf "$T"
  fi
fi

echo "== settings"
[ -f "$HOME/.config/cutroom/config.json" ] || .venv/bin/cutroom init
.venv/bin/cutroom doctor
echo
echo "Done. Optional next steps:"
echo "  .venv/bin/cutroom init --profile yourname --force    # your name, handle, word fixes (edit ~/.config/cutroom/profiles/yourname.json)"
echo "  mkdir -p ~/.claude/skills/cutroom && cp claude-skill/SKILL.md ~/.claude/skills/cutroom/"
echo "  claude mcp add cutroom -- \"$PWD/.venv/bin/python\" -m studio.mcp_server"
