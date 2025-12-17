#!/usr/bin/env python3
"""
历史数据存储（SQLite）

- 所有历史快照写入 history/date.db（默认路径由 main.py 的 --history-dir 控制）
- 仅当本次抓取结果与上一次不同才新增一条记录
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL UNIQUE,
  fetched_at TEXT,
  hash TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  image TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_created_at ON records(created_at);
"""


def open_db(history_dir: Path) -> sqlite3.Connection:
    history_dir.mkdir(parents=True, exist_ok=True)
    db_path = history_dir / "date.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def get_latest_meta(conn: sqlite3.Connection) -> Tuple[Optional[str], Optional[str]]:
    """返回 (latest_hash, latest_ts)"""
    row = conn.execute(
        "SELECT hash, ts FROM records ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def insert_record(
    conn: sqlite3.Connection,
    *,
    ts: str,
    fetched_at: Optional[str],
    hash_value: str,
    snapshot: Dict[str, Any],
    image_rel: Optional[str],
) -> None:
    snapshot_str = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    conn.execute(
        "INSERT INTO records (ts, fetched_at, hash, snapshot, image, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, fetched_at, hash_value, snapshot_str, image_rel, ts),
    )
    conn.commit()


def list_snapshots(conn: sqlite3.Connection, *, limit: int = 60) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT snapshot FROM records ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    snapshots: List[Dict[str, Any]] = []
    for (snap_str,) in rows:
        try:
            snapshots.append(json.loads(snap_str))
        except Exception:
            continue
    return snapshots


def list_records(conn: sqlite3.Connection, *, limit: int = 200) -> List[Dict[str, Any]]:
    """供页面/调试使用，返回不含 snapshot 大字段的元信息列表。"""
    rows = conn.execute(
        "SELECT ts, fetched_at, hash, image FROM records ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"ts": ts, "fetchedAt": fetched_at, "hash": h, "image": image}
        for (ts, fetched_at, h, image) in rows
    ]


