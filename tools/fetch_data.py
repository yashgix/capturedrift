"""Download the pinned agent-session subset into data/, redact personal data, and check it against data/MANIFEST.json.

Every file comes from a public, ungated Hugging Face dataset at a fixed commit. Each upstream file is checked
against its recorded sha256 before redaction and again after. `--verify` only checks files already present and
needs no network.
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
HUB = "https://huggingface.co/datasets/"

# Placeholder or service names that publishers already left in home paths; anything else is treated as a person.
KEEP_NAMES = {"user", "user1", "node", "runner", "root"}
HOME = re.compile(rb"(/Users/|/home/|[A-Za-z]:(?:\\\\|/)Users(?:\\\\|/))([A-Za-z][A-Za-z0-9_.-]*)")
ENCODED_HOME = re.compile(rb"(-(?:Users|home)-)([A-Za-z][A-Za-z0-9_]*)(?![A-Za-z0-9_])")
# An address may follow a JSON escape such as \n or \u003c, whose last character is a letter or digit.
EMAIL = re.compile(
    rb"(?:(?<=\\[nrt])|(?<=\\u[0-9a-fA-F]{4})|(?<![\\A-Za-z0-9._%+-]))"
    rb"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
    rb"\.(?:com|org|net|io|ai|dev|edu|gov|co|me|app|xyz|info|us|uk|de|fr|in|cn|jp)\b"
)
TOKEN = re.compile(
    rb"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|hf_[A-Za-z0-9]{30,}"
    rb"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,})"
)


def _home(match):
    name = match.group(2)
    return match.group(0) if name.lower().decode() in KEEP_NAMES else match.group(1) + b"user"


RULES = (
    ("home", HOME, _home),
    ("encoded_home", ENCODED_HOME, _home),
    ("email", EMAIL, lambda m: b"user@example.com"),
    ("token", TOKEN, lambda m: b"REDACTED"),
)


def _sub(pattern, replace, raw):
    """pattern.sub with a count of the matches that actually changed."""
    changed = 0

    def counted(match):
        nonlocal changed
        new = replace(match)
        changed += new != match.group(0)
        return new

    return pattern.sub(counted, raw), changed


# Credential shapes, as a credential scan checks them; none may stay in the data.
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|PASSWORD)=[^\s\"']{8,}"
)
# In decoded text, any NAME=value: a short value can still match in the raw line once escapes such as \n count.
ASSIGNMENT = re.compile(r"([A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|PASSWORD))=[^\s\"']*")
BARE = {
    "sk": "sk-REDACTED",
    "gh": "ghp_REDACTED",
    "xo": "xoxb-REDACTED",
    "AK": "AKIA-EXAMPLE",
    "--": "-----BEGIN KEY-----",
}


def _neutral(text):
    """text with every credential shape replaced by a placeholder that cannot match again, and the count."""
    text, n = ASSIGNMENT.subn(lambda m: m.group(1) + "='x'", text)
    text, k = SECRET.subn(lambda m: BARE[m.group(0)[:2]], text)
    return text, n + k


def _scrub(value):
    if isinstance(value, str):
        return _neutral(value)
    if isinstance(value, list):
        items = [_scrub(v) for v in value]
        return [v for v, _ in items], sum(n for _, n in items)
    if isinstance(value, dict):
        items = [(_neutral(k), _scrub(v)) for k, v in value.items()]
        return {k: v for (k, _), (v, _) in items}, sum(a + b for (_, a), (_, b) in items)
    return value, 0


def scrub_line(line):
    """One JSON line with credential shapes replaced inside its decoded strings; re-encoded only when changed."""
    value, n = _scrub(json.loads(line))
    if not n:
        return line, 0
    spaced = b'": ' in line or b'", "' in line
    separators = (", ", ": ") if spaced else (",", ":")
    return json.dumps(value, ensure_ascii=False, separators=separators).encode(), n


def scrub_text(raw):
    """Plain text (dataset cards) with credential shapes replaced."""
    text, n = _neutral(raw.decode("utf-8"))
    return text.encode("utf-8"), n


def sanitize(raw):
    """Redacted bytes and the number of replacements per rule. The byte rules never insert quotes or backslashes,
    so every JSON line stays valid; credential shapes are replaced in each line's decoded strings."""
    counts = {}
    for rule, pattern, replace in RULES:
        raw, counts[rule] = _sub(pattern, replace, raw)
    lines, counts["secret"] = [], 0
    for line in raw.split(b"\n"):
        if line.strip():
            line, n = scrub_line(line)
            counts["secret"] += n
        lines.append(line)
    return b"\n".join(lines), counts


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def download(source, path):
    url = f"{HUB}{source['dataset']}/resolve/{source['revision']}/{urllib.parse.quote(path)}"
    request = urllib.request.Request(url, headers={"User-Agent": "capturedrift fetch"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch(manifest):
    sources = manifest["sources"]
    for name, entry in manifest["files"].items():
        target = DATA / name
        if target.is_file():
            continue
        raw = download(sources[entry["source"]], entry["upstream_path"])
        if sha256(raw) != entry["upstream_sha256"]:
            sys.exit(f"upstream changed: {entry['source']} {entry['upstream_path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sanitize(raw)[0])
        time.sleep(1)


def problems(manifest):
    return [name for name, entry in manifest["files"].items()
            if not (DATA / name).is_file() or sha256((DATA / name).read_bytes()) != entry["sha256"]]  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="check files only; no network")
    args = parser.parse_args()
    manifest = json.loads((DATA / "MANIFEST.json").read_text())
    if not args.verify:
        fetch(manifest)
    bad = problems(manifest)
    for name in bad:
        print(f"missing or changed: {name}", file=sys.stderr)
    if bad:
        sys.exit("the data no longer matches the pinned snapshot")
    print(f"{len(manifest['files'])} files match MANIFEST.json")


if __name__ == "__main__":
    main()
