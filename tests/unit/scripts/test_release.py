"""scripts/release.py: when a beta is cut or promoted, and what version
lands in the zip. The decisions are tested on plain values; tagging and
packaging are tested against a real throwaway git repository."""

import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.flare.blueprint_version import version_from_description
from tests.support import REPO_ROOT, load_script

release = load_script("release")
Refuse, Repo, Skip, Tag = release.Refuse, release.Repo, release.Skip, release.Tag

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def tags(*names: str) -> list[Tag]:
    return [Tag.parse(n) for n in names]


def aged(**days: int) -> dict[str, datetime]:
    """{'v0.0.1-beta.4': 8} -> that tag, made 8 days before NOW."""
    return {_tag_name(k): NOW - timedelta(days=d) for k, d in days.items()}


def _tag_name(key: str) -> str:
    """v0_16_0_beta_1 -> v0.16.0-beta.1 (a kwarg cannot be spelled with dots)."""
    return re.sub(r"^v(\d+)_(\d+)_(\d+)_beta_(\d+)$", r"v\1.\2.\3-beta.\4", key)


# --- Tags --------------------------------------------------------------


def test_only_our_own_tags_are_release_tags():
    assert Tag.parse("v0.16.0").stable
    assert not Tag.parse("v0.16.0-beta.3").stable
    for other in ("latest", "v0.16", "v1.0.0-rc.1", "0.16.0", "v0.16.0-beta"):
        assert Tag.parse(other) is None, other


def test_a_beta_sorts_below_its_release_and_betas_sort_numerically():
    """beta.10 above beta.9 is the one a string sort gets wrong, and it is
    the difference between the newest beta and a stale one."""
    order = sorted(tags("v0.16.0", "v0.16.0-beta.10", "v0.16.0-beta.9", "v0.15.9"))

    assert [t.name for t in order] == ["v0.15.9", "v0.16.0-beta.9", "v0.16.0-beta.10", "v0.16.0"]


def test_the_changelogs_top_section_names_the_target():
    text = "# Changelog\n\n## [0.17.0] - Unreleased\n\n## [0.16.0] - 2026-09-20\n"

    assert release.changelog_base(text) == "0.17.0"
    assert release.changelog_base("# Changelog\n\nnothing yet") is None


# --- Release notes -----------------------------------------------------


def test_a_first_beta_s_notes_count_from_the_last_release():
    """v0.16.0-beta.2 sorts above v0.16.0 by git's default version sort,
    which is the one that gets this wrong."""
    known = tags("v0.15.0", "v0.16.0-beta.1", "v0.16.0-beta.2", "v0.16.0", "v0.17.0-beta.1")

    assert release.notes_start(Tag.parse("v0.17.0-beta.1"), known).name == "v0.16.0"


def test_a_later_beta_s_notes_count_from_the_beta_before_it():
    known = tags("v0.16.0", "v0.17.0-beta.1", "v0.17.0-beta.2")

    assert release.notes_start(Tag.parse("v0.17.0-beta.2"), known).name == "v0.17.0-beta.1"


def test_a_release_s_notes_count_from_the_release_before_it_not_its_betas():
    known = tags("v0.16.0", "v0.17.0-beta.1", "v0.17.0-beta.2", "v0.17.0")

    assert release.notes_start(Tag.parse("v0.17.0"), known).name == "v0.16.0"


def test_the_first_tag_s_notes_count_from_nothing():
    assert release.notes_start(Tag.parse("v0.1.0-beta.1"), tags("v0.1.0-beta.1")) is None


# --- Cutting a beta ----------------------------------------------------


def test_the_first_beta_of_a_version_is_beta_one():
    assert release.next_beta("0.17.0", tags("v0.16.0")).name == "v0.17.0-beta.1"


def test_a_later_beta_continues_the_count():
    got = release.next_beta("0.17.0", tags("v0.16.0", "v0.17.0-beta.1", "v0.17.0-beta.2"))

    assert got.name == "v0.17.0-beta.3"


def test_a_released_version_has_no_more_betas():
    """A merge whose changelog still says the version that just shipped is
    a docs or test change, not a new release - it must not go red, and it
    must not invent a beta of something already stable."""
    with pytest.raises(Skip):
        release.next_beta("0.16.0", tags("v0.16.0", "v0.16.0-beta.9"))


def test_a_beta_below_an_existing_one_is_refused():
    """HACS orders by version, so this would reach testers as a downgrade.
    Loud, because it means a changelog heading was mistyped."""
    with pytest.raises(Refuse):
        release.next_beta("0.16.5", tags("v0.16.0", "v0.17.0-beta.1"))


