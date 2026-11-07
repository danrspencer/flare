"""A blueprint input hidden by `visible:` is built from its default, not
its stored value, so an input may only hide while it's at its default."""

from tests.support import load_blueprint


def _inputs():
    for key, value in load_blueprint()["blueprint"]["input"].items():
        if value and "input" in value:
            yield from (value["input"] or {}).items()
        else:
            yield key, value


def test_an_input_hides_only_while_it_is_at_its_default():
    hidden = {key: value for key, value in _inputs() if value and "visible" in value}
    assert hidden, "nothing hides: drop this test"
    for key, value in hidden.items():
        default = value["default"]
        assert isinstance(default, bool), f"{key}: only a boolean can be told apart from its default"
        assert value["visible"] == {"field": key, "value": not default}, key


def test_no_section_hides():
    """A hidden section hides every input in it, whatever their values."""
    sections = [value for value in load_blueprint()["blueprint"]["input"].values() if value and "input" in value]
    assert all("visible" not in section for section in sections)
