#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
branch="$(git -C "$repo_root" branch --show-current)"

if [[ -z "$branch" ]]; then
  echo "O repositorio nao esta em uma branch. Saia do estado detached HEAD." >&2
  exit 1
fi

if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "A sincronizacao foi interrompida: ha alteracoes sem commit." >&2
  git -C "$repo_root" status --short
  echo "Revise o diff, execute os testes e crie o commit conscientemente." >&2
  exit 1
fi

git -C "$repo_root" fetch origin
git -C "$repo_root" pull --rebase origin "$branch"
git -C "$repo_root" push --set-upstream origin "$branch"
echo "Branch $branch sincronizada com o GitHub."