# --- Promoting ---------------------------------------------------------


def test_a_beta_that_has_sat_a_week_is_promoted():
    got = release.pick_promotion(
        tags("v0.15.0", "v0.16.0-beta.1", "v0.16.0-beta.2"),
        aged(v0_16_0_beta_1=20, v0_16_0_beta_2=7),
        NOW,
    )

    assert got.name == "v0.16.0-beta.2"


def test_a_beta_a_minute_short_of_a_week_is_not():
    with pytest.raises(Skip):
        release.pick_promotion(
            tags("v0.15.0", "v0.16.0-beta.1"),
            {"v0.16.0-beta.1": NOW - timedelta(days=7) + timedelta(minutes=1)},
            NOW,
        )


def test_a_newer_beta_of_the_same_version_restarts_its_clock():
    """What gets promoted is the newest beta's contents, so an old beta
    having soaked says nothing about a fix landed since."""
    with pytest.raises(Skip):
        release.pick_promotion(
            tags("v0.15.0", "v0.16.0-beta.3", "v0.16.0-beta.4"),
            aged(v0_16_0_beta_3=30, v0_16_0_beta_4=5),
            NOW,
        )


def test_a_newer_version_does_not_hold_back_an_older_one_that_has_soaked():
    """The rule as it was asked for: 0.0.1-beta.4 is 7 days old, ship it;
    0.0.2-beta.1 is 5 days old, don't."""
    got = release.pick_promotion(
        tags("v0.0.0", "v0.0.1-beta.4", "v0.0.2-beta.1"),
        aged(v0_0_1_beta_4=7, v0_0_2_beta_1=5),
        NOW,
    )

    assert got.name == "v0.0.1-beta.4"


def test_when_several_versions_have_soaked_the_highest_wins():
    got = release.pick_promotion(
        tags("v0.0.0", "v0.0.1-beta.4", "v0.0.2-beta.1"),
        aged(v0_0_1_beta_4=20, v0_0_2_beta_1=9),
        NOW,
    )

    assert got.name == "v0.0.2-beta.1"


def test_a_version_below_the_latest_release_is_never_promoted():
    """Tags pushed in an odd order must not be able to ship a downgrade:
    0.0.3 is out, so a soaked 0.0.1 beta is superseded, not pending."""
    with pytest.raises(Skip):
        release.pick_promotion(
            tags("v0.0.3", "v0.0.1-beta.4"),
            aged(v0_0_1_beta_4=30),
            NOW,
        )


def test_nothing_to_promote_is_not_an_error():
    with pytest.raises(Skip):
        release.pick_promotion(tags("v0.16.0"), {}, NOW)


def test_force_ignores_the_soak_period():
    got = release.pick_promotion(
        tags("v0.15.0", "v0.16.0-beta.1"), aged(v0_16_0_beta_1=0), NOW, force=True
    )

    assert got.name == "v0.16.0-beta.1"


BLUEPRINT_A = "description: >\n  Blueprint version {stamp} - and text\ninput:\n  a: 1\n"


def bp(template: str, stamp: str) -> str:
    return template.format(stamp=stamp)


# --- Writing a version into a tree -------------------------------------

MANIFEST_JSON = '{\n  "domain": "flare",\n  "version": "0.0.0-dev"\n}\n'
STAMP_PY = 'import re\n\nBLUEPRINT_VERSION = "0.0.0-dev"\n\nOTHER = "0.0.0-dev"\n'


def write_tree(root: Path, *, blueprint: str = BLUEPRINT_A, changelog: str = "") -> None:
    (root / release.BLUEPRINT).parent.mkdir(parents=True, exist_ok=True)
    (root / release.MANIFEST).write_text(MANIFEST_JSON)
    (root / release.BLUEPRINT_VERSION_PY).write_text(STAMP_PY)
    (root / release.BLUEPRINT).write_text(bp(blueprint, "0.0.0-dev"))
    (root / release.CHANGELOG).write_text(changelog or "# Changelog\n\n## [0.17.0] - Unreleased\n")


def test_all_three_places_are_written(tmp_path):
    write_tree(tmp_path)

    release.stamp_tree(tmp_path, "0.17.0-beta.1")

    assert json.loads((tmp_path / release.MANIFEST).read_text())["version"] == "0.17.0-beta.1"
    assert 'BLUEPRINT_VERSION = "0.17.0-beta.1"' in (tmp_path / release.BLUEPRINT_VERSION_PY).read_text()
    written = (tmp_path / release.BLUEPRINT).read_text()
    # Read back through the integration's own parser, not this script's:
    # that is what an installed copy is judged by.
    assert version_from_description(written) == "0.17.0-beta.1"


