"""Tests for the same-length cookie and signature redaction, on small strings and on the pinned data."""

import json
import tempfile
import unittest
from pathlib import Path

from capturedrift import DATA_DIR
from capturedrift.data import manifest
from tools.redact import main, redact


class RedactTest(unittest.TestCase):
    def test_cookie_values_become_x_runs_of_the_same_length(self):
        raw = b"Cookie: csv=2; loid=0000abc.2.1700000000000.Z2FiYw; edgebucket=AbCdEf123456; theme=2"
        self.assertEqual(redact(raw), b"Cookie: csv=2; loid=" + b"x" * 30 + b"; edgebucket=" + b"x" * 12 + b"; theme=2")

    def test_set_cookie_keeps_attributes_and_other_cookies(self):
        raw = b"set-cookie: _gh_sess=abc%2Fdef--123%3D%3D; path=/; secure\r\nset-cookie: logged_in=no; path=/"
        self.assertEqual(
            redact(raw), b"set-cookie: _gh_sess=" + b"x" * 20 + b"; path=/; secure\r\nset-cookie: logged_in=no; path=/"
        )

    def test_short_values_and_longer_names_stay(self):
        for raw in (b"edgebucket=test", b"xrdt=abcdefgh123", b"my_loid=abcdefgh123"):
            self.assertEqual(redact(raw), raw)

    def test_name_after_json_escape(self):
        self.assertEqual(redact(b'"a\\nrdt=abcdef123456"'), b'"a\\nrdt=' + b"x" * 12 + b'"')

    def test_g_state_browser_id(self):
        raw = b'g_state={\\"i_l\\":0,\\"i_b\\":\\"+L/abc123=\\"}'
        self.assertEqual(redact(raw), b'g_state={\\"i_l\\":0,\\"i_b\\":\\"' + b"x" * 10 + b'\\"}')

    def test_signed_url_signatures(self):
        raw = (
            b"https://h/f?Expires=1&Signature=a~b-c&Key-Pair-Id=K1 https://h/g?X-Amz-Date=1\\u0026X-Amz-Signature=ff00"
        )
        self.assertEqual(
            redact(raw),
            b"https://h/f?Expires=1&Signature=xxxxx&Key-Pair-Id=K1 https://h/g?X-Amz-Date=1\\u0026X-Amz-Signature=xxxx",
        )

    def test_json_stays_valid_and_a_second_pass_changes_nothing(self):
        raw = json.dumps({"headers": {"set-cookie": ["_cfuvid=Ab12.Cd34-1.0.1.1-Ef56; HttpOnly"]}}).encode()
        once = redact(raw)
        self.assertEqual(len(once), len(raw))
        self.assertEqual(json.loads(once)["headers"]["set-cookie"], ["_cfuvid=" + "x" * 22 + "; HttpOnly"])
        self.assertEqual(redact(once), once)

    def test_main_rewrites_files_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            path.write_bytes(b"rdt=abcdef123456\n")
            main([str(path)])
            self.assertEqual(path.read_bytes(), b"rdt=" + b"x" * 12 + b"\n")


class PinnedDataTest(unittest.TestCase):
    def test_pinned_data_is_already_redacted(self):
        for name in manifest()["files"]:
            data = (DATA_DIR / name).read_bytes()
            self.assertEqual(redact(data), data, name)
