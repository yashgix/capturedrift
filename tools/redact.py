"""Replace third-party cookie values and signed-URL signatures in session files with same-length runs of `x`.

Byte counts, JSON validity, keys and structure stay as they were, and a second pass changes nothing.
Usage: python tools/redact.py FILE... (rewrites each file in place).
"""

import re
import sys
from pathlib import Path

COOKIES = rb"csrf_token|loid|rdt|session_tracker|edgebucket|reddit_chat_path|_cfuvid|_gh_sess|_octo"
# A name may follow a JSON escape such as \n, whose last character is a letter.
# Values under 8 bytes, such as `test`, are placeholders and stay.
START = rb"(?:(?<![A-Za-z0-9_-])|(?<=\\[nrt]))"
VALUES = (
    re.compile(START + rb"(?:" + COOKIES + rb")=([^;\s\"'\\,&`]{8,})"),
    # The browser id inside Google's g_state cookie, whose quotes are JSON-escaped in the logs.
    re.compile(rb"i_b\\*\":\\*\"([A-Za-z0-9+/=]+)"),
    # Signed download URLs (CloudFront and S3), whose separator may be JSON-escaped as \u0026.
    re.compile(rb"(?:[?&]|\\u0026)(?:X-Amz-)?Signature=([^&\s\"'\\]+)"),
)


def _blank(match):
    start, end = (i - match.start() for i in match.span(1))
    whole = match.group(0)
    return whole[:start] + b"x" * (end - start) + whole[end:]


def redact(raw):
    """raw with every matched value replaced by as many `x` bytes."""
    for pattern in VALUES:
        raw = pattern.sub(_blank, raw)
    return raw


def main(paths):
    for path in map(Path, paths):
        path.write_bytes(redact(path.read_bytes()))


if __name__ == "__main__":
    main(sys.argv[1:])
