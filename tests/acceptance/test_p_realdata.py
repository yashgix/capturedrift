import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import capturedrift
from capturedrift import DATA_DIR, HARNESSES
from capturedrift.data import load, manifest, read_records
from capturedrift.drift import CUTOFF, top_unseen
from capturedrift.run import main
from capturedrift.sts import normalize


def strings(value):
    """Every string in a parsed JSON value, dict keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from strings(v)


def require_data():
    """The data is pinned in the repo, so a missing manifest is a failure, never a skip."""
    if not (DATA_DIR / "MANIFEST.json").is_file():
        raise AssertionError(f"pinned data missing: {DATA_DIR / 'MANIFEST.json'}")


REPO = DATA_DIR.parent
LICENSES = {"CC-BY-4.0", "MIT", "Apache-2.0", "CC0-1.0"}
SCALARS = ("data_files", "data_bytes", "content_min", "bytes_min")
METRICS = {
    **dict.fromkeys(SCALARS),
    "bytes_grid": 5,
    "train_bytes_f1": 5,
    **dict.fromkeys(
        (
            "sessions",
            "records",
            "versions",
            "train_versions",
            "test_versions",
            "kinds",
            "keys",
            "sts_byte_share",
            "sts_text_share",
            "frozen_new_kinds",
            "frozen_new_keys",
            "frozen_content_keys",
            "frozen_record_share",
            "frozen_byte_share",
            "frozen_text_share",
        ),
        2,
    ),
    **{
        f"version_{k}": 26
        for k in (
            "harness",
            "test",
            "sessions",
            "records",
            "shapes",
            "keys",
            "new_keys",
            "content_keys",
            "record_share",
            "byte_share",
            "text_share",
            "sts_text_share",
        )
    },
    **{
        f"alarm_{k}": 6
        for k in (
            "key_tp",
            "key_fp",
            "key_fn",
            "key_precision",
            "key_recall",
            "version_tp",
            "version_fp",
            "version_fn",
            "version_precision",
            "version_recall",
        )
    },
}


class PinnedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_data()
        cls.manifest = manifest()
        cls.sessions = load()

    def test_data_dir(self):
        self.assertEqual(capturedrift.DATA_DIR, Path(capturedrift.__file__).resolve().parent.parent / "data")
        self.assertEqual(HARNESSES, ("claude", "codex"))

    def test_checksums(self):
        files = self.manifest["files"]
        self.assertEqual(len(files), 40)
        self.assertEqual(sum(e["bytes"] for e in files.values()), 56_092_812)
        for name, entry in files.items():
            data = (DATA_DIR / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], name)
            self.assertEqual(len(data), entry["bytes"], name)

    def test_sources_licenses_and_cards(self):
        sources = self.manifest["sources"]
        self.assertEqual(len(sources), 12)
        for slug, src in sources.items():
            self.assertIn(src["license"], LICENSES, slug)
            self.assertTrue((DATA_DIR / src["card"]).is_file(), slug)
            self.assertTrue((DATA_DIR / "licenses" / f"{src['license']}.txt").is_file())
            self.assertRegex(src["revision"], r"^[0-9a-f]{40}$")
        self.assertEqual({e["source"] for e in self.manifest["files"].values()}, set(sources))

    def test_no_personal_data_left(self):
        home = re.compile(rb"(?:/Users/|/home/|[A-Za-z]:(?:\\\\|/)Users(?:\\\\|/))([A-Za-z][A-Za-z0-9_.-]*)")
        email = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|org|net|io|ai|dev)\b")
        token = re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})")
        names = set()
        for name in self.manifest["files"]:
            data = (DATA_DIR / name).read_bytes()
            names |= {m.group(1).lower() for m in home.finditer(data)}
            left = {m.group(0) for m in email.finditer(data) if not m.group(0).endswith(b"user@example.com")}
            self.assertEqual(left, set(), name)
            self.assertIsNone(token.search(data), name)
        self.assertLessEqual(names, {b"user", b"user1", b"node", b"runner", b"root"})
        counts = [e["redactions"] for e in self.manifest["files"].values()]
        totals = {rule: sum(c[rule] for c in counts) for rule in ("home", "encoded_home", "email", "token", "secret")}
        self.assertEqual(totals, {"home": 197, "encoded_home": 23, "email": 81, "token": 0, "secret": 172})

    def test_no_credential_shapes_left(self):
        # The same credential shapes Arcturus's runner refuses to send, in raw bytes and in decoded JSON strings.
        secret = re.compile(
            r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
            r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|PASSWORD)=[^\s\"']{8,}"
        )
        for path in sorted(p for p in DATA_DIR.rglob("*") if p.is_file()):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(secret.search(text), path.name)
            if path.suffix == ".jsonl":
                for line in filter(str.strip, text.splitlines()):
                    self.assertFalse(any(secret.search(s) for s in strings(json.loads(line))), path.name)

    def test_no_encoded_home_names_left(self):
        # Claude Code names project folders after the path, so /home/alice/app becomes -home-alice-app.
        encoded = re.compile(rb"-(?:Users|home)-([A-Za-z][A-Za-z0-9_]*)(?![A-Za-z0-9_])")
        names = set()
        for name in self.manifest["files"]:
            names |= {m.group(1).lower() for m in encoded.finditer((DATA_DIR / name).read_bytes())}
        self.assertLessEqual(names, {b"user", b"user1", b"node", b"runner", b"root"})

    def test_sessions(self):
        for h, n, records, first, last in (
            ("claude", 35, 15838, "2.1.114", "2.1.220"),
            ("codex", 5, 3229, "0.125.0", "0.147.0-alpha.1.2"),
        ):
            mine = [s for s in self.sessions if s.harness == h]
            self.assertEqual(len(mine), n)
            self.assertEqual(sum(len(s.records) for s in mine), records)
            self.assertEqual((mine[0].version, mine[-1].version), (first, last))
        for s in self.sessions:
            self.assertEqual(s.version, self.manifest["files"][s.name]["version"], s.name)
        self.assertEqual(self.sessions[0].start, "2026-05-17T14:58:06.237Z")

    def test_top_unseen(self):
        claude = top_unseen(self.sessions, "claude", 2)
        self.assertEqual(
            [(k, p) for k, p, _, _ in claude],
            [("system/local_command", "content:str"), ("attachment/invoked_skills", "attachment.skills[].content:str")],
        )
        self.assertEqual(claude[0][2:], (21246, 21183))
        codex = top_unseen(self.sessions, "codex", 1)
        self.assertEqual(
            codex, [("response_item/custom_tool_call_output", "payload.output[]<input_text>.text:str", 522306, 522081)]
        )

    def test_normalize_real_session(self):
        name = "sessions/codex/thomwolf__am-session-codex-check-d17941/"
        name += "rollout-2026-07-28T05-34-19-019fa737-7c2e-7393-89cf-9d9c60ea3899.jsonl"
        lines = normalize("codex", read_records(DATA_DIR / name))
        self.assertEqual(lines[0]["id"], "019fa737-7c2e-7393-89cf-9d9c60ea3899")
        self.assertEqual([x["message"]["role"] for x in lines[1:]], ["system"] * 3 + ["user"] * 2 + ["assistant"])
        self.assertTrue(all(isinstance(x["message"]["timestamp"], int) for x in lines[1:]))


class Experiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_data()
        cls.tmp = Path(tempfile.mkdtemp())
        cls.m = main(DATA_DIR, cls.tmp / "a" / "metrics.json")
        main(DATA_DIR, cls.tmp / "b" / "metrics.json")

    def test_writes_identical_sorted_files(self):
        a, b = (self.tmp / d / "metrics.json" for d in "ab")
        self.assertEqual(a.read_bytes(), b.read_bytes())
        text = a.read_text()
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(text, json.dumps(json.loads(text), sort_keys=True, indent=1) + "\n")
        self.assertEqual(json.loads(text), self.m)

    def test_metric_names_and_lengths(self):
        self.assertEqual(set(self.m), set(METRICS))
        for k, n in METRICS.items():
            if n is None:
                self.assertIsInstance(self.m[k], int, k)
            else:
                self.assertEqual(len(self.m[k]), n, k)

    def test_counts(self):
        m = self.m
        self.assertEqual((m["data_files"], m["data_bytes"], m["content_min"]), (40, 56_092_812, 200))
        self.assertEqual(m["sessions"], [35, 5])
        self.assertEqual(m["records"], [15838, 3229])
        self.assertEqual((m["versions"], m["train_versions"], m["test_versions"]), ([22, 4], [7, 1], [15, 3]))
        self.assertEqual((m["kinds"], m["keys"]), ([36, 22], [658, 274]))

    def test_threshold_tuned_before_the_cutoff(self):
        self.assertEqual(CUTOFF, {"claude": "2.1.145", "codex": "0.125.0"})
        self.assertEqual(self.m["bytes_grid"], [1, 32, 200, 1024, 8192])
        self.assertEqual(self.m["bytes_min"], 200)
        self.assertEqual(self.m["train_bytes_f1"], [0.086093, 0.143713, 0.358209, 0.296296, 0.235294])

    def test_sts_accounting(self):
        self.assertEqual(self.m["sts_byte_share"], [0.290205, 0.331063])
        self.assertEqual(self.m["sts_text_share"], [0.440651, 0.794765])

    def test_frozen_parser(self):
        m = self.m
        self.assertEqual(
            (m["frozen_new_kinds"], m["frozen_new_keys"], m["frozen_content_keys"]), ([8, 9], [150, 151], [6, 18])
        )
        self.assertEqual(m["frozen_record_share"], [0.151302, 0.337289])
        self.assertEqual(m["frozen_byte_share"], [0.075787, 0.652241])
        self.assertEqual(m["frozen_text_share"], [0.004246, 0.294209])

    def test_per_version(self):
        m = self.m
        self.assertEqual(m["version_harness"], [0] * 22 + [1] * 4)
        self.assertEqual(m["version_test"], [0] * 7 + [1] * 15 + [0] + [1] * 3)
        self.assertEqual(sum(m["version_sessions"]), 40)
        self.assertEqual(sum(m["version_records"]), 15838 + 3229)
        self.assertEqual(
            m["version_new_keys"],
            [0, 5, 151, 33, 53, 33, 14, 12, 16, 0, 17, 0, 42, 17, 1, 1, 0, 15, 4, 1, 2, 22, 0, 49, 38, 64],
        )
        self.assertEqual(
            m["version_content_keys"], [0, 2, 12, 2, 0, 1, 1, 2, 0, 0, 0, 0, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 7, 2, 9]
        )
        self.assertEqual(m["version_shapes"][:3] + m["version_shapes"][-4:], [28, 21, 32, 15, 23, 10, 28])
        self.assertEqual(m["version_record_share"][:7], [0.0] * 7)
        self.assertEqual(m["version_text_share"][-1], 0.792514)
        self.assertEqual(m["version_sts_text_share"][0], 0.544235)

    def test_frozen_shares_match_test_versions(self):
        m = self.m
        weights = [
            r
            for r, t, h in zip(m["version_records"], m["version_test"], m["version_harness"], strict=True)
            if t and h == 0
        ]
        shares = [
            s
            for s, t, h in zip(m["version_record_share"], m["version_test"], m["version_harness"], strict=True)
            if t and h == 0
        ]
        pooled = sum(w * s for w, s in zip(weights, shares, strict=True)) / sum(weights)
        self.assertAlmostEqual(pooled, m["frozen_record_share"][0], places=4)

    def test_alarms(self):
        m = self.m
        self.assertEqual(m["alarm_key_tp"], [3, 5, 5, 11, 18, 16])
        self.assertEqual(m["alarm_key_fp"], [91, 126, 14, 79, 133, 40])
        self.assertEqual(m["alarm_key_fn"], [3, 1, 1, 7, 0, 2])
        self.assertEqual(m["alarm_key_precision"], [0.031915, 0.038168, 0.263158, 0.122222, 0.119205, 0.285714])
        self.assertEqual(m["alarm_key_recall"], [0.5, 0.833333, 0.833333, 0.611111, 1.0, 0.888889])
        self.assertEqual(m["alarm_version_tp"], [3, 4, 4, 3, 3, 3])
        self.assertEqual(m["alarm_version_fp"], [3, 6, 2, 0, 0, 0])
        self.assertEqual(m["alarm_version_fn"], [1, 0, 0, 0, 0, 0])
        self.assertEqual(m["alarm_version_precision"][:3], [0.5, 0.4, 0.666667])

    def test_cli_entry_point(self):
        args = [sys.executable, "experiment.py", "--out", str(self.tmp / "c" / "metrics.json")]
        out = subprocess.run(args, check=False, cwd=REPO, capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.assertEqual((self.tmp / "c" / "metrics.json").read_bytes(), (self.tmp / "a" / "metrics.json").read_bytes())

    def test_demo_readme(self):
        results = self.tmp / "a"
        template = self.tmp / "README.md"
        template.write_text("# title\n\nbefore\n\n<!-- results:start -->\nold\n<!-- results:end -->\n\nafter\n")
        out = self.tmp / "README.out.md"
        args = [sys.executable, "demo.py", "--readme", str(template), "--out", str(out), "--results", str(results)]
        run = subprocess.run(args, check=False, cwd=REPO, capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        text = out.read_text()
        self.assertTrue(text.startswith("# title\n\nbefore\n\n<!-- results:start -->\n"))
        self.assertTrue(text.endswith("<!-- results:end -->\n\nafter\n"))
        self.assertNotIn("\nold\n", text)
        for needle in ("2.1.145", "0.147.0-alpha.1.2", "attachment/invoked_skills", "15.1%", "0.26", "|---|"):
            self.assertIn(needle, text)
        args = [sys.executable, "demo.py", "--results", str(results)]
        summary = subprocess.run(args, check=False, cwd=REPO, capture_output=True, text=True, timeout=300)
        self.assertEqual(summary.returncode, 0, summary.stderr[-2000:])
        self.assertEqual(len(summary.stdout.strip().splitlines()), 1)

    def test_fetch_verify(self):
        args = [sys.executable, "tools/fetch_data.py", "--verify"]
        run = subprocess.run(args, check=False, cwd=REPO, capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        self.assertIn("40 files match", run.stdout)
