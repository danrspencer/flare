"""Cut betas and promote them to stable releases, without ever committing
a version number to a branch.

WHY NO VERSION IN THE SOURCE. HACS reads a release's version out of the
`manifest.json` inside the tag it downloads, so every release needs a
commit whose files say the right thing. Putting that commit on a branch
means either a person bumps it by hand (which is how the blueprint stamp
got forgotten) or a bot pushes it and the branch it came from never
contains it, so dev and main drift apart on every release.

So the manifest carries a placeholder (0.0.0-dev) and a release is
built on the side: a commit on top of the source commit with the real
version written into the three places it lives, tagged, and left
unreachable from any branch. Nothing moves. The other two (the constant
in blueprint_version.py and the blueprint's description stamp) hold
whatever they last held in source and are overwritten the same way, with
the same number: the blueprint is versioned with FLARE, not separately.
A beta and the release it becomes are the same source commit with
different numbers written in.

The commit message records that source (`Source: <sha>`), which is how a
promotion finds what to rebuild.

Five subcommands. The first two build and tag locally and print what they
did; the others only answer a question. Pushing the tag and
publishing the GitHub release is the workflow's job, because that is the
part that needs credentials:

    release.py cut-beta --source SHA     what .github/workflows/cut-beta.yml runs
    release.py promote [--force]         what .github/workflows/promote.yml runs
    release.py check --source SHA        what .github/workflows/tests.yml runs on a pull request
    release.py preview --source SHA      what .github/workflows/release-preview.yml comments with
    release.py docs-source --head SHA    what .github/workflows/docs.yml builds a release's docs from

Pure functions up top, git at the bottom. Standard library only, so the
workflows need no install step.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST = "custom_components/flare/manifest.json"
BLUEPRINT_VERSION_PY = "custom_components/flare/blueprint_version.py"
BLUEPRINT = "custom_components/flare/blueprints/flare.yaml"
CHANGELOG = "CHANGELOG.md"

# How long a version's newest beta must sit before it is promoted.
SOAK = timedelta(days=7)

# The paths whose contents reach a user's house. A push to main that
# touches none of them (docs, tests, CI) has nothing to put in a beta.
SHIPPED = ("custom_components",)

_BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


class Skip(Exception):
    """Nothing to do, and that is fine - not a failure."""


class Refuse(Exception):
    """Something is wrong and a person needs to look."""


# --- Versions ----------------------------------------------------------

_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?")


@dataclass(frozen=True, order=True)
class Tag:
    """A release tag of ours: `vX.Y.Z` or `vX.Y.Z-beta.N`.

    Field order IS the sort order: by base, then stable above any beta of
    that base (False < True), then by beta number. Anything else in the
    repository's tag list is not a Tag and is ignored.
    """

    base: tuple[int, int, int]
    stable: bool
    beta: int

    @classmethod
    def parse(cls, name: str) -> Tag | None:
        m = _TAG.fullmatch(name)
        if not m:
            return None
        major, minor, patch, beta = m.groups()
        return cls((int(major), int(minor), int(patch)), beta is None, int(beta or 0))

    @property
    def base_str(self) -> str:
        return ".".join(map(str, self.base))

    @property
    def version(self) -> str:
        return self.base_str if self.stable else f"{self.base_str}-beta.{self.beta}"

    @property
    def name(self) -> str:
        return f"v{self.version}"


def parse_base(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def changelog_base(text: str) -> str | None:
    """The version the changelog's top section is working toward.

    That heading is already required before the first beta, so it is the
    one place a person says what number they are aiming at - and reading
    it here means there is no second place to say it.
    """
    m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    return m.group(1) if m else None


def highest_stable(tags: list[Tag]) -> tuple[int, int, int] | None:
    return max((t.base for t in tags if t.stable), default=None)


# --- Deciding ----------------------------------------------------------


def next_beta(base: str, tags: list[Tag]) -> Tag:
    """The beta to cut for a changelog whose top section is `base`.

    Refuses to go backwards. HACS orders releases by version, so a beta
    below one that already exists would be offered to testers as a
    downgrade, and one at or below a stable release would be a beta of
    something already shipped.
    """
    want = parse_base(base)

    stable = highest_stable(tags)
    if stable is not None and want <= stable:
        raise Skip(
            f"the changelog's top section is [{base}], which is already released "
            f"(v{'.'.join(map(str, stable))}). Add a section for the next version "
            "to have a change ship."
        )

    seen = max((t.base for t in tags), default=None)
    if seen is not None and want < seen:
        raise Refuse(
            f"the changelog's top section is [{base}], but betas of "
            f"{'.'.join(map(str, seen))} already exist. Cutting this would look "
            "like a downgrade to anyone on the beta channel."
        )

    n = max((t.beta for t in tags if t.base == want and not t.stable), default=0)
    return Tag(want, False, n + 1)


def notes_start(tag: Tag, tags: list[Tag]) -> Tag | None:
    """The tag a release's notes count from: a beta's, the newest tag below
    it; a release's, the newest release below it, since its own betas are
    nearly the same code.

    Named explicitly because release commits are on no branch, so GitHub
    finds no earlier tag among a release's ancestors.
    """
    earlier = [t for t in tags if t < tag and (t.stable or not tag.stable)]
    return max(earlier, default=None)


def pick_promotion(
    tags: list[Tag],
    made_at: dict[str, datetime],
    now: datetime,
    *,
    soak: timedelta = SOAK,
    force: bool = False,
) -> Tag:
    """The beta to turn into a release: the newest beta of the highest
    version whose newest beta has sat for the whole soak period.

    Per version, not overall. A fresh 0.0.2-beta.1 does not hold back
    0.0.1-beta.4 - each version's clock is its own newest beta - but a
    later beta of the SAME version restarts that version's clock, since
    what is being promoted is that beta's contents.

    Only versions above the highest stable release are candidates, which
    is what stops tags pushed in an odd order from promoting a downgrade;
    a lower version left behind is superseded and stays that way.
    """
    stable = highest_stable(tags)

    newest: dict[tuple[int, int, int], Tag] = {}
    for t in tags:
        if t.stable or (stable is not None and t.base <= stable):
            continue
        if t.base not in newest or t > newest[t.base]:
            newest[t.base] = t

    if not newest:
        raise Skip("no beta is waiting to be promoted")

    waiting = []
    for base in sorted(newest, reverse=True):
        beta = newest[base]
        age = now - made_at[beta.name]
        if force or age >= soak:
            return beta
        waiting.append(f"{beta.name} is {age.days}d old")

    raise Skip(f"nothing has soaked for {soak.days} days yet: " + ", ".join(waiting))


# --- Writing the version into a tree ------------------------------------

# The line a blueprint's description carries. Kept in step with
# blueprint_version._VERSION_IN_DESCRIPTION by a test that reads a stamp
# back through that module, rather than by importing its private name.
_STAMP = re.compile(r"(Blueprint version\s+)(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)")


def _replace_once(path: Path, pattern: str, replacement: str, flags: int = 0) -> None:
    text = path.read_text()
    new, count = re.subn(pattern, replacement, text, flags=flags)
    if count != 1:
        raise Refuse(f"expected exactly one match for {pattern!r} in {path.name}, found {count}")
    path.write_text(new)


def stamp_tree(root: Path, version: str) -> None:
    """Write `version` into the three places a release carries it: the
    manifest, and the constant and the blueprint's own stamp, which are
    always the release's version. Each must match exactly once, so a file
    that was reshaped fails here rather than shipping unstamped."""
    _replace_once(root / MANIFEST, r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{version}\g<2>")
    _replace_once(
        root / BLUEPRINT_VERSION_PY,
        r'^(BLUEPRINT_VERSION = ")[^"]*(")',
        rf"\g<1>{version}\g<2>",
        re.MULTILINE,
    )
    _replace_once(root / BLUEPRINT, _STAMP.pattern, rf"\g<1>{version}")


# --- git ---------------------------------------------------------------


class Repo:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.root,
            capture_output=True,
            text=True,
            check=check,
        )

    def out(self, *args: str, cwd: Path | None = None) -> str:
        return self.git(*args, cwd=cwd).stdout.strip()

    def tags(self) -> tuple[list[Tag], dict[str, datetime]]:
        """Every tag of ours, and when it was made. Lightweight tags, so
        creatordate is the release commit's own date."""
        listing = self.out(
            "for-each-ref", "--format=%(refname:strip=2)|%(creatordate:iso-strict)", "refs/tags"
        )
        tags, made_at = [], {}
        for line in listing.splitlines():
            name, _, when = line.partition("|")
            tag = Tag.parse(name)
            if tag:
                tags.append(tag)
                made_at[name] = datetime.fromisoformat(when)
        return tags, made_at

    def show(self, ref: str, path: str) -> str | None:
        result = self.git("show", f"{ref}:{path}", check=False)
        return result.stdout if result.returncode == 0 else None

    def source_of(self, tag: Tag) -> str:
        """The commit a release was built from, per its own message."""
        body = self.out("log", "-1", "--format=%B", tag.name)
        m = re.search(r"^Source: ([0-9a-f]{40})$", body, re.MULTILINE)
        if not m:
            raise Refuse(
                f"{tag.name} has no 'Source:' line, so it was not built by this script "
                "and there is nothing to rebuild it from."
            )
        return m.group(1)

    def shipped_changed(self, old: str, new: str) -> bool:
        return self.git("diff", "--quiet", old, new, "--", *SHIPPED, check=False).returncode != 0

    def build(self, tag: Tag, source: str) -> str:
        """Commit `source` with `tag`'s version written in, and tag it.

        Done in a throwaway worktree so the caller's checkout is never
        touched, and the result is reachable from no branch - which is
        the point.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "release"
            self.git("worktree", "add", "--detach", str(tree), source)
            try:
                stamp_tree(tree, tag.version)

                self.git("add", "-A", cwd=tree)
                self.git(
                    "-c", f"user.name={_BOT[0]}", "-c", f"user.email={_BOT[1]}",
                    "-c", "commit.gpgsign=false",
                    "commit", "--allow-empty", "-m", f"Release {tag.name}\n\nSource: {source}\n",
                    cwd=tree,
                )
                sha = self.out("rev-parse", "HEAD", cwd=tree)
            finally:
                self.git("worktree", "remove", "--force", str(tree), check=False)
        self.git("tag", tag.name, sha)
        return sha


# --- Subcommands -------------------------------------------------------


def check(repo: Repo, source: str) -> tuple[str, list[Tag], Tag]:
    """The full source SHA, our tags, and the beta `source` would become.

    Refuses a change to what ships while the changelog's top section names
    a version that is already out: the change belongs in a new section.
    """
    # Whatever the caller passed (HEAD, a branch, a short SHA), record the
    # full SHA: it is written into the release commit and read back at
    # promotion time, when HEAD would mean something else entirely.
    source = repo.out("rev-parse", "--verify", f"{source}^{{commit}}")
    tags, _ = repo.tags()

    text = repo.show(source, CHANGELOG) or ""
    base = changelog_base(text)
    if base is None:
        raise Refuse(f"{CHANGELOG} has no '## [x.y.z]' section to read the target version from")

    stable = highest_stable(tags)
    if stable is not None and parse_base(base) <= stable:
        released = Tag(stable, True, 0)
        try:
            changed = repo.shipped_changed(repo.source_of(released), source)
        except Refuse:
            changed = True  # a hand-made release: no recorded source to compare
        if changed:
            raise Refuse(
                f"the changelog's top section is [{base}], which is already released "
                f"({released.name}), but {', '.join(SHIPPED)} has changed since. Add a "
                f"section for the next version to {CHANGELOG} and list the change there."
            )

    return source, tags, next_beta(base, tags)


def planned_beta(repo: Repo, source: str) -> tuple[str, list[Tag], Tag]:
    """check(), and also Skip when nothing shipped has changed since the
    version's last beta."""
    source, tags, beta = check(repo, source)

    # A push that changed nothing a house would receive (docs, tests, CI)
    # would otherwise cut a beta that HACS offers testers as an update to
    # identical code. Also what makes a re-run of the same commit a no-op.
    earlier = [t for t in tags if t.base == beta.base and not t.stable]
    if earlier:
        last = max(earlier)
        try:
            if not repo.shipped_changed(repo.source_of(last), source):
                raise Skip(f"nothing under {', '.join(SHIPPED)} has changed since {last.name}")
        except Refuse:
            pass  # a hand-made beta: no recorded source, so cut a fresh one
    return source, tags, beta


