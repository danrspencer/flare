"""Local viewer: trace steps on the left, the blueprint YAML on the right.

Hovering a step in a captured trace (see tests/behaviour/ and
scripts/trace_summary.py) scrolls the YAML pane to - and highlights - the
exact block that step corresponds to. scripts/trace_summary.py's markdown
table answers "did this pass or fail"; this answers "which line is that",
which the table can't (it has no notion of the blueprint's source text at
all).

The trick is that a Home Assistant trace path (e.g.
"action/0/default/1/if/condition/0") doesn't always match the YAML's own
key names one-for-one - `if:`'s value is a bare list, but the trace
inserts a synthetic "condition" segment before indexing into it (see
homeassistant/helpers/script.py's `_async_step_if`, which calls
`_test_conditions(if_data["if_conditions"], "if", "condition")` - "if" is
the literal YAML key, "condition" is not, it's just the label the tracer
always uses for a conditions list). `resolve()` in trace_viewer.html
handles this generically: a word segment with no matching key on the
current map is treated as a label with nothing to consume, and passed
through unchanged so the following numeric segment indexes the list it
already found. That one rule, with no special-casing of "if" specifically,
also covers the top-level `condition:`/`action:` keys and choose/and/or
`conditions:` lists, because those really do match the YAML literally.

Line numbers come from `yaml.compose()`'s Node objects (`start_mark`/
`end_mark`), not a hand-rolled indentation parser - PyYAML already parses
this file correctly (block scalars, `!input`, comments and all), so there
is no reason to reimplement that. The only custom bit is a constructor for
`!input` (the one non-standard tag this blueprint uses), and the
recursive walk that carries each node's line range into the JSON handed
to the browser.

Usage: python scripts/trace_viewer.py [--port 8765] [--no-open]
Then: mise run test:behaviour to (re)capture traces, pick one from the
dropdown. The YAML is re-read from disk on every /api/yaml request, so
editing the blueprint and hitting the page's Reload button reflects the
change with no server restart needed.
"""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BLUEPRINT_PATH = REPO_ROOT / "blueprints" / "automation" / "danspencer" / "flare.yaml"
TRACE_DIR = REPO_ROOT / "trace-dumps"
HTML_PATH = Path(__file__).resolve().parent / "trace_viewer.html"

TRACE_NAME_RE = re.compile(r"^[\w.-]+\.json$")


class _InputLoader(yaml.SafeLoader):
    """SafeLoader plus the one custom tag this blueprint uses."""


_InputLoader.add_constructor(
    "!input", lambda loader, node: "!input " + loader.construct_scalar(node)
)


def _annotate(node: yaml.Node, loader: _InputLoader) -> dict:
    """A node -> {__type__, __line__, __end_line__, value}, recursively.

    __line__/__end_line__ are 1-indexed and bound the node's own source
    lines - enough for the browser to highlight and scroll to the right
    span without it needing to understand YAML itself.
    """
    start = node.start_mark.line + 1
    end = node.end_mark.line + (0 if node.end_mark.column == 0 else 1)
    end = max(start, end)

    if isinstance(node, yaml.MappingNode):
        value = {}
        for key_node, value_node in node.value:
            key = str(loader.construct_object(key_node, deep=True))
            value[key] = _annotate(value_node, loader)
        return {"__type__": "map", "__line__": start, "__end_line__": end, "value": value}

    if isinstance(node, yaml.SequenceNode):
        items = [_annotate(child, loader) for child in node.value]
        return {"__type__": "seq", "__line__": start, "__end_line__": end, "value": items}

    scalar = loader.construct_object(node, deep=True)
    return {"__type__": "scalar", "__line__": start, "__end_line__": end, "value": scalar}


def _yaml_payload() -> dict:
    text = BLUEPRINT_PATH.read_text(encoding="utf-8")
    loader = _InputLoader(text)
    try:
        root = loader.get_single_node()
        tree = _annotate(root, loader)
    finally:
        loader.dispose()
    return {
        "text": text,
        "tree": tree,
        "path": str(BLUEPRINT_PATH.relative_to(REPO_ROOT)),
    }


def _trace_listing() -> list[dict]:
    entries = []
    for p in sorted(TRACE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text())
            test = data.get("test", p.stem)
            outcome = data.get("outcome", "?")
            runs = len(data.get("traces", []))
        except (json.JSONDecodeError, OSError):
            test, outcome, runs = p.stem, "parse-error", 0
        entries.append({"name": p.name, "test": test, "outcome": outcome, "runs": runs})
    return entries


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # the default access log is noise for a single-user local tool

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path

        if path in ("/", "/index.html"):
            body = HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/yaml":
            try:
                self._send_json(_yaml_payload())
            except yaml.YAMLError as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/traces":
            self._send_json(_trace_listing())
            return

        if path.startswith("/api/trace/"):
            name = path.removeprefix("/api/trace/")
            if not TRACE_NAME_RE.match(name):
                self._send_json({"error": "invalid trace name"}, status=400)
                return
            candidate = TRACE_DIR / name
            if candidate.parent != TRACE_DIR or not candidate.is_file():
                self._send_json({"error": "not found"}, status=404)
                return
            body = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        self._send_json({"error": "not found"}, status=404)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="don't launch a browser")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Trace viewer at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