def test_only_the_constant_is_rewritten_not_lookalikes(tmp_path):
    write_tree(tmp_path)

    release.stamp_tree(tmp_path, "0.17.0")

    assert 'OTHER = "0.0.0-dev"' in (tmp_path / release.BLUEPRINT_VERSION_PY).read_text()


def test_a_file_that_lost_its_stamp_fails_loudly_rather_than_shipping_unstamped(tmp_path):
    write_tree(tmp_path)
    (tmp_path / release.BLUEPRINT).write_text("description: nothing here\n")

    with pytest.raises(Refuse):
        release.stamp_tree(tmp_path, "0.17.0")


# --- Against real git --------------------------------------------------


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "test")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")


class Project:
    """A throwaway repository shaped like this one."""

    def __init__(self, root: Path):
        self.root = root
        self.repo = Repo(root)
        self.repo.git("init", "-q", "-b", "dev")
        self.repo.git("config", "commit.gpgsign", "false")
        write_tree(root, changelog="# Changelog\n\n## [0.16.0]\n")
        self.commit("start")

    def commit(self, message: str) -> str:
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--allow-empty", "-m", message)
        return self.repo.out("rev-parse", "HEAD")

    def edit(self, path: str, text: str, message: str) -> str:
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        return self.commit(message)

    def target(self, version: str) -> None:
        (self.root / release.CHANGELOG).write_text(f"# Changelog\n\n## [{version}]\n")

    def at(self, tag: str, path: str) -> str:
        """A file as the tag's zip carries it."""
        zipped = self.repo.package(Tag.parse(tag), self.root / ".git" / "dist")
        with zipfile.ZipFile(zipped) as files:
            return files.read(Path(path).relative_to(release.COMPONENT).as_posix()).decode()


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path)


def test_a_beta_tags_its_source_and_leaves_the_checkout_alone(project):
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, source)

    assert project.repo.out("rev-parse", f"{beta.name}^{{commit}}") == source
    assert project.repo.out("cat-file", "-t", beta.name) == "tag", "not annotated, so not dated"
    assert project.repo.out("rev-parse", "HEAD") == source, "the checkout moved"
    assert project.repo.out("status", "--porcelain") == "", "the checkout was dirtied"
    assert json.loads(project.at(beta.name, release.MANIFEST))["version"] == "0.17.0-beta.1"


def test_the_zip_is_the_integration_s_folder_with_its_files_at_the_root(project):
    project.edit("custom_components/flare/www/card.js", "card", "a card")
    project.edit("docs/page.md", "hello", "docs")
    project.target("0.17.0")
    beta = release.cut_beta(project.repo, project.commit("target 0.17.0"))

    with zipfile.ZipFile(project.repo.package(beta, project.root / ".git" / "dist")) as files:
        names = sorted(files.namelist())

    assert names == ["blueprint_version.py", "blueprints/flare.yaml", "manifest.json", "www/card.js"]


def test_source_keeps_its_placeholders(project):
    project.target("0.17.0")
    beta = release.cut_beta(project.repo, project.commit("target 0.17.0"))

    assert json.loads(project.repo.out("show", f"{beta.name}:{release.MANIFEST}"))["version"] == "0.0.0-dev"


def test_an_older_release_commit_is_read_back_to_its_source(project):
    """Releases from before the zip are a commit on their source."""
    source = project.repo.out("rev-parse", "HEAD")
    project.repo.git("commit", "-q", "--allow-empty", "-m", f"Release v0.16.0\n\nSource: {source}\n")
    project.repo.git("tag", "v0.16.0")

    assert project.repo.source_of(Tag.parse("v0.16.0")) == source


def test_a_beta_records_what_it_was_built_from(project):
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, source)

    assert project.repo.source_of(beta) == source


def test_the_source_is_recorded_as_a_full_sha_whatever_was_passed(project):
    """A short ref like HEAD must be recorded as its full SHA, or a promotion
    can't rebuild from it."""
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, "HEAD")

    assert project.repo.source_of(beta) == source


