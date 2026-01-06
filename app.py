"""Lightweight web UI server to visualize repository word, code, and structure clouds.

Run the server with:

```
python app.py --port 8000
```

Then open http://localhost:8000 to interact with the UI.
"""

from __future__ import annotations

import argparse
import http.server
import json
from collections import Counter
from pathlib import Path
import re
import socketserver
from typing import Iterable, List, Sequence
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = REPO_ROOT / "public"
MAX_FILE_BYTES = 400_000
DEFAULT_EXCLUDES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
}
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def should_skip_path(path: Path) -> bool:
    """Return True if the path should be excluded from scanning."""

    parts = set(path.parts)
    return any(excluded in parts for excluded in DEFAULT_EXCLUDES)


def is_probably_text(data: bytes) -> bool:
    """Heuristic to detect binary files.

    If a null byte is present or more than a small fraction of bytes are
    non-printable, the data is treated as binary.
    """

    if not data:
        return False
    if b"\0" in data:
        return False

    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in data)
    return printable / len(data) > 0.8


def read_text(path: Path) -> str:
    """Read a file defensively and return text content or an empty string."""

    try:
        raw = path.read_bytes()[:MAX_FILE_BYTES]
    except (OSError, PermissionError):
        return ""

    if not is_probably_text(raw):
        return ""

    try:
        return raw.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return ""


def split_identifier(token: str) -> List[str]:
    """Break identifiers into readable pieces.

    Examples:
        "codeCloud" -> ["code", "cloud"]
        "code_cloud" -> ["code", "cloud"]
        "HTTPServer" -> ["http", "server"]
    """

    pieces: List[str] = []
    for chunk in re.split(r"[_\-]+", token):
        if not chunk:
            continue
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", chunk)
        pieces.extend(camel_parts or [chunk])
    return [piece.lower() for piece in pieces if len(piece) > 1]


def tokenize(text: str, mode: str) -> Iterable[str]:
    """Yield tokens for the requested mode.

    Words mode favors human-readable text and ignores very short tokens.
    Code mode aggressively splits identifiers and keeps alphanumerics.
    """

    base_tokens = re.findall(r"[A-Za-z0-9_]+", text)
    for token in base_tokens:
        if mode == "words":
            lowered = token.lower()
            if len(lowered) > 2:
                yield lowered
        elif mode == "code":
            for piece in split_identifier(token):
                yield piece
        else:  # symbols
            # Symbols mode is extracted separately; do not use generic tokens here.
            return


def symbol_tokens(text: str) -> Iterable[str]:
    """Extract class, function/method, and top-level variable names."""

    definitions: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//", "/*", "*", "--")):
            continue

        class_match = re.match(
            r"^(?:export\s+)?(?:abstract\s+)?(?:public\s+|private\s+|protected\s+)?"
            r"(?:class|interface|struct|trait)\s+([A-Za-z_][\w]*)",
            stripped,
        )
        if class_match:
            definitions.append(class_match.group(1))
            continue

        func_match = re.match(
            r"^(?:export\s+)?(?:async\s+)?(?:public\s+|private\s+|protected\s+|static\s+)?"
            r"(?:def|func|fn|function)\s+([A-Za-z_][\w]*)",
            stripped,
        )
        if func_match:
            definitions.append(func_match.group(1))
            continue

        # Top-level variable or constant (avoid obvious indent)
        if not line.startswith((" ", "\t")):
            var_match = re.match(r"^([A-Za-z_][\w]*)\s*=", stripped)
            if var_match:
                definitions.append(var_match.group(1))

    for name in definitions:
        lowered = name.lower()
        if len(lowered) > 1:
            yield lowered


def should_skip_file(path: Path, mode: str) -> bool:
    """Decide if a file should be skipped for the given mode."""

    if should_skip_path(path) or path.name.startswith("."):
        return True
    if not path.is_file():
        return True
    if mode == "symbols" and path.suffix.lower() in JS_EXTENSIONS:
        return True
    return False


def collect_frequencies(mode: str) -> List[dict]:
    """Walk the repository and build frequency data for the requested mode."""

    counter: Counter[str] = Counter()
    scanned_files = 0

    for path in REPO_ROOT.rglob("*"):
        if path.is_dir():
            if should_skip_path(path):
                continue
            continue

        if should_skip_file(path, mode):
            continue

        text = read_text(path)
        if not text:
            continue

        scanned_files += 1
        if mode == "symbols":
            counter.update(symbol_tokens(text))
        else:
            counter.update(tokenize(text, mode))

    most_common = counter.most_common(120)
    return [
        {"term": term, "count": count, "mode": mode, "files": scanned_files}
        for term, count in most_common
    ]


def build_response(mode: str) -> dict:
    items = collect_frequencies(mode)
    total_terms = sum(item["count"] for item in items)
    return {
        "mode": mode,
        "items": items,
        "total_terms": total_terms,
    }


class CloudRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static assets and a JSON API for the cloud data."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - required by parent class
        parsed = urlparse(self.path)
        if parsed.path == "/api/cloud":
            query = parse_qs(parsed.query)
            requested_mode = query.get("type", ["words"])[0].lower()
            if requested_mode not in {"words", "code", "symbols"}:
                requested_mode = "words"
            mode = requested_mode
            payload = build_response(mode)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        super().do_GET()

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - match signature
        # Quieter logging that still shows path and status code.
        message = f"{self.address_string()} - {format % args}"
        print(message)


def serve(host: str, port: int) -> None:
    handler = CloudRequestHandler
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"Serving code cloud UI at http://{host}:{port}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a repository word/code/structure cloud UI"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument(
        "--mode",
        choices=["words", "code", "symbols"],
        help="Optional: print a single analysis to stdout instead of starting the server.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mode:
        data = build_response(args.mode)
        print(json.dumps(data, indent=2))
        return

    if not PUBLIC_DIR.exists():
        raise SystemExit("public/ directory is missing; static assets are required.")

    serve(args.host, args.port)


if __name__ == "__main__":
    main()
