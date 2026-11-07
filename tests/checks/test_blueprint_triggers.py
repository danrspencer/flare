"""The blueprint tells the user's Additional Triggers apart from its own by
position, so their position has to be what trigger_id says it is."""

import re

import yaml

from tests.support import load_blueprint


def test_additional_triggers_come_last_at_the_position_trigger_id_reads():
    blueprint = load_blueprint()
    triggers = blueprint["trigger"]
    nested = [i for i, trigger in enumerate(triggers) if set(trigger) == {"triggers"}]
    assert nested == [len(triggers) - 1], "Additional Triggers must be the one nested list, and last"

    template = blueprint["variables"]["trigger_id"]
    assert re.search(r"trigger\.idx \| int\(-1\) >= (\d+)", template).group(1) == str(nested[0]), (
        "trigger_id must count the blueprint's own triggers"
    )


def test_nothing_but_trigger_id_and_manual_run_reads_trigger_id_directly():
    """A user's trigger can be given any id, so everything else reads the
    position-aware trigger_id."""
    blueprint = load_blueprint()
    variables = {key: value for key, value in blueprint["variables"].items() if key not in ("trigger_id", "manual_run")}
    rest = {**blueprint, "variables": variables}
    assert "trigger.id" not in yaml.safe_dump(rest)


def test_the_reference_page_lists_exactly_the_trigger_ids():
    """The IDs are public: conditions in rooms check them, so renaming one
    breaks those rooms. The reference page's table is the list."""
    from tests.support import REPO_ROOT

    page = (REPO_ROOT / "docs" / "reference" / "blueprint.md").read_text()
    table = page.split("### Trigger IDs", 1)[1].split("\n## ", 1)[0]
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", table, re.M))
    own = {trigger["id"] for trigger in load_blueprint()["trigger"] if "id" in trigger}
    assert documented == own
