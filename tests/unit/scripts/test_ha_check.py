"""scripts/ha_check.py, which checks FLARE against a Home Assistant release."""

from tests.support import load_script

ha_check = load_script("ha_check")


def release(yanked: bool = False) -> list[dict]:
    return [{"filename": "homeassistant.whl", "yanked": yanked}]


def test_the_newest_release_includes_betas():
    releases = {"2026.10.4": release(), "2026.11.0": release(), "2026.12.0b0": release(), "2026.12.0b1": release()}
    assert ha_check.newest(releases) == "2026.12.0b1"


def test_a_release_is_newer_than_its_betas():
    releases = {"2026.12.0b3": release(), "2026.12.0": release(), "2026.11.3": release()}
    assert ha_check.newest(releases) == "2026.12.0"


def test_months_compare_as_numbers():
    assert ha_check.newest({"2026.9.3": release(), "2026.10.0": release()}) == "2026.10.0"


def test_yanked_dev_and_empty_releases_are_skipped():
    releases = {
        "2026.11.0": release(),
        "2026.12.0b0": release(yanked=True),
        "2026.12.0.dev20261101": release(),
        "2026.12.0b1": [],
    }
    assert ha_check.newest(releases) == "2026.11.0"


def test_a_form_is_submitted_with_its_suggested_values_else_its_defaults():
    schema = [
        {"name": "layout", "required": True, "default": "Home"},
        {"name": "note", "required": False},
        {
            "type": "expandable",
            "name": "Downstairs",
            "schema": [
                {"name": "Kitchen", "required": False, "description": {"suggested_value": "home"}},
                {"name": "Study", "required": False, "description": {"suggested_value": None}, "default": "x"},
            ],
        },
    ]
    assert ha_check.submitted(schema) == {"layout": "Home", "Downstairs": {"Kitchen": "home", "Study": "x"}}


LOG = """\
2026-11-05 10:57:31.188+00:00 WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration flare which has not been tested by Home Assistant.
2026-11-05 10:57:34.353+00:00 ERROR (MainThread) [metno] Access to https://api.met.no returned error
2026-11-05 10:57:40.000+00:00 INFO (MainThread) [custom_components.flare] Set up 3 schedules
2026-11-05 10:57:41.797+00:00 ERROR (MainThread) [custom_components.flare] Error setting up entry Flares for flare
Traceback (most recent call last):
ImportError: cannot import name 'SERVICE_TRIGGER'
2026-11-05 10:57:42.000+00:00 WARNING (MainThread) [homeassistant.helpers.frame] Detected that custom integration 'flare' calls a deprecated helper
2026-11-05 10:57:43 ERROR (MainThread) [homeassistant.components.automation.kitchen_lighting] Error executing script. Action flare.resolve_target not found
"""


def test_the_log_keeps_flare_warnings_and_errors_with_their_tracebacks():
    found = ha_check.flare_log_entries(LOG)
    assert [ha_check.first_line(e) for e in found] == [
        "ERROR (MainThread) [custom_components.flare] Error setting up entry Flares for flare",
        "WARNING (MainThread) [homeassistant.helpers.frame] Detected that custom integration 'flare' calls a deprecated helper",
        "ERROR (MainThread) [homeassistant.components.automation.kitchen_lighting] Error executing script. Action flare.resolve_target not found",
    ]
    assert found[0].endswith("ImportError: cannot import name 'SERVICE_TRIGGER'")


def test_the_same_failures_on_the_same_release_have_the_same_marker():
    def report(version, *failed):
        r = ha_check.Report(version)
        r.check("Home Assistant starts", True)
        for name in failed:
            r.check(name, False, "detail that can vary")
        return r.fingerprint()

    assert report("2026.12.0b1", "Flares are created") == report("2026.12.0b1", "Flares are created")
    assert report("2026.12.0b1", "Flares are created") != report("2026.12.0b2", "Flares are created")
    assert report("2026.12.0b1", "Flares are created") != report("2026.12.0b1", "Services register")


def test_a_log_entry_fails_the_report():
    r = ha_check.Report("2026.12.0b1")
    r.check("Home Assistant starts", True)
    assert r.passed
    r.log = ["2026-11-05 10:57:43 ERROR (MainThread) [custom_components.flare] boom"]
    assert not r.passed


class FakeGitHub:
    """Stands in for `gh`: answers the issue list, records everything else."""

    def __init__(self, open_issues: list[dict]):
        self.open_issues = open_issues
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        if args[:2] == ("issue", "list"):
            return ha_check.json.dumps(self.open_issues)
        self.calls.append(args)
        return ""

    def did(self, *prefix: str) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c[: len(prefix)] == prefix]


def run_issue(monkeypatch, tmp_path, outcome, open_issues, report="<!-- ha-check 2026.12.0b1 abc -->\n### report\n"):
    fake = FakeGitHub(open_issues)
    monkeypatch.setattr(ha_check, "gh", fake)
    path = tmp_path / "report.md"
    path.write_text(report)
    ha_check.main(["issue", "--version", "2026.12.0b1", "--outcome", outcome, "--report", str(path)])
    return fake


def test_a_first_failure_opens_an_issue(monkeypatch, tmp_path):
    fake = run_issue(monkeypatch, tmp_path, "failure", [])
    (created,) = fake.did("issue", "create")
    assert "FLARE fails on Home Assistant 2026.12.0b1" in created
    assert any("<!-- ha-check 2026.12.0b1 abc -->" in arg for arg in created)


def test_a_failure_already_reported_adds_nothing(monkeypatch, tmp_path):
    issue = {"number": 7, "body": "intro\n<!-- ha-check 2026.12.0b1 abc -->", "comments": []}
    assert run_issue(monkeypatch, tmp_path, "failure", [issue]).calls == []


def test_a_new_failure_is_a_comment_on_the_open_issue(monkeypatch, tmp_path):
    issue = {"number": 7, "body": "<!-- ha-check 2026.12.0b0 abc -->", "comments": []}
    fake = run_issue(monkeypatch, tmp_path, "failure", [issue])
    assert [c[:3] for c in fake.calls] == [("issue", "comment", "7")]


def test_a_pass_closes_the_open_issue(monkeypatch, tmp_path):
    issue = {"number": 7, "body": "<!-- ha-check 2026.12.0b0 abc -->", "comments": []}
    fake = run_issue(monkeypatch, tmp_path, "success", [issue])
    assert [c[:3] for c in fake.calls] == [("issue", "comment", "7"), ("issue", "close", "7")]


def test_a_pass_with_no_issue_does_nothing(monkeypatch, tmp_path):
    assert run_issue(monkeypatch, tmp_path, "success", []).calls == []


def test_a_failed_install_still_reports(monkeypatch, tmp_path):
    fake = FakeGitHub([])
    monkeypatch.setattr(ha_check, "gh", fake)
    ha_check.main(["issue", "--version", "2026.12.0b1", "--outcome", "failure", "--report", str(tmp_path / "none.md")])
    (created,) = fake.did("issue", "create")
    assert any("installing that release probably failed" in arg for arg in created)