def test_a_push_that_changes_nothing_shipped_cuts_no_beta(project):
    project.target("0.17.0")
    first = project.commit("target 0.17.0")
    release.cut_beta(project.repo, first)

    docs = project.edit("docs/page.md", "hello", "docs only")

    with pytest.raises(Skip):
        release.cut_beta(project.repo, docs)
    with pytest.raises(Skip):
        release.cut_beta(project.repo, first)  # and re-running is a no-op


def released(project: Project, version: str) -> None:
    project.target(version)
    project.repo.build(Tag.parse(f"v{version}"), project.commit(version))


def test_a_shipped_change_under_a_released_version_is_refused(project):
    released(project, "0.17.0")
    change = project.edit("custom_components/flare/x.py", "y = 2", "python change")

    with pytest.raises(Refuse, match=r"\[0\.17\.0\], which is already released"):
        release.check(project.repo, change)
    with pytest.raises(Refuse):
        release.cut_beta(project.repo, change)


def test_a_docs_change_under_a_released_version_is_not_refused(project):
    released(project, "0.17.0")
    docs = project.edit("docs/page.md", "hello", "docs only")

    with pytest.raises(Skip):
        release.check(project.repo, docs)


def test_a_shipped_change_under_a_new_section_passes(project):
    released(project, "0.17.0")
    project.edit("custom_components/flare/x.py", "y = 2", "python change")
    project.target("0.18.0")

    _, _, beta = release.check(project.repo, project.commit("target 0.18.0"))

    assert beta.name == "v0.18.0-beta.1"


def test_check_fails_the_command_for_a_shipped_change_under_a_released_version(project, capsys, monkeypatch):
    released(project, "0.17.0")
    change = project.edit("custom_components/flare/x.py", "y = 2", "python change")
    monkeypatch.setattr(release, "REPO_ROOT", project.root)

    assert release.main(["check", "--source", change]) == 1
    assert "::error::" in capsys.readouterr().out


def test_a_release_s_docs_follow_main_while_nothing_shipped_has_changed(project):
    released(project, "0.17.0")
    docs = project.edit("docs/page.md", "fixed", "docs fix")

    assert release.docs_source(project.repo, docs) == (Tag.parse("v0.17.0"), docs)


def test_a_release_s_docs_stay_on_the_tag_once_shipped_code_moves_on(project):
    released(project, "0.17.0")
    change = project.edit("custom_components/flare/x.py", "y = 2", "python change")

    assert release.docs_source(project.repo, change, "v0.17.0") == (Tag.parse("v0.17.0"), "v0.17.0")


def test_docs_source_needs_a_release(project):
    with pytest.raises(Skip):
        release.docs_source(project.repo, "HEAD")
    with pytest.raises(Refuse):
        release.docs_source(project.repo, "HEAD", "v0.17.0-beta.1")


def test_every_beta_stamps_the_blueprint_with_its_own_version(project):
    """The blueprint's stamp is each release's own version."""
    project.target("0.17.0")
    first = project.commit("target 0.17.0")
    beta_1 = release.cut_beta(project.repo, first)

    second = project.edit("custom_components/flare/x.py", "print(1)", "python change")
    beta_2 = release.cut_beta(project.repo, second)

    assert beta_2.name == "v0.17.0-beta.2"
    for beta in (beta_1, beta_2):
        assert version_from_description(project.at(beta.name, release.BLUEPRINT)) == beta.version
        assert f'BLUEPRINT_VERSION = "{beta.version}"' in project.at(
            beta.name, release.BLUEPRINT_VERSION_PY
        )


def test_promotion_rebuilds_the_betas_own_source_as_the_bare_version(project):
    project.target("0.17.0")
    source = project.commit("target 0.17.0")
    beta = release.cut_beta(project.repo, source)
    # Main moves on after the beta; the release must NOT pick that up.
    project.edit("custom_components/flare/later.py", "x = 1", "unsoaked change")

    # The beta is cut now, by the real clock, so its soak is too.
    stable = release.promote(project.repo, datetime.now(timezone.utc) + timedelta(days=8))

    assert stable.name == "v0.17.0"
    assert project.repo.source_of(stable) == source
    assert json.loads(project.at("v0.17.0", release.MANIFEST))["version"] == "0.17.0"
    assert project.repo.out("ls-tree", "-r", "--name-only", "v0.17.0").count("later.py") == 0
    assert version_from_description(project.at("v0.17.0", release.BLUEPRINT)) == "0.17.0"
    assert 'BLUEPRINT_VERSION = "0.17.0"' in project.at("v0.17.0", release.BLUEPRINT_VERSION_PY)
    assert beta.name == "v0.17.0-beta.1"