def cut_beta(repo: Repo, source: str) -> Tag:
    source, _, beta = planned_beta(repo, source)
    repo.build(beta, source)
    return beta


def docs_source(repo: Repo, head: str, tag_name: str | None = None) -> tuple[Tag, str]:
    """A release (the newest unless named) and the commit to build its docs
    from: `head`, while nothing shipped has changed since the release's
    source, so a docs fix after the last beta still reaches the release;
    otherwise the release itself, whose docs match its code.
    """
    head = repo.out("rev-parse", "--verify", f"{head}^{{commit}}")
    if tag_name is None:
        tags, _ = repo.tags()
        stable = highest_stable(tags)
        if stable is None:
            raise Skip("there is no release yet")
        tag = Tag(stable, True, 0)
    else:
        tag = Tag.parse(tag_name)
        if tag is None or not tag.stable:
            raise Refuse(f"{tag_name} is not a release tag")
    try:
        changed = repo.shipped_changed(repo.source_of(tag), head)
    except Refuse:
        changed = True  # a hand-made release: build its docs from the tag
    return tag, tag.name if changed else head


def promote(repo: Repo, now: datetime, *, force: bool = False) -> Tag:
    tags, made_at = repo.tags()
    beta = pick_promotion(tags, made_at, now, force=force)

    stable = Tag(beta.base, True, 0)
    repo.build(stable, repo.source_of(beta))
    return stable


