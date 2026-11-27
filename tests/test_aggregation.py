import asyncio
import tempfile
import unittest
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree

import main


class AggregationTests(unittest.TestCase):
    def collect(self, previous, **results):
        fixtures = {key: [] for key in main.PRIMARY_PLATFORMS}
        fixtures["itad"] = {"deals": [], "bundles": []}
        fixtures.update(results)
        fetchers = {}
        for key, result in fixtures.items():
            if isinstance(result, Exception):
                fetchers["fetch_" + key] = AsyncMock(side_effect=result)
            else:
                fetchers["fetch_" + key] = AsyncMock(return_value=result)
        with tempfile.TemporaryDirectory() as output, patch.multiple(main, **fetchers):
            return asyncio.run(main.fetch_all(output, previous=previous))

    def test_successful_empty_clears_cache_and_outages_retain_original_timestamp(self):
        previous = {
            "fetchedAt": "2026-11-01T12:30:00+08:00",
            "psn": [{"title": "Previous month"}],
            "steam": [{"title": "Steam offer"}],
        }
        first = self.collect(previous, steam=RuntimeError())
        second = self.collect(first, steam=RuntimeError(), psn=RuntimeError())
        self.assertEqual(first["psn"], [])
        self.assertEqual(first["sourceStatus"]["psn"]["state"], "ok")
        self.assertEqual(second["sourceStatus"]["psn"]["asOf"], first["fetchedAt"])
        self.assertEqual(second["steam"], previous["steam"])
        self.assertEqual(second["sourceStatus"]["steam"]["state"], "cached")
        self.assertEqual(second["sourceStatus"]["steam"]["asOf"], previous["fetchedAt"])

    def test_itad_component_outage_preserves_redistributed_deals_until_verified_empty(self):
        deal = {"title": "Game", "url": "https://example.com/g", "store": "Steam", "storeFamily": "steam", "cut": 100}
        first = self.collect({}, itad={"deals": [deal], "bundles": []})
        outage = {"deals": [], "bundles": [], "errors": {"deals": "offline"}}
        second = self.collect(first, itad=outage)
        third = self.collect(second, itad=outage)
        self.assertEqual(third["steam"], first["steam"])
        self.assertEqual(third["sourceStatus"]["steam"]["state"], "cached")
        statuses = third["sourceStatus"]["itad"]["components"]
        self.assertEqual(statuses["deals"]["asOf"], first["fetchedAt"])
        self.assertEqual(statuses["bundles"]["state"], "ok")
        self.assertEqual(self.collect(third)["steam"], [])

    def test_matching_store_offer_keeps_official_record_and_separate_editions(self):
        titles = ["Bread & Fred", "Bread & Fred Deluxe"]
        deals = [{"title": title, "url": f"https://example.com/{i}", "store": "Epic",
                  "storeFamily": "epic", "cut": 100} for i, title in enumerate(titles)]
        result = self.collect({}, epic={"now": [{"title": "Bread and Fred"}], "upcoming": []},
                              itad={"deals": deals, "bundles": []})
        self.assertEqual([r["title"] for r in result["epic"]["now"]], ["Bread and Fred", "Bread & Fred Deluxe"])

    def test_external_steam_giveaways_follow_their_own_source_and_expire(self):
        key = {"title": "Game Key", "id": 42, "platforms": "PC, Steam", "link": "https://example.com/key"}
        other = {"title": "Other", "platforms": "PC, DRM-Free"}
        first = self.collect({}, gamerpower=[key, other])
        self.assertEqual([row["id"] for row in first["steam"]], [42])
        self.assertEqual(first["gamerpower"], [other])
        second = self.collect(first, gamerpower=RuntimeError(), steam=RuntimeError())
        third = self.collect(second, gamerpower=RuntimeError())
        self.assertEqual(third["steam"], first["steam"])
        self.assertEqual(third["sourceStatus"]["gamerpower"]["asOf"], first["fetchedAt"])
        self.assertEqual(self.collect(third, steam=RuntimeError())["steam"], [])
        with tempfile.TemporaryDirectory() as output:
            main.generate_feed(third, output)
            entry = ElementTree.parse(Path(output) / "feed.xml").find(".//item[category='Steam']")
            self.assertEqual(entry.findtext("title"), "Game Key")
            self.assertIn("上次核对", entry.findtext("description"))

    def test_epic_time_and_itad_bundle_changes(self):
        epic = [{"title": "Game", "status": "ACTIVE", "date": "2026/11/28 12:45:13"}]
        snapshot = self.collect({}, epic=epic)
        end = datetime.fromisoformat("2026-11-28T12:45:13+08:00")
        self.assertEqual(snapshot["epic"]["now"][0]["freeEndAt"], int(end.timestamp() * 1000))
        bundle = {"title": "Bundle", "url": "https://example.com/b", "gameCount": 3}
        flat = {"itad": [bundle]}
        nested = {"itad": {"deals": [], "bundles": [dict(bundle)]}}
        self.assertEqual(main._snapshot_hash(flat), main._snapshot_hash(nested))
        nested["itad"]["bundles"][0]["gameCount"] = 4
        self.assertNotEqual(main._snapshot_hash(flat), main._snapshot_hash(nested))

    def test_rss_includes_all_sources_and_keeps_cache_publication_date(self):
        stamp = "2026-11-01T12:30:00+08:00"
        old_stamp = "2026-10-29T12:30:00+08:00"
        game = {"title": "Game & friends", "link": "https://example.com/?a=1&b=2", "description": "A\x03B"}
        snapshot = {
            **{key: [game] for key in main.PRIMARY_PLATFORMS if key != "epic"},
            "epic": {"now": [game], "upcoming": [dict(game, title="Next")]},
            "itad": {"deals": [dict(game, title="Deal")], "bundles": [dict(game, title="Bundle")]},
            "sourceStatus": {"steam": {"state": "cached", "asOf": old_stamp, "checkedAt": stamp}},
            "fetchedAt": stamp,
        }
        with tempfile.TemporaryDirectory() as output:
            main.generate_feed(snapshot, output)
            feed = ElementTree.parse(Path(output) / "feed.xml")
        self.assertEqual(len(feed.findall(".//item")), 9)
        steam = feed.find(".//item[category='Steam']")
        self.assertEqual(parsedate_to_datetime(steam.findtext("pubDate")), datetime.fromisoformat(old_stamp))
        self.assertEqual(parsedate_to_datetime(feed.findtext(".//lastBuildDate")), datetime.fromisoformat(stamp))
