"""An entry belongs to one release. An edit anchored on a heading that
every release has ("### Fixed") once copied one into eighteen of them."""

import re
from collections import Counter

from tests.support import REPO_ROOT


def test_no_entry_appears_under_two_releases():
    text = (REPO_ROOT / "CHANGELOG.md").read_text()
    entries = re.findall(r"^- \*\*(.+?)\*\*", text, flags=re.MULTILINE)

    repeated = [entry for entry, count in Counter(entries).items() if count > 1]
    assert repeated == []
