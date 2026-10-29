"""Cut betas and promote them to stable releases, without ever committing
a version number.

Source carries a placeholder (0.0.0-dev) in the three places a version
lives: the manifest, the constant in blueprint_version.py and the
blueprint's description stamp. A release tags its source commit and
builds flare.zip from it with the real version written into all three;
HACS installs that zip (`zip_release` in hacs.json), never the tagged
files. The blueprint is versioned with FLARE, so all three get the same
number. A beta and the release it becomes are the same commit, tagged
twice.

Releases from before the zip were a commit on top of their source with
the version written in, and name that source in their message
(`Source: <sha>`); source_of() still reads it.

Seven subcommands. The first three tag and package locally and print what
they did; `package` only packages; the others only answer a question.
Pushing the tag and publishing the GitHub release with its zip is the
workflow's job, because that is the part that needs credentials:

    release.py cut-beta --source SHA     what .github/workflows/cut-beta.yml runs
    release.py promote [--force]         what .github/workflows/promote.yml runs
    release.py patch --source SHA        what .github/workflows/patch-release.yml runs
    release.py package --tag TAG         what .github/workflows/release.yml runs for a tag pushed by hand
    release.py check --source SHA        what .github/workflows/tests.yml runs on a pull request
    release.py preview --source SHA      what .github/workflows/release-preview.yml comments with

`check` and `preview` take `--patch` for a pull request into a release branch.
    release.py docs-source --head SHA    what .github/workflows/docs.yml builds a release's docs from

Pure functions up top, git at the bottom. Standard library only, so the
workflows need no install step.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST = "custom_components/flare/manifest.json"
BLUEPRINT_VERSION_PY = "custom_components/flare/blueprint_version.py"
BLUEPRINT = "custom_components/flare/blueprints/flare.yaml"
CHANGELOG = "CHANGELOG.md"
COMPONENT = "custom_components/flare"
# hacs.json's `filename`: the asset HACS downloads from each release.
ZIP = "flare.zip"
# Where the zip is written, for the workflow to attach.
DIST = "dist"

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

    Named explicitly because GitHub would count a release's notes from
    its own beta, the same commit, and older releases are on no branch.
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
        """Every tag of ours, and when it was made: an annotated tag's own
        date, or an older release commit's."""
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
        """The commit a release was built from: the tagged commit, or for an
        older release, the one its message names."""
        body = self.out("log", "-1", "--format=%B", tag.name)
        m = re.search(r"^Source: ([0-9a-f]{40})$", body, re.MULTILINE)
        return m.group(1) if m else self.out("rev-parse", f"{tag.name}^{{commit}}")

    def is_ancestor(self, old: str, new: str) -> bool:
        return self.git("merge-base", "--is-ancestor", old, new, check=False).returncode == 0

    def shipped_changed(self, old: str, new: str) -> bool:
        return self.git("diff", "--quiet", old, new, "--", *SHIPPED, check=False).returncode != 0

    def build(self, tag: Tag, source: str) -> None:
        """Tag `source`. Annotated, so the tag's date is when it was cut,
        which the soak period counts from."""
        self.git(
            "-c", f"user.name={_BOT[0]}", "-c", f"user.email={_BOT[1]}", "-c", "tag.gpgsign=false",
            "tag", "-a", tag.name, source, "-m", f"Release {tag.name}",
        )

    def package(self, tag: Tag, out: Path) -> Path:
        """The zip HACS installs for `tag`: the integration's folder at the
        tag with the version written in, its files at the zip's root."""
        archive = subprocess.run(
            ["git", "archive", tag.name, COMPONENT], cwd=self.root, capture_output=True, check=True
        ).stdout
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(tree, filter="data")
            stamp_tree(tree, tag.version)
            out.mkdir(parents=True, exist_ok=True)
            path = out / ZIP
            component = tree / COMPONENT
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zipped:
                for file in sorted(p for p in component.rglob("*") if p.is_file()):
                    zipped.write(file, file.relative_to(component).as_posix())
        return path


# --- Subcommands -------------------------------------------------------


def check(repo: Repo, source: str) -> tuple[str, list[Tag], Tag]:
    """The full source SHA, our tags, and the beta `source` would become.

    Refuses a change to what ships while the changelog's top section names
    a version that is already out: the change belongs in a new section.
    """
    # Whatever the caller passed (HEAD, a branch, a short SHA), tag the
    # full SHA: HEAD means something else by the time anything reads it.
    source = repo.out("rev-parse", "--verify", f"{source}^{{commit}}")
    tags, _ = repo.tags()

    text = repo.show(source, CHANGELOG) or ""
    base = changelog_base(text)
    if base is None:
        raise Refuse(f"{CHANGELOG} has no '## [x.y.z]' section to read the target version from")

    stable = highest_stable(tags)
    if stable is not None and parse_base(base) <= stable:
        released = Tag(stable, True, 0)
        if repo.shipped_changed(repo.source_of(released), source):
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
        if not repo.shipped_changed(repo.source_of(last), source):
            raise Skip(f"nothing under {', '.join(SHIPPED)} has changed since {last.name}")
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
    changed = repo.shipped_changed(repo.source_of(tag), head)
    return tag, tag.name if changed else head


