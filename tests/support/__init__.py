"""Shared by every test layer: repo paths and the blueprint loader."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT = REPO_ROOT / "custom_components" / "flare"
WWW = COMPONENT / "www"
BLUEPRINT_PATH = "danrspencer/flare.yaml"
BLUEPRINT_FILE = COMPONENT / "blueprints" / "flare.yaml"


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that accepts `!input` (as None)."""


_BlueprintLoader.add_constructor("!input", lambda loader, node: None)


def load_blueprint() -> dict:
    """The blueprint file as plain YAML, `!input` tags read as None."""
    return yaml.load(BLUEPRINT_FILE.read_text(), Loader=_BlueprintLoader)


def load_script(name: str):
    """Import scripts/<name>.py as a module."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: @dataclass looks its module up in sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