def test_promotion_waits_for_the_soak_period(project):
    project.target("0.17.0")
    release.cut_beta(project.repo, project.commit("target 0.17.0"))

    with pytest.raises(Skip):
        release.promote(project.repo, datetime.now(timezone.utc) + timedelta(days=6))


def test_a_release_stamps_the_blueprint_even_if_it_never_changed(project):
    """Even when the blueprint didn't change."""
    project.target("0.16.0")
    project.repo.build(Tag.parse("v0.16.0"), project.commit("0.16.0"))

    project.target("0.17.0")
    source = project.edit("custom_components/flare/x.py", "y = 2", "python only")
    release.cut_beta(project.repo, source)
    stable = release.promote(project.repo, datetime.now(timezone.utc) + timedelta(days=8))

    assert version_from_description(project.at(stable.name, release.BLUEPRINT)) == "0.17.0"


def test_a_hand_made_beta_is_promoted_from_its_own_commit(project):
    sha = project.repo.out("rev-parse", "HEAD")
    project.repo.git("tag", "v0.17.0-beta.1", sha)

    stable = release.promote(project.repo, datetime.now(timezone.utc) + timedelta(days=8))

    assert project.repo.source_of(stable) == sha


def test_a_preview_names_the_beta_and_where_its_notes_start(project):
    released(project, "0.16.0")
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta, previous, reason = release.preview(project.repo, source)

    assert (beta.name, previous.name, reason) == ("v0.17.0-beta.1", "v0.16.0", "")
    assert project.repo.out("tag", "--list", "v0.17.0*") == "", "a preview built a release"


def test_a_preview_of_nothing_shipped_says_why(project):
    project.target("0.17.0")
    release.cut_beta(project.repo, project.commit("target 0.17.0"))

    beta, previous, reason = release.preview(project.repo, project.edit("docs/page.md", "hello", "docs only"))

    assert (beta, previous) == (None, None)
    assert "nothing under custom_components has changed since v0.17.0-beta.1" in reason


def test_a_preview_of_a_refused_change_says_why_without_failing(project):
    """The changelog job fails the pull request; the preview only explains."""
    released(project, "0.17.0")

    beta, _, reason = release.preview(project.repo, project.edit("custom_components/flare/x.py", "y = 2", "change"))

    assert beta is None
    assert "already released" in reason


def test_the_command_line_hands_the_workflow_a_tag_or_nothing(project, monkeypatch, capsys, tmp_path):
    """The workflows read `tag=`: a skip exits 0 with it empty."""
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    assert release.main(["cut-beta", "--source", source]) == 0
    assert output.read_text().splitlines() == ["tag=v0.17.0-beta.1", "previous=", "prerelease=true"]
    assert (project.root / release.DIST / release.ZIP).exists(), "nothing for the workflow to attach"

    output.write_text("")
    assert release.main(["cut-beta", "--source", source]) == 0  # nothing new: a skip
    assert output.read_text().splitlines() == ["tag="]

    project.target("0.16.5")  # a downgrade: somebody needs to look
    assert release.main(["cut-beta", "--source", project.commit("oops")]) == 1
    assert "::error::" in capsys.readouterr().out


# --- Patches -----------------------------------------------------------


def patch_branch(project: Project, version: str) -> str:
    """A branch from the current release's source, with a fix and a section for it."""
    current = max(t for t in project.repo.tags()[0] if t.stable)
    project.repo.git("switch", "-q", "-c", "patch", project.repo.source_of(current))
    project.edit("custom_components/flare/fix.py", "fixed = True", "the fix")
    project.target(version)
    return project.commit(f"target {version}")


def test_a_patch_ships_the_branch_as_the_next_patch_release(project):
    released(project, "0.17.0")
    project.target("0.18.0")
    project.edit("custom_components/flare/later.py", "x = 1", "in beta on main")
    source = patch_branch(project, "0.17.1")

    tag = release.patch(project.repo, source)

    assert tag.name == "v0.17.1"
    assert project.repo.source_of(tag) == source
    assert json.loads(project.at("v0.17.1", release.MANIFEST))["version"] == "0.17.1"
    assert version_from_description(project.at("v0.17.1", release.BLUEPRINT)) == "0.17.1"
    files = project.repo.out("ls-tree", "-r", "--name-only", "v0.17.1")
    assert "custom_components/flare/fix.py" in files
    assert "later.py" not in files


