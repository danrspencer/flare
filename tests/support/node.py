"""Running the dashboard's JS modules under node."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# Enough of the browser for the dashboard modules to import.
_SHIMS = """
globalThis.HTMLElement = class {};
globalThis.customElements = { define() {}, get() { return undefined; }, whenDefined: () => Promise.resolve() };
globalThis.window = globalThis;
"""


def js_path(path: Path) -> str:
    """A path as a JS string literal, for `await import(...)`."""
    return json.dumps(path.as_posix())


def run_js(body: str, payload: Any = None) -> Any:
    """Run `body` as the inside of an async function, with `input` bound to
    `payload`, and return what it returns (via JSON)."""
    driver = f"""{_SHIMS}
const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));
const result = await (async () => {{
{body}
}})();
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", driver],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout)
