#!/usr/bin/env bash
set -euo pipefail
cd /state
if [[ ! -d pending ]]; then
  git -C history-repo pull --ff-only origin history
  stage=$(mktemp -d /state/build.XXXXXXXX)
  trap 'if [[ -d "$stage" ]]; then rm -rf -- "$stage"; fi' EXIT
  head=$(git -C source rev-parse HEAD)
  release="docker-$(date -u +%Y%m%dT%H%M%SZ)-${head:0:8}"
  if [[ -s /run/secrets/itad_api_key ]]; then
    ITAD_API_KEY=$(cat /run/secrets/itad_api_key)
    export ITAD_API_KEY
  fi
  echo "[build] $release"
  (cd source && python main.py "$stage/site" --history-dir /state/history-repo/history)
  cp source/ads.txt "$stage/site/ads.txt"
  touch "$stage/site/.nojekyll"
  echo 'gameinfo.gbtgame.me' > "$stage/site/CNAME"
  python - "$stage/site" "$release" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
for path in [root / "index.html", root / "history/index.html"]:
    html = path.read_text()
    if html.count("</head>") != 1:
        raise ValueError(f"Invalid page: {path}")
    path.write_text(html.replace("</head>", f'<meta name="freegame-build" content="{sys.argv[2]}"></head>'))
PY
  echo "$head" > "$stage/source-sha"
  echo "$release" > "$stage/release"
  mv "$stage" pending
fi

release=$(cat pending/release)
push_changes() {
  local dir="$1" branch="$2"
  git -C "$dir" add -A
  if ! git -C "$dir" diff --cached --quiet; then
    git -C "$dir" -c user.name="FreeGame server publisher" -c user.email="publisher@gbtgame.me" commit -qm "$release"
  fi
  # Also push commits left locally if a previous network attempt failed.
  git -C "$dir" push origin "HEAD:refs/heads/$branch"
}

push_changes history-repo history
# Each branch is exclusively used for generated pages. A divergent push fails safely.
if git -C project ls-remote --exit-code origin refs/heads/gh-pages >/dev/null; then
  git -C project pull --ff-only --no-rebase origin gh-pages
elif [[ $? != 2 ]]; then
  exit 1
fi
rsync -a --delete --exclude='/.git/' --exclude='/.github/' pending/site/ project/
push_changes project gh-pages

git -C account pull --ff-only --no-rebase origin main
bash source/deploy/sync-account-pages.sh pending/site account
push_changes account main

printf '%s %s\n' "$(cat pending/source-sha)" "$(date +%s)" > last-success.tmp
mv last-success.tmp last-success
rm -rf -- pending
echo "[published] $release"