def test_a_patch_from_a_commit_not_built_on_the_release_is_refused(project):
    first = project.repo.out("rev-parse", "HEAD")
    released(project, "0.17.0")
    project.repo.git("switch", "-q", "-c", "patch", first)
    project.edit("custom_components/flare/fix.py", "fixed = True", "the fix")
    project.target("0.17.1")

    with pytest.raises(Refuse, match="not built on v0.17.0"):
        release.patch(project.repo, project.commit("target 0.17.1"))


def test_main_with_work_in_beta_is_not_a_patch(project):
    released(project, "0.17.0")
    project.target("0.18.0")
    source = project.edit("custom_components/flare/later.py", "x = 1", "in beta on main")

    with pytest.raises(Refuse, match=r"is v0\.17\.1"):
        release.patch(project.repo, source)


def test_a_patch_must_be_the_next_patch_of_the_current_release(project):
    released(project, "0.17.0")

    for version in ("0.18.0", "0.17.2", "0.17.0"):
        project.repo.git("switch", "-q", "dev")
        project.repo.git("branch", "-q", "-D", "patch", check=False)
        with pytest.raises(Refuse, match=r"is v0\.17\.1"):
            release.patch(project.repo, patch_branch(project, version))
    assert Tag.parse("v0.17.1") not in project.repo.tags()[0]


def test_a_patch_with_nothing_shipped_changed_is_skipped(project):
    released(project, "0.17.0")
    project.repo.git("switch", "-q", "-c", "patch", project.repo.source_of(Tag.parse("v0.17.0")))
    project.target("0.17.1")
    source = project.edit("docs/page.md", "hello", "docs only")

    with pytest.raises(Skip):
        release.patch(project.repo, source)


def test_a_docs_change_on_a_release_branch_needs_no_changelog_section(project):
    released(project, "0.17.0")
    project.repo.git("switch", "-q", "-c", "patch", project.repo.source_of(Tag.parse("v0.17.0")))
    source = project.edit("docs/page.md", "hello", "docs only")

    with pytest.raises(Skip):
        release.patch(project.repo, source)


def test_a_pull_request_into_a_release_branch_is_checked_as_a_patch(project, monkeypatch, capsys):
    """Judged as a beta, a patch below main's betas reads as a downgrade."""
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    released(project, "0.17.0")
    project.target("0.18.0")
    release.cut_beta(project.repo, project.edit("custom_components/flare/later.py", "x = 1", "beta"))
    source = patch_branch(project, "0.17.1")

    assert release.main(["check", "--source", source]) == 1
    capsys.readouterr()
    assert release.main(["check", "--source", source, "--patch"]) == 0
    assert "v0.17.1" in capsys.readouterr().out


def test_a_preview_of_a_patch_names_it_and_counts_its_notes_from_the_release(project):
    released(project, "0.17.0")
    source = patch_branch(project, "0.17.1")

    tag, previous, reason = release.preview(project.repo, source, for_patch=True)

    assert (tag.name, previous.name, reason) == ("v0.17.1", "v0.17.0", "")


def test_there_is_nothing_to_patch_before_a_release(project):
    project.target("0.16.1")

    with pytest.raises(Refuse, match="no release"):
        release.patch(project.repo, project.commit("target 0.16.1"))


def test_main_still_cuts_its_betas_after_a_patch(project):
    released(project, "0.17.0")
    patch_source = patch_branch(project, "0.17.1")
    release.patch(project.repo, patch_source)
    project.repo.git("switch", "-q", "dev")
    project.target("0.18.0")
    source = project.edit("custom_components/flare/fix.py", "fixed = True", "the fix, on main")

    assert release.cut_beta(project.repo, source).name == "v0.18.0-beta.1"


def test_the_command_line_hands_the_workflow_a_patch_and_its_previous_release(
    project, monkeypatch, tmp_path
):
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    released(project, "0.17.0")
    source = patch_branch(project, "0.17.1")

    assert release.main(["patch", "--source", source]) == 0
    assert output.read_text().splitlines() == ["tag=v0.17.1", "previous=v0.17.0", "prerelease=false"]
    assert (project.root / release.DIST / release.ZIP).exists()


def test_a_tag_pushed_by_hand_is_packaged_with_its_own_version(project, monkeypatch):
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    project.repo.git("tag", "v0.16.0")

    assert release.main(["package", "--tag", "v0.16.0"]) == 0
    with zipfile.ZipFile(project.root / release.DIST / release.ZIP) as files:
        assert json.loads(files.read("manifest.json"))["version"] == "0.16.0"



# --- Release notes -----------------------------------------------------

