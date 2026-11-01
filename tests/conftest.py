import pytest

from idf_trains.config import settings


@pytest.fixture(autouse=True, scope="session")
def isolated_db(tmp_path_factory):
    """Les tests n'écrivent jamais dans la vraie base data/journeys.db."""
    original = settings.db_path
    settings.db_path = tmp_path_factory.mktemp("db") / "journeys.db"
    yield
    settings.db_path = original
