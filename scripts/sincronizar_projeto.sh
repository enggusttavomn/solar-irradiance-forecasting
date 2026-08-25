#!/usr/bin/env bash
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Atualizacao local - $(date '+%Y-%m-%d %H:%M:%S')"
else
  echo "Nenhuma alteracao nova para registrar."
fi

git pull --rebase origin main
git push origin main
echo "Projeto sincronizado com o GitHub."