CHANGELOG_TEXT = """# Changelog

Intro.

## [0.17.0] - Unreleased

Opening paragraph that was wrapped
at a hundred columns.

### Updating

1. Update FLARE in HACS and
   restart Home Assistant.
2. Open **Repairs** and submit
   it.

- **A bullet** wrapped over
  two lines.
  - A nested bullet, also
    wrapped.

## [0.16.0] - 2026-09-20

- Older.
"""


def test_a_version_s_section_is_its_body_without_the_heading_up_to_the_next():
    section = release.changelog_section(CHANGELOG_TEXT, "0.17.0")

    assert section.startswith("Opening paragraph")
    assert section.endswith("    wrapped.")
    assert release.changelog_section(CHANGELOG_TEXT, "0.16.0") == "- Older."
    assert release.changelog_section(CHANGELOG_TEXT, "0.1.0") is None


def test_a_version_s_section_is_not_a_longer_version_s():
    text = "## [1.0.10]\n\nten\n\n## [1.0.1]\n\none\n"

    assert release.changelog_section(text, "1.0.1") == "one"


def test_paragraphs_numbered_items_and_nested_bullets_each_become_one_line():
    unwrapped = release.unwrap(release.changelog_section(CHANGELOG_TEXT, "0.17.0"))

    assert unwrapped.splitlines() == [
        "Opening paragraph that was wrapped at a hundred columns.",
        "",
        "### Updating",
        "",
        "1. Update FLARE in HACS and restart Home Assistant.",
        "2. Open **Repairs** and submit it.",
        "",
        "- **A bullet** wrapped over two lines.",
        "  - A nested bullet, also wrapped.",
    ]


def test_a_heading_is_never_joined_onto_or_continued():
    assert release.unwrap("### Fixed\n- one\n## Next\ntext") == "### Fixed\n- one\n## Next\ntext"


def test_a_code_span_wrapped_across_lines_is_joined_with_a_space():
    text = "- A template reading\n  `state_attr('sensor.home_flare', 'color_temp')` needs\n  changing."

    assert release.unwrap(text) == (
        "- A template reading `state_attr('sensor.home_flare', 'color_temp')` needs changing."
    )


def test_fenced_code_and_hard_breaks_are_kept_as_written():
    text = (
        "- Update its type:\n"
        "\n"
        "  ```yaml\n"
        "  views:\n"
        "    - title: Lighting\n"
        "      strategy:\n"
        "        type: custom:flare-schedule\n"
        "  ```\n"
        "\n"
        "  Then it\n"
        "  loads.\n"
        "\n"
        "Line one  \n"
        "line two\\\n"
        "line three\n"
        "| a | b |\n"
        "| 1 | 2 |"
    )

    assert release.unwrap(text).splitlines() == [
        "- Update its type:",
        "",
        "  ```yaml",
        "  views:",
        "    - title: Lighting",
        "      strategy:",
        "        type: custom:flare-schedule",
        "  ```",
        "",
        "  Then it loads.",
        "",
        "Line one",
        "line two\\",
        "line three",
        "| a | b |",
        "| 1 | 2 |",
    ]


def _words_outside_fences(text: str) -> list[str]:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL).split()


def test_every_released_section_unwraps_without_losing_or_moving_a_word():
    """The real changelog: no line outside a fence is left as a bare
    continuation, and the words are the same words in the same order."""
    text = (REPO_ROOT / release.CHANGELOG).read_text()
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert "2.0.0" in versions

    for version in versions:
        section = release.changelog_section(text, version)
        unwrapped = release.unwrap(section)
        assert _words_outside_fences(unwrapped) == _words_outside_fences(section), version
        in_fence = False
        for before, line in zip([""] + unwrapped.splitlines(), unwrapped.splitlines()):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line.strip() or not before.strip() or before.strip().startswith("```"):
                continue
            assert release._BLOCK_START.match(line), f"{version}: {line!r} still continues {before!r}"


def test_the_2_0_section_keeps_its_upgrade_steps_and_code_spans_whole():
    notes = release.release_notes(
        (REPO_ROOT / release.CHANGELOG).read_text(),
        Tag.parse("v2.0.0"),
        Tag.parse("v1.2.1"),
        "https://github.com/danrspencer/flare",
    )
    lines = notes.splitlines()

    assert "### Updating from 1.x" in lines
    step = next(line for line in lines if line.startswith("2. "))
    assert "**FLARE blueprint is out of date**" in step and "switch off when a room empties." in step
    assert any(
        "`state_attr('sensor.home_flare', 'color_temp')` needs changing to `'color_temp_kelvin'`" in line
        for line in lines
    )
    assert lines[-1] == "**Full Changelog**: https://github.com/danrspencer/flare/compare/v1.2.1...v2.0.0"


