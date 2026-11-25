import pytest

from packages.core.config import Settings


@pytest.fixture(autouse=True)
def isolate_from_local_env(monkeypatch):
    """Tests must give the same result whatever is in the developer's .env file."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
