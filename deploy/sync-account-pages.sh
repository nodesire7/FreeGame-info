#!/usr/bin/env bash
set -euo pipefail
build=$1
account=$2
for file in index.html history/index.html history/date.db 白嫖信息.json ads.txt feed.xml; do
  test -s "$build/$file" || { echo "Missing build output: $file" >&2; exit 1; }
done
test -d "$account/.git"
case "$(git -C "$account" remote get-url origin)" in
  https://github.com/nodesire7/nodesire7.github.io|https://github.com/nodesire7/nodesire7.github.io.git|git@github.com:nodesire7/nodesire7.github.io|git@github.com:nodesire7/nodesire7.github.io.git) ;;
  *) echo "Expected the nodesire7.github.io Pages repository" >&2; exit 1 ;;
esac
# The project domain and its third-party verification file belong to gameinfo only.
rsync -a --delete --exclude='/.git/' --exclude='/.github/' --exclude='/CNAME' \
  --exclude='/6da64ae9f15c6a6e8149.txt' "$build/" "$account/"
python3 - "$account/index.html" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
content = p.read_text(encoding="utf-8")
p.write_text("".join(line for line in content.splitlines(keepends=True)
                     if '<meta name="6da64ae9f15c6a6e81499ff21b745e42d48f40db"' not in line),
             encoding="utf-8")
PY
