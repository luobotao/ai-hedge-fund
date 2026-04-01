"""
Tests that L2 (MySQL) cache initializes successfully when cryptography package is available.

Regression test for: MySQL connections failing with sha256_password/caching_sha2_password
auth methods due to missing cryptography package.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import src.data.database as _db_module


@pytest.fixture
def sqlite_db():
    """Patch database module to use in-memory SQLite (simulates a working DB connection)."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    original_engine = _db_module.engine
    original_session_local = _db_module.SessionLocal

    _db_module.engine = test_engine
    _db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    _db_module.Base.metadata.create_all(bind=test_engine)

    yield test_engine

    _db_module.engine = original_engine
    _db_module.SessionLocal = original_session_local


class TestDualCacheL2Init:
    def test_l2_cache_initializes_when_database_url_set(self, sqlite_db):
        """L2 cache must be non-None when DATABASE_URL is set and DB is reachable."""
        from src.data.dual_cache import DualLayerCacheManager

        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}):
            cache = DualLayerCacheManager(enable_l2=True)

        assert cache.l2_cache is not None, (
            "L2 cache is None — likely missing 'cryptography' package or DB connection failed"
        )

    def test_cryptography_package_importable(self):
        """cryptography package must be installed for MySQL sha256/caching_sha2 auth."""
        try:
            import cryptography
        except ImportError:
            pytest.fail(
                "cryptography package not installed. "
                "Run: poetry add cryptography\n"
                "Required for MySQL sha256_password/caching_sha2_password auth."
            )
