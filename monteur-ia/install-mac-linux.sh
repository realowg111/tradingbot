#!/usr/bin/env bash
# Installe les outils du "Monteur IA" (étape 2 de la vidéo).
# Lance-le depuis le dossier monteur-ia :  bash install-mac-linux.sh
set -e
cd "$(dirname "$0")"

if [[ "$OSTYPE" == darwin* ]]; then
  command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  brew install ffmpeg whisper-cpp yt-dlp node git
  brew install --cask google-chrome || true
else
  sudo apt-get update
  sudo apt-get install -y ffmpeg git nodejs npm python3-pip cmake build-essential
  pip3 install --user -U yt-dlp
  if ! command -v whisper-cli >/dev/null; then
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$HOME/whisper.cpp"
    (cd "$HOME/whisper.cpp" && cmake -B build && cmake --build build -j --config Release)
    echo "whisper.cpp compilé dans $HOME/whisper.cpp/build/bin"
  fi
fi

# 1. Les skills de montage (dans ce dossier, pour Claude Code)
npx -y skills add Melvynx/video-agent-skills -a claude-code -y || {
  git clone --depth 1 https://github.com/Melvynx/video-agent-skills.git /tmp/video-agent-skills
  mkdir -p .claude/skills && cp -r /tmp/video-agent-skills/skills/* .claude/skills/
}

echo; echo "Vérification :"
for t in ffmpeg yt-dlp node; do printf "  %-8s " "$t"; command -v $t >/dev/null && echo OK || echo MANQUANT; done
printf "  %-8s " whisper; (command -v whisper-cli || ls "$HOME/whisper.cpp/build/bin/whisper-cli") >/dev/null 2>&1 && echo OK || echo MANQUANT
ls .claude/skills >/dev/null 2>&1 && echo "  skills   OK ($(ls .claude/skills | wc -l) installés)"
echo; echo "Prêt. Ouvre Claude Code en mode Local sur ce dossier, puis tape /studio-setup"