def test_notes_end_with_a_compare_link_from_where_they_start():
    url = "https://github.com/o/r"
    beta = Tag.parse("v0.17.0-beta.2")

    notes = release.release_notes(CHANGELOG_TEXT, beta, Tag.parse("v0.17.0-beta.1"), url)
    assert notes.endswith("\n\n**Full Changelog**: https://github.com/o/r/compare/v0.17.0-beta.1...v0.17.0-beta.2\n")
    assert release.release_notes(CHANGELOG_TEXT, beta, None, url).endswith("/o/r/commits/v0.17.0-beta.2\n")
    assert "Full Changelog" not in release.release_notes(CHANGELOG_TEXT, beta, None, url, compare=False)


def test_a_release_without_a_changelog_section_is_refused():
    with pytest.raises(Refuse, match=r"no '## \[0.18.0\]' section"):
        release.release_notes(CHANGELOG_TEXT, Tag.parse("v0.18.0"), None, "https://github.com/o/r")


def test_a_release_s_notes_are_read_at_its_source_not_the_checkout(project):
    released(project, "0.16.0")
    project.edit(release.CHANGELOG, "# Changelog\n\n## [0.17.0]\n\nThe beta's\nnotes.\n", "target 0.17.0")
    beta = release.cut_beta(project.repo, project.edit(f"{release.COMPONENT}/x.py", "x", "change"))
    project.edit(release.CHANGELOG, "# Changelog\n\n## [0.17.0]\n\nRewritten later.\n", "later")

    notes = release.notes(project.repo, beta, "https://github.com/o/r")

    assert notes == "The beta's notes.\n\n**Full Changelog**: https://github.com/o/r/compare/v0.16.0...v0.17.0-beta.1\n"
    preview = release.notes(project.repo, Tag.parse("v0.17.0-beta.2"), "u", source="HEAD", compare=False)
    assert preview == "Rewritten later.\n"


def test_the_notes_command_prints_the_body_for_gh(project, monkeypatch, capsys):
    released(project, "0.16.0")
    project.edit(release.CHANGELOG, "# Changelog\n\n## [0.17.0]\n\nNew.\n", "target 0.17.0")
    release.cut_beta(project.repo, project.edit(f"{release.COMPONENT}/x.py", "x", "change"))
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)

    assert release.main(["notes", "--tag", "v0.17.0-beta.1"]) == 0
    assert capsys.readouterr().out == "New.\n\n**Full Changelog**: https://github.com/o/r/compare/v0.16.0...v0.17.0-beta.1\n"


# --- The wiring --------------------------------------------------------


def test_the_workflows_call_the_script_the_same_way_these_tests_do():
    """The workflows' subcommands and flags exist."""
    cut = (REPO_ROOT / ".github" / "workflows" / "cut-beta.yml").read_text()
    promote = (REPO_ROOT / ".github" / "workflows" / "promote.yml").read_text()

    assert "scripts/release.py cut-beta --source" in cut
    assert "scripts/release.py promote" in promote
    preview = (REPO_ROOT / ".github" / "workflows" / "release-preview.yml").read_text()
    assert "scripts/release.py preview --source" in preview
    patch = (REPO_ROOT / ".github" / "workflows" / "patch-release.yml").read_text()
    assert 'scripts/release.py patch --source "$GITHUB_SHA"' in patch
    assert 'branches: ["release/**"]' in patch, "a push to a release branch patches"
    tests = (REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text()
    assert "release/*) python scripts/release.py check --source HEAD --patch" in tests
    assert "release/*) python scripts/release.py preview --source HEAD --patch" in preview
    assert "steps.cut.outputs.previous" in cut, "a beta's pull request list counts from its notes_start"
    for workflow in (cut, promote, patch):
        assert f"{release.DIST}/{release.ZIP}" in workflow, "the release has no zip for HACS"
        assert 'scripts/release.py notes --tag "$TAG"' in workflow
        assert "--notes-file notes.md" in workflow, "the release's notes aren't its changelog section"
    assert "scripts/release.py notes --tag \"$TAG\" --source HEAD" in preview


def test_hacs_installs_the_zip_the_script_builds():
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text())

    assert hacs["zip_release"] is True
    assert hacs["filename"] == release.ZIP
