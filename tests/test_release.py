"""
The release script: what decides when a beta is cut, when it is promoted,
and what number ends up written into the files a house receives.

Two layers, because they fail differently. The decisions (which beta,
whether it has soaked, whether this would be a downgrade) are pure and
tested on plain values. The building (a commit nothing points at, the
source it records, the working checkout left alone) is git, and is tested
against a real throwaway repository - a mock of git would only prove the
script agrees with itself.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "flare"))

import release  # noqa: E402
from blueprint_version import version_from_description  # noqa: E402
from release import Refuse, Repo, Skip, Tag  # noqa: E402

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


# --- The blueprint stamp -----------------------------------------------

BLUEPRINT_A = "description: >\n  Blueprint version {stamp} - and text\ninput:\n  a: 1\n"
BLUEPRINT_B = "description: >\n  Blueprint version {stamp} - and text\ninput:\n  a: 2\n"


def bp(template: str, stamp: str) -> str:
    return template.format(stamp=stamp)


def test_a_first_release_stamps_itself():
    assert release.blueprint_stamp(bp(BLUEPRINT_A, "0.0.0-dev"), None, "0.17.0") == "0.17.0"


def test_an_unchanged_blueprint_keeps_the_previous_releases_stamp():
    """A release that only touched Python must not tell everyone to
    re-import an identical file. The previous copy wears its own stamp,
    so the comparison has to ignore it."""
    got = release.blueprint_stamp(
        bp(BLUEPRINT_A, "0.0.0-dev"), bp(BLUEPRINT_A, "0.16.0"), "0.17.0"
    )

    assert got == "0.16.0"


def test_a_changed_blueprint_stamps_the_new_version():
    got = release.blueprint_stamp(
        bp(BLUEPRINT_B, "0.0.0-dev"), bp(BLUEPRINT_A, "0.16.0"), "0.17.0-beta.1"
    )

    assert got == "0.17.0-beta.1"


# --- Writing a version into a tree -------------------------------------

MANIFEST_JSON = '{\n  "domain": "flare",\n  "version": "0.0.0-dev"\n}\n'
STAMP_PY = 'import re\n\nBLUEPRINT_VERSION = "0.0.0-dev"\n\nOTHER = "0.0.0-dev"\n'


def write_tree(root: Path, *, blueprint: str = BLUEPRINT_A, changelog: str = "") -> None:
    (root / "custom_components" / "flare").mkdir(parents=True, exist_ok=True)
    (root / "blueprints" / "automation" / "danspencer").mkdir(parents=True, exist_ok=True)
    (root / release.MANIFEST).write_text(MANIFEST_JSON)
    (root / release.BLUEPRINT_VERSION_PY).write_text(STAMP_PY)
    (root / release.BLUEPRINT).write_text(bp(blueprint, "0.0.0-dev"))
    (root / release.CHANGELOG).write_text(changelog or "# Changelog\n\n## [0.17.0] - Unreleased\n")


def test_all_three_places_are_written(tmp_path):
    write_tree(tmp_path)

    release.stamp_tree(tmp_path, "0.17.0-beta.1", "0.16.0")

    assert json.loads((tmp_path / release.MANIFEST).read_text())["version"] == "0.17.0-beta.1"
    assert 'BLUEPRINT_VERSION = "0.16.0"' in (tmp_path / release.BLUEPRINT_VERSION_PY).read_text()
    written = (tmp_path / release.BLUEPRINT).read_text()
    # Read back through the integration's own parser, not this script's:
    # that is what an installed copy is judged by.
    assert version_from_description(written) == "0.16.0"


def test_only_the_constant_is_rewritten_not_lookalikes(tmp_path):
    write_tree(tmp_path)

    release.stamp_tree(tmp_path, "0.17.0", "0.17.0")

    assert 'OTHER = "0.0.0-dev"' in (tmp_path / release.BLUEPRINT_VERSION_PY).read_text()


def test_a_file_that_lost_its_stamp_fails_loudly_rather_than_shipping_unstamped(tmp_path):
    write_tree(tmp_path)
    (tmp_path / release.BLUEPRINT).write_text("description: nothing here\n")

    with pytest.raises(Refuse):
        release.stamp_tree(tmp_path, "0.17.0", "0.17.0")


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
        return self.repo.out("show", f"{tag}:{path}")


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path)


def test_the_release_commit_is_on_no_branch_and_leaves_the_checkout_alone(project):
    source = project.repo.out("rev-parse", "HEAD")
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, source)

    sha = project.repo.out("rev-parse", beta.name)
    assert project.repo.out("branch", "--contains", sha) == "", "a branch now holds it"
    assert project.repo.out("rev-parse", "HEAD") == source, "the checkout moved"
    assert project.repo.out("status", "--porcelain") == "", "the checkout was dirtied"
    assert project.repo.out("rev-parse", f"{beta.name}^") == source
    assert json.loads(project.at(beta.name, release.MANIFEST))["version"] == "0.17.0-beta.1"


def test_a_beta_records_what_it_was_built_from(project):
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, source)

    assert project.repo.source_of(beta) == source


def test_the_source_is_recorded_as_a_full_sha_whatever_was_passed(project):
    """Found by running the script for real with `--source HEAD`: it wrote
    the word HEAD into the release commit, and a promotion a week later
    could not rebuild from it. The workflow passes a full SHA, so only a
    person typing a shorter name would ever hit it - which is the case a
    test using full SHAs everywhere never exercises."""
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    beta = release.cut_beta(project.repo, "HEAD")

    assert project.repo.source_of(beta) == source


def test_a_push_that_changes_nothing_shipped_cuts_no_beta(project):
    """Docs, tests and CI all reach main too. A beta of identical code
    would be offered to every tester as an update to nothing."""
    project.target("0.17.0")
    first = project.commit("target 0.17.0")
    release.cut_beta(project.repo, first)

    docs = project.edit("docs/page.md", "hello", "docs only")

    with pytest.raises(Skip):
        release.cut_beta(project.repo, docs)
    with pytest.raises(Skip):
        release.cut_beta(project.repo, first)  # and re-running is a no-op


def test_a_shipped_change_cuts_the_next_beta_with_the_blueprint_stamp_carried(project):
    project.target("0.17.0")
    first = project.commit("target 0.17.0")
    release.cut_beta(project.repo, first)

    second = project.edit("custom_components/flare/x.py", "print(1)", "python change")
    beta = release.cut_beta(project.repo, second)

    assert beta.name == "v0.17.0-beta.2"
    # The blueprint did not change between the two, so it still says the
    # first beta - nobody is told to re-import an identical file.
    stamp = version_from_description(project.at(beta.name, release.BLUEPRINT))
    assert stamp == "0.17.0-beta.1"


def test_promotion_rebuilds_the_betas_own_source_as_the_bare_version(project):
    project.target("0.17.0")
    source = project.commit("target 0.17.0")
    beta = release.cut_beta(project.repo, source)
    # Main moves on after the beta; the release must NOT pick that up.
    project.edit("custom_components/flare/later.py", "x = 1", "unsoaked change")

    stable = release.promote(project.repo, NOW + timedelta(days=30) + timedelta(hours=1))

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


def test_a_release_that_left_the_blueprint_alone_keeps_the_previous_stable_stamp(project):
    """The stamp names the tag the repair's Fix button downloads from, so
    it has to be one that exists: v0.16.0 does, and 0.17.0-beta.1's blueprint
    is identical to it."""
    project.target("0.16.0")
    stable_source = project.commit("0.16.0")
    project.repo.build(Tag.parse("v0.16.0"), stable_source, None)

    project.target("0.17.0")
    source = project.edit("custom_components/flare/x.py", "y = 2", "python only")
    release.cut_beta(project.repo, source)
    stable = release.promote(project.repo, datetime.now(timezone.utc) + timedelta(days=8))

    assert version_from_description(project.at(stable.name, release.BLUEPRINT)) == "0.16.0"


def test_a_hand_made_beta_cannot_be_promoted(project):
    """Tags made before this script existed have no recorded source, and
    guessing one would ship something nobody tested."""
    sha = project.repo.out("rev-parse", "HEAD")
    project.repo.git("tag", "v0.17.0-beta.1", sha)

    with pytest.raises(Refuse):
        release.promote(project.repo, NOW + timedelta(days=400))


def test_the_command_line_hands_the_workflow_a_tag_or_nothing(project, monkeypatch, capsys, tmp_path):
    """The workflows branch on `tag=`: set means push and publish, empty
    means stop quietly. A skip must therefore exit 0 with an EMPTY tag -
    exiting non-zero would turn every docs-only merge into a red run."""
    monkeypatch.setattr(release, "REPO_ROOT", project.root)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    project.target("0.17.0")
    source = project.commit("target 0.17.0")

    assert release.main(["cut-beta", "--source", source]) == 0
    assert output.read_text().splitlines() == ["tag=v0.17.0-beta.1", "prerelease=true"]

    output.write_text("")
    assert release.main(["cut-beta", "--source", source]) == 0  # nothing new: a skip
    assert output.read_text().splitlines() == ["tag="]

    project.target("0.16.5")  # a downgrade: somebody needs to look
    assert release.main(["cut-beta", "--source", project.commit("oops")]) == 1
    assert "::error::" in capsys.readouterr().out


# --- The wiring --------------------------------------------------------


def test_the_workflows_call_the_script_the_same_way_these_tests_do():
    """The logic is tested above; what can go stale is the wiring - a
    renamed subcommand or flag makes a workflow fail on the one day
    nobody is watching, which for the scheduled promotion is a week later."""
    cut = (REPO_ROOT / ".github" / "workflows" / "cut-beta.yml").read_text()
    promote = (REPO_ROOT / ".github" / "workflows" / "promote.yml").read_text()

    assert "scripts/release.py cut-beta --source" in cut
    assert "scripts/release.py promote" in promote
