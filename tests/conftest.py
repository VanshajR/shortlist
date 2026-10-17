import os

import pytest

from shortlist import db

# A throwaway database, never DATABASE_URL: these tests empty the tables.
TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def conn():
    if not TEST_DB:
        pytest.skip("set TEST_DATABASE_URL to run database tests")
    connection = db.connect(TEST_DB)
    connection.execute("truncate jobs, users restart identity")
    connection.commit()
    yield connection
    connection.close()
