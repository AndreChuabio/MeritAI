import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.seed_outreach import seed_content_types  # noqa: E402
from paperpilot.outreach.content_types import CONTENT_TYPE_CONFIGS  # noqa: E402


def test_seed_creates_all_content_types_when_workspace_empty():
    senso = MagicMock()
    senso.list_content_types.return_value = []
    senso.create_content_type.side_effect = (
        lambda name, config: {"id": f"ct-{name}"}
    )

    ids = seed_content_types(senso)

    assert set(ids.keys()) == set(CONTENT_TYPE_CONFIGS.keys())
    assert senso.create_content_type.call_count == len(CONTENT_TYPE_CONFIGS)


def test_seed_is_idempotent_when_all_exist():
    existing = [
        {"id": f"ct-{name}", "name": name} for name in CONTENT_TYPE_CONFIGS
    ]
    senso = MagicMock()
    senso.list_content_types.return_value = existing

    ids = seed_content_types(senso)

    assert ids == {name: f"ct-{name}" for name in CONTENT_TYPE_CONFIGS}
    senso.create_content_type.assert_not_called()


def test_content_type_configs_cover_all_channels():
    from paperpilot.outreach.purpose import PURPOSE_CHANNELS
    used = set()
    for chans in PURPOSE_CHANNELS.values():
        used.update(chans)
    assert used.issubset(set(CONTENT_TYPE_CONFIGS.keys()))
