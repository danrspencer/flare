"""Assemble the versioned docs site.

GitHub Pages serves one upload at a time, so every version the site
offers is kept, already built, on the `docs-site` branch, and each publish
updates its own part of that tree and uploads the whole of it:

    /                 the latest release (the beta, until there is one)
    /v/<version>/     every release
    /beta/            the newest beta, while it is newer than the latest release
    /trace-report/    the blueprint trace report, from the newest beta build
    /_versions/       versions.json and the picker every page loads

The root is a build of its own, not a redirect, so links to
https://danrspencer.github.io/flare/... keep working and land on the
latest release. The picker is added to every page when the site is
assembled rather than when a version is built, so older versions get
today's picker too.

    docs_site.py beta-version
    docs_site.py publish --site DIR --channel beta|release --version V \\
        --build DIR --root-build DIR

Standard library only, like release.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release import Tag  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PICKER_SOURCE = REPO_ROOT / "docs" / "_versions" / "picker.js"

RELEASES = "v"
BETA = "beta"
TRACE_REPORT = "trace-report"
VERSIONS = "_versions"
# What the root build must never replace.
RESERVED = {RELEASES, BETA, TRACE_REPORT, VERSIONS, ".git", ".nojekyll"}

PICKER_TAG = '<script defer src="{base}/_versions/picker.js"></script>'
PICKER_MARK = "/_versions/picker.js"


def _tag(version: str) -> Tag:
    tag = Tag.parse(f"v{version}")
    if tag is None:
        raise ValueError(f"not a version of ours: {version}")
    return tag


def read_versions(site: Path) -> dict:
    path = site / VERSIONS / "versions.json"
    if path.is_file():
        return json.loads(path.read_text())
    return {"releases": [], "beta": None}


def _write_versions(site: Path, versions: dict) -> None:
    releases = sorted(set(versions["releases"]), key=_tag, reverse=True)
    beta = versions["beta"]
    if beta and releases and _tag(beta) <= _tag(releases[0]):
        beta = None
    out = {"latest": releases[0] if releases else beta, "releases": releases, "beta": beta}
    (site / VERSIONS).mkdir(parents=True, exist_ok=True)
    (site / VERSIONS / "versions.json").write_text(json.dumps(out, indent=2) + "\n")


def _replace(target: Path, build: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(build, target)


def _replace_root(site: Path, build: Path) -> None:
    for child in site.iterdir():
        if child.name in RESERVED:
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in build.iterdir():
        if child.name in RESERVED:
            continue
        dest = site / child.name
        shutil.copytree(child, dest) if child.is_dir() else shutil.copy2(child, dest)


def _move_trace_report(site: Path, build: Path) -> None:
    report = build / TRACE_REPORT
    if report.is_dir():
        _replace(site / TRACE_REPORT, report)
        shutil.rmtree(report)


def inject_picker(site: Path, base: str) -> None:
    """Every page loads the picker, once."""
    tag = PICKER_TAG.format(base=base)
    for page in site.rglob("*.html"):
        if page.relative_to(site).parts[0] in {TRACE_REPORT, ".git"}:
            continue
        html = page.read_text(encoding="utf-8")
        if PICKER_MARK in html or "</head>" not in html:
            continue
        page.write_text(html.replace("</head>", f"{tag}</head>", 1), encoding="utf-8")


def publish(site: Path, channel: str, version: str, build: Path, root_build: Path, base: str = "/flare") -> bool:
    """Put one build in place. Returns False when there is nothing to
    publish: a beta no newer than the latest release."""
    site.mkdir(parents=True, exist_ok=True)
    versions = read_versions(site)
    releases = versions["releases"]
    latest_release = max(releases, key=_tag) if releases else None

    if channel == BETA:
        _move_trace_report(site, build)
        shutil.rmtree(root_build / TRACE_REPORT, ignore_errors=True)
        if latest_release and _tag(version) <= _tag(latest_release):
            return False
        _replace(site / BETA, build)
        versions["beta"] = version
        if not releases:
            _replace_root(site, root_build)
    elif channel == "release":
        _replace(site / RELEASES / version, build)
        versions["releases"] = [*releases, version]
        if latest_release is None or _tag(version) >= _tag(latest_release):
            _replace_root(site, root_build)
        if versions["beta"] and _tag(versions["beta"]) <= _tag(max(versions["releases"], key=_tag)):
            versions["beta"] = None
            shutil.rmtree(site / BETA, ignore_errors=True)
    else:
        raise ValueError(f"unknown channel: {channel}")

    _write_versions(site, versions)
    shutil.copy2(PICKER_SOURCE, site / VERSIONS / "picker.js")
    (site / ".nojekyll").touch()
    inject_picker(site, base)
    return True


def latest_beta(tag_names: list[str]) -> str | None:
    betas = [t for t in map(Tag.parse, tag_names) if t is not None and not t.stable]
    return max(betas).version if betas else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("beta-version", help="the newest beta tag's version")
    pub = sub.add_parser("publish")
    pub.add_argument("--site", type=Path, required=True)
    pub.add_argument("--channel", choices=[BETA, "release"], required=True)
    pub.add_argument("--version", required=True)
    pub.add_argument("--build", type=Path, required=True)
    pub.add_argument("--root-build", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "beta-version":
        tags = subprocess.run(["git", "tag"], capture_output=True, text=True, check=True, cwd=REPO_ROOT).stdout
        version = latest_beta(tags.split())
        if version is None:
            print("no beta tags", file=sys.stderr)
            return 1
        print(version)
        return 0

    published = publish(args.site, args.channel, args.version, args.build, args.root_build)
    print(f"published {args.channel} {args.version}" if published else f"{args.version} is not newer than the latest release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
