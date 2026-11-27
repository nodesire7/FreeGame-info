#!/usr/bin/env bash
set -euo pipefail
cd /state
exec 9>/state/publisher.lock
flock -n 9 || { echo 'A publisher already holds the state lock.' >&2; exit 1; }

checkout() {
  local dir="$1" key="$2" repo="$3" branch="$4"
  local ssh_cmd="ssh -o BatchMode=yes -o ConnectTimeout=20 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/keys/known_hosts -i /keys/$key"
  if [[ ! -d "$dir/.git" ]]; then
    local attempt
    attempt=$(mktemp -d /state/clone.XXXXXXXX)
    if ! git -c core.sshCommand="$ssh_cmd" clone --single-branch --branch "$branch" --depth 1 \
      "git@github.com:nodesire7/$repo.git" "$attempt"; then
      rm -rf -- "$attempt"
      return 1
    fi
    git -C "$attempt" config core.sshCommand "$ssh_cmd"
    mv "$attempt" "$dir"
  fi
}

checkout source project FreeGame-info main
checkout history-repo project FreeGame-info history
checkout account account nodesire7.github.io main

# gh-pages is an independent output branch, created by the first successful push.
if [[ ! -d project/.git ]]; then
  git init -b gh-pages project
  git -C project remote add origin git@github.com:nodesire7/FreeGame-info.git
  git -C project config core.sshCommand "$(git -C source config core.sshCommand)"
fi

while true; do
  if git -C source pull --ff-only --quiet origin main; then
    head=$(git -C source rev-parse HEAD)
    read -r last_head last_epoch < last-success || { last_head=''; last_epoch=0; }
    if [[ -d pending || "$head" != "$last_head" ]] || (( $(date +%s) >= last_epoch + ${FETCH_INTERVAL:-10800} )); then
      if ! bash source/deploy/publish-snapshot.sh; then
        echo "[retry] Publication failed; retrying in ${POLL_INTERVAL:-60}s" >&2
      fi
    fi
  else
    echo '[retry] Could not refresh the source branch.' >&2
  fi
  sleep "${POLL_INTERVAL:-60}"
done
