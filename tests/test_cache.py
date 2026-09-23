import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "jinchanchan-strategy" / "scripts" / "cache.py"
spec = importlib.util.spec_from_file_location("jcc_cache", SCRIPT)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)
NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def evidence(kind="guide", age=1):
    when = (NOW - timedelta(hours=age)).isoformat()
    return {
        "schema_version": 1,
        "identity": {"game": "金铲铲之战", "region": "国服", "season": "测试赛季",
                     "patch": "test-1.0a", "mode": "标准排位", "edition": "2025原版"},
        "topic": "测试阵容-装备", "kind": kind, "status": "verified",
        "verified_at": when, "summary": "测试数据，不是真实攻略。",
        "sources": [{"title": "测试公告", "url": "https://example.com/patch",
                     "checked_at": when, "supports": "测试规则，仅用于程序验证。"}],
        "limitations": [],
    }


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jcc-cache-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "cache with spaces"
        self.card = evidence()

    def save(self, card=None):
        return cache.put(self.directory, card or self.card, NOW)

    def lookup(self, card=None, **kwargs):
        card = card or self.card
        return cache.get(self.directory, card["identity"], card["topic"], now=NOW, **kwargs)

    def test_missing_cache_does_not_write(self):
        self.assertEqual(cache.list_cards(self.directory)["entries"], [])
        self.assertEqual(self.lookup()["status"], "miss")
        self.assertFalse(self.directory.exists())

    def test_roundtrip_requires_current_version_check(self):
        self.save()
        result = self.lookup()
        self.assertEqual(result["status"], "hit")
        self.assertFalse(result["requires_research"])
        self.assertTrue(result["requires_version_check"])
        self.assertEqual(result["card"]["summary"], self.card["summary"])

    def test_every_identity_dimension_and_topic_are_isolated(self):
        self.save()
        for field in cache.IDENTITY_FIELDS:
            with self.subTest(field=field):
                different = copy.deepcopy(self.card)
                different["identity"][field] += "-different"
                self.assertEqual(self.lookup(different)["status"], "miss")
        different = copy.deepcopy(self.card)
        different["topic"] += "-positioning"
        self.assertEqual(self.lookup(different)["status"], "miss")

    def test_ttl_boundaries_for_all_kinds(self):
        for kind, ttl in cache.TTL_HOURS.items():
            for age, expected in ((ttl - 0.01, "hit"), (ttl, "stale"), (ttl + 1, "stale")):
                with self.subTest(kind=kind, age=age):
                    card = evidence(kind, age)
                    card["topic"] = f"{kind}-{age}"
                    self.save(card)
                    result = self.lookup(card)
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["requires_research"], expected != "hit")

    def test_historical_exact_patch_reuses_old_evidence(self):
        card = evidence("stats", 8760)
        self.save(card)
        result = self.lookup(card, scope="historical")
        self.assertEqual(result["status"], "hit")
        self.assertFalse(result["requires_version_check"])
        self.assertEqual(result["card"]["verified_at"], card["verified_at"])
        self.assertEqual(self.lookup(card)["status"], "stale")

    def test_partial_and_conflicting_cards_never_hit_even_historical(self):
        for status in ("partial", "conflict"):
            for scope in ("current", "historical"):
                with self.subTest(status=status, scope=scope):
                    card = evidence()
                    card.update(status=status, limitations=["缺少规则证据"])
                    self.save(card)
                    result = self.lookup(card, scope=scope)
                    self.assertEqual(result["status"], status)
                    self.assertTrue(result["requires_research"])

    def test_rewriting_verification_does_not_refresh_old_sources(self):
        card = evidence(age=48)
        card["verified_at"] = NOW.isoformat()
        self.save(card)
        self.assertEqual(self.lookup(card)["status"], "stale")
        self.assertEqual(self.lookup(card)["age_hours"], 48)

    def test_bad_records_rejected_without_writes(self):
        bad_values = [("schema_version", 2), ("schema_version", True), ("kind", []),
                      ("kind", "forever"), ("status", "partial"), ("summary", ""),
                      ("sources", []), ("identity", {}), ("limitations", "none"),
                      ("verified_at", "2026-01-01T00:00:00"),
                      ("verified_at", (NOW + timedelta(days=1)).isoformat())]
        for field, value in bad_values:
            with self.subTest(field=field, value=value):
                card = evidence()
                card[field] = value
                with self.assertRaises(ValueError):
                    self.save(card)
                self.assertFalse(self.directory.exists())

    def test_source_validation(self):
        for field, value in (("url", "file:///private/file"), ("url", "https://user:secret@example.com/"),
                             ("checked_at", NOW.isoformat()), ("supports", "")):
            with self.subTest(field=field):
                card = evidence()
                card["sources"][0][field] = value
                with self.assertRaises(ValueError):
                    self.save(card)

    def test_unknown_version_rejected(self):
        for value in ("未知", "latest", " CURRENT ", "待确认"):
            with self.subTest(value=value):
                card = evidence()
                card["identity"]["patch"] = value
                with self.assertRaises(ValueError):
                    self.save(card)

    def test_corrupt_and_oversized_cache_are_invalid_not_hits(self):
        path = self.save()
        for data in (b"not JSON", b"\xff", b"[1]", b"x" * (cache.MAX_BYTES + 1)):
            with self.subTest(length=len(data)):
                path.write_bytes(data)
                result = self.lookup()
                self.assertEqual(result["status"], "invalid")
                self.assertTrue(result["requires_research"])
                self.assertEqual(path.read_bytes(), data)

    def test_content_must_match_filename(self):
        path = self.save()
        changed = copy.deepcopy(self.card)
        changed["identity"]["patch"] = "different-hotfix"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.assertEqual(self.lookup()["status"], "invalid")
        self.assertEqual(cache.list_cards(self.directory, NOW)["entries"], [])
        self.assertEqual(len(cache.list_cards(self.directory, NOW)["invalid"]), 1)

    def test_older_replacement_refused_and_original_preserved(self):
        path = self.save()
        previous = path.read_bytes()
        with self.assertRaises(ValueError):
            self.save(evidence(age=2))
        self.assertEqual(path.read_bytes(), previous)
        self.save(evidence(age=0))
        self.assertEqual(self.lookup()["age_hours"], 0)

    def test_failed_atomic_replace_preserves_card_and_cleans_temp(self):
        path = self.save()
        original = path.read_bytes()
        with patch.object(cache.os, "replace", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                self.save(evidence(age=0))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.directory.iterdir()), [path])

    @unittest.skipIf(sys.platform == "win32", "Symlink creation may require privileges")
    def test_symlink_not_read_or_replaced(self):
        path = self.save()
        outside = Path(self.temporary.name) / "outside.json"
        path.rename(outside)
        path.symlink_to(outside)
        original = outside.read_bytes()
        self.assertEqual(self.lookup()["status"], "invalid")
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(outside.read_bytes(), original)
        self.assertTrue(path.is_symlink())

    def test_list_only_exposes_discovery_metadata(self):
        self.save()
        result = cache.list_cards(self.directory, NOW)
        self.assertEqual(len(result["entries"]), 1)
        self.assertNotIn("summary", result["entries"][0])
        self.assertNotIn("sources", result["entries"][0])

    def test_cli_put_get_list_outside_repo(self):
        source = Path(self.temporary.name) / "public evidence.json"
        source.write_text(json.dumps(self.card, ensure_ascii=False), encoding="utf-8")
        base = [sys.executable, str(SCRIPT), "--cache-dir", str(self.directory)]
        get_args = ["get", "--topic", self.card["topic"], "--scope", "historical"]
        for field, value in self.card["identity"].items():
            get_args += [f"--{field}", value]
        for args, expected in ((["put", "--file", str(source)], "saved"),
                               (get_args, "status"), (["list"], "entries")):
            run = subprocess.run(base + args, cwd=self.temporary.name, capture_output=True,
                                 text=True, encoding="utf-8",
                                 env={**os.environ, "PYTHONIOENCODING": "ascii"})
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertIn(expected, result)
            if expected == "status":
                self.assertEqual(result["status"], "hit")


if __name__ == "__main__":
    unittest.main()
