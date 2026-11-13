"""A blueprint can't share a template between two places, so a few are
written out twice. Each pair has to stay the same but for what's meant to
differ."""

import re

from tests.support import load_blueprint


def _expansion(template: str) -> list[str]:
    """The statements turning Room Target into entities: from the namespace
    to the areas' entities. The YAML folds the template's lines, so it's
    read tag by tag."""
    tags = re.findall(r"{%.*?%}", template)
    start = next(i for i, tag in enumerate(tags) if tag.startswith("{% set ns = namespace(entities=[]"))
    end = next(i for i, tag in enumerate(tags) if "area_entities(a)" in tag)
    return tags[start : end + 2]


def _find(blueprint: dict, key: str):
    """The first value under `key`, anywhere in the blueprint."""
    if isinstance(blueprint, dict):
        if key in blueprint:
            return blueprint[key]
        blueprint = list(blueprint.values())
    if isinstance(blueprint, list):
        return next((found for item in blueprint if (found := _find(item, key)) is not None), None)
    return None


def test_recovered_and_lux_dark_expand_the_target_the_same_way():
    """lux_dark's one extra line leaves out everything but named entities
    with Sensors From Areas off."""
    triggers = {t.get("id"): t for t in load_blueprint()["trigger"] if t.get("platform") == "template"}
    recovered = _expansion(triggers["recovered"]["value_template"])
    lux_dark = _expansion(triggers["lux_dark"]["value_template"])

    assert [line for line in lux_dark if line != "{% elif not use_area_sensors %}"] == recovered
    assert len(lux_dark) == len(recovered) + 1


def test_the_brightness_and_idle_templates_become_levels_the_same_way():
    blueprint = load_blueprint()
    brightness = _find(blueprint["action"], "template_brightness_map")
    idle = _find(blueprint["action"], "template_idle_map")

    assert re.sub(r"\s+", " ", idle).replace("template_idle_brightness", "template_brightness_levels") == re.sub(
        r"\s+", " ", brightness
    )