def promote(repo: Repo, now: datetime, *, force: bool = False) -> Tag:
    tags, made_at = repo.tags()
    beta = pick_promotion(tags, made_at, now, force=force)

    stable = Tag(beta.base, True, 0)
    repo.build(stable, repo.source_of(beta))
    return stable


def planned_patch(repo: Repo, source: str) -> tuple[str, list[Tag], Tag]:
    """The full source SHA, our tags, and the current release's next patch,
    which `source` would ship as with no beta.

    Only the current release can be patched, from a commit built on its
    source whose changelog names the patch. Main with work in beta names the
    next version instead, so it can't go out as a patch.
    """
    source = repo.out("rev-parse", "--verify", f"{source}^{{commit}}")
    tags, _ = repo.tags()
    stable = highest_stable(tags)
    if stable is None:
        raise Refuse("there is no release to patch")
    current = Tag(stable, True, 0)
    tag = Tag((stable[0], stable[1], stable[2] + 1), True, 0)

    built_from = repo.source_of(current)
    if not repo.is_ancestor(built_from, source):
        raise Refuse(
            f"{source[:12]} is not built on {current.name}'s source ({built_from[:12]}). Branch "
            f"from that commit and cherry-pick the fix, so nothing else ships with it."
        )
    # Before the changelog, so a docs or test change needs no section.
    if not repo.shipped_changed(built_from, source):
        raise Skip(f"nothing under {', '.join(SHIPPED)} has changed since {current.name}")

    base = changelog_base(repo.show(source, CHANGELOG) or "")
    if base != tag.base_str:
        raise Refuse(
            f"a patch to {current.name} is {tag.name}, but the changelog's top section at "
            f"{source[:12]} is [{base}]. Add a '## [{tag.base_str}]' section above [{current.base_str}]."
        )
    return source, tags, tag


def patch(repo: Repo, source: str) -> Tag:
    source, _, tag = planned_patch(repo, source)
    repo.build(tag, source)
    return tag


def preview(repo: Repo, source: str, *, for_patch: bool = False) -> tuple[Tag | None, Tag | None, str]:
    """The beta `source` would ship as if pushed to main now (or the patch,
    pushed to a release branch), the tag its notes would count from, and,
    when it would ship as nothing, why."""
    try:
        _, tags, tag = (planned_patch if for_patch else planned_beta)(repo, source)
    except (Skip, Refuse) as reason:
        return None, None, str(reason)
    return tag, notes_start(tag, tags), ""


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
    chk.add_argument("--patch", action="store_true", help="check it as a patch, for a release branch")

    prom = sub.add_parser("promote", help="build a stable release from the beta that has soaked")
    prom.add_argument("--force", action="store_true", help="ignore the soak period")

    pat = sub.add_parser("patch", help="build the current release's next patch, with no beta")
    pat.add_argument("--source", required=True, help="the commit to release, built on the current release")

    pkg = sub.add_parser("package", help="build an existing tag's zip")
    pkg.add_argument("--tag", required=True, help="the release tag")

    pre = sub.add_parser("preview", help="the beta a commit would ship as, for a pull request comment")
    pre.add_argument("--source", required=True, help="the commit to preview")
    pre.add_argument("--patch", action="store_true", help="preview it as a patch, for a release branch")

    docs = sub.add_parser("docs-source", help="the commit to build a release's docs from")
    docs.add_argument("--head", required=True, help="the newest commit on main")
    docs.add_argument("--tag", help="the release (default: the newest)")

    args = parser.parse_args(argv)
    repo = Repo(REPO_ROOT)

    try:
        if args.command == "check":
            _, _, tag = (planned_patch if args.patch else check)(repo, args.source)
            print(f"OK: this would ship as {tag.name}")
        elif args.command == "preview":
            tag, previous, reason = preview(repo, args.source, for_patch=args.patch)
            _emit(
                tag=tag.name if tag else "", previous=previous.name if previous else "", reason=reason
            )
        elif args.command == "docs-source":
            tag, ref = docs_source(repo, args.head, args.tag)
            _emit(tag=tag.name, ref=ref, follows_head=str(ref != tag.name).lower())
        elif args.command == "package":
            tag = Tag.parse(args.tag)
            if tag is None:
                raise Refuse(f"{args.tag} is not a release tag")
            print(repo.package(tag, REPO_ROOT / DIST).relative_to(REPO_ROOT))
        else:
            if args.command == "cut-beta":
                tag = cut_beta(repo, args.source)
            elif args.command == "patch":
                tag = patch(repo, args.source)
            else:
                tag = promote(repo, datetime.now(timezone.utc), force=args.force)
            repo.package(tag, REPO_ROOT / DIST)
            _emit(tag=tag.name, previous=_notes_start_name(repo, tag), prerelease=str(not tag.stable).lower())
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