def preview(repo: Repo, source: str) -> tuple[Tag | None, Tag | None, str]:
    """The beta `source` would ship as if pushed to main now, the tag its
    notes would count from, and, when it would ship as nothing, why."""
    try:
        _, tags, beta = planned_beta(repo, source)
    except (Skip, Refuse) as reason:
        return None, None, str(reason)
    return beta, notes_start(beta, tags), ""


def _notes_start_name(repo: Repo, tag: Tag) -> str:
    previous = notes_start(tag, repo.tags()[0])
    return previous.name if previous else ""


def _emit(**outputs: str) -> None:
    for key, value in outputs.items():
        print(f"{key}={value}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for key, value in outputs.items():
                f.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    beta = sub.add_parser("cut-beta", help="build the next beta from a source commit")
    beta.add_argument("--source", required=True, help="the commit to release")

    chk = sub.add_parser("check", help="fail if a commit changes a version that is already out")
    chk.add_argument("--source", required=True, help="the commit to check")

    prom = sub.add_parser("promote", help="build a stable release from the beta that has soaked")
    prom.add_argument("--force", action="store_true", help="ignore the soak period")

    pre = sub.add_parser("preview", help="the beta a commit would ship as, for a pull request comment")
    pre.add_argument("--source", required=True, help="the commit to preview")

    docs = sub.add_parser("docs-source", help="the commit to build a release's docs from")
    docs.add_argument("--head", required=True, help="the newest commit on main")
    docs.add_argument("--tag", help="the release (default: the newest)")

    args = parser.parse_args(argv)
    repo = Repo(REPO_ROOT)

    try:
        if args.command == "check":
            _, _, beta = check(repo, args.source)
            print(f"OK: this would ship as {beta.name}")
        elif args.command == "preview":
            tag, previous, reason = preview(repo, args.source)
            _emit(
                tag=tag.name if tag else "", previous=previous.name if previous else "", reason=reason
            )
        elif args.command == "docs-source":
            tag, ref = docs_source(repo, args.head, args.tag)
            _emit(tag=tag.name, ref=ref, follows_head=str(ref != tag.name).lower())
        elif args.command == "cut-beta":
            tag = cut_beta(repo, args.source)
            _emit(tag=tag.name, previous=_notes_start_name(repo, tag), prerelease="true")
        else:
            tag = promote(repo, datetime.now(timezone.utc), force=args.force)
            _emit(tag=tag.name, previous=_notes_start_name(repo, tag), prerelease="false")
    except Skip as skip:
        done = "Nothing to follow" if args.command == "docs-source" else "Nothing released"
        print(f"::notice::{done}: {skip}")
        _emit(tag="")
    except Refuse as refusal:
        print(f"::error::{refusal}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
