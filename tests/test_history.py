import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from history_db import open_db
from main import ARCHIVES_PER_PAGE, archive_if_changed, write_history_pages
from render_html import snapshot_time


TEMPLATE = str(Path(__file__).resolve().parents[1] / "epic-freebies.html.template")


class HistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = open_db(self.root)
        self.addCleanup(self.db.close)

    def test_only_consecutive_changes_create_archives(self):
        offer = {"id": "42", "title": "Game", "link": "https://example.com/game?id=42",
                 "price": 0, "platforms": ["Windows", "Linux"], "instructions": "Claim in store"}
        another = {"id": "77", "title": "Second"}
        original = {"steam": [offer, another]}
        ts, created = archive_if_changed(self.db, original)
        self.assertTrue(created)
        # An older import can have a higher row id, and the newest row a legacy hash.
        with self.db:
            self.db.execute("UPDATE records SET hash = 'legacy'")
            self.db.execute("INSERT INTO records(ts,hash,snapshot,created_at) VALUES ('20000101','old','{}','20000101')")
        refresh = {"steam": [another, dict(offer, platforms=["Linux", "Windows"], cover="new",
                                          link=offer["link"] + "&utm_source=feed")],
                   "fetchedAt": "2026-11-28T01:00:00Z", "sourceStatus": {"steam": {"state": "cached"}}}
        self.assertEqual(archive_if_changed(self.db, refresh), (ts, False))
        for change in ({"price": 1}, {"expiry": "2027-01-01"}, {"instructions": "Requires a code"}):
            self.assertTrue(archive_if_changed(self.db, {"steam": [dict(offer, **change), another]})[1])
            self.assertTrue(archive_if_changed(self.db, original)[1])
        self.assertTrue(archive_if_changed(self.db, {"steam": [offer]})[1])

    def test_historical_platform_layout_is_equivalent(self):
        giveaway = {"id": "gp-1", "title": "GOG Key Giveaway", "platforms": "GOG",
                    "link": "https://example.com/key"}
        ts, _ = archive_if_changed(self.db, {"gamerpower": [giveaway]})
        current = {"gamerpower": [], "gog": [dict(giveaway, source="gamerpower", offerType="externalGiveaway")]}
        self.assertEqual(archive_if_changed(self.db, current), (ts, False))

    def test_every_archive_is_reachable_in_date_order(self):
        dates = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(63)]
        with self.db:
            for date in reversed(dates):
                ts = date.strftime("%Y%m%d%H%M%S")
                self.db.execute("INSERT INTO records(ts,hash,snapshot,image,created_at) VALUES (?,?,?,?,?)",
                                (ts, ts, json.dumps({"fetchedAt": date.isoformat()}), f"records/{ts}.webp", ts))
        output = self.root / "pages"
        write_history_pages(self.db, output, TEMPLATE)
        path = output / "index.html"
        seen = []
        for page in range(1, 14):
            soup = BeautifulSoup(path.read_text(), "html.parser")
            rows = soup.select("details.record")
            self.assertEqual(len(rows), min(ARCHIVES_PER_PAGE, 63 - len(seen)))
            seen.extend(row.select_one("summary strong").text for row in rows)
            nav = soup.select_one(".archive-pager")
            self.assertEqual(nav.select_one("[aria-current=page]").text, str(page))
            prev = nav.select_one("[rel=prev]")
            self.assertEqual(prev.get("href") if prev else None, None if page == 1 else "./" if page == 2 else f"page-{page - 1}.html")
            nxt = nav.select_one("[rel=next]")
            if page < 13:
                path = output / nxt["href"]
            else:
                self.assertIsNone(nxt)
        self.assertEqual(seen, [snapshot_time(date.isoformat()) for date in reversed(dates)])
        self.db.execute("DELETE FROM records")
        write_history_pages(self.db, output, TEMPLATE)
        self.assertEqual(list(output.iterdir()), [output / "index.html"])
        self.assertIn("暂无历史记录", (output / "index.html").read_text())
