"""Unit tests for DB schema migration safety."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from shared.core.database import Base, OHLCV, Trade, Position, TradeLog


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database with all models."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestDBMigration:
    """Tests for DB schema integrity and model/DB alignment."""

    def test_position_has_direction_column(self, db_engine):
        """Position model has 'direction' column."""
        inspector = inspect(db_engine)
        columns = [col["name"] for col in inspector.get_columns("positions")]
        assert "direction" in columns

    def test_all_model_columns_exist_in_db(self, db_engine):
        """For each SQLAlchemy model, verify all columns exist in actual DB table."""
        inspector = inspect(db_engine)

        models = [OHLCV, Trade, Position, TradeLog]

        for model in models:
            table_name = model.__tablename__
            db_columns = {col["name"] for col in inspector.get_columns(table_name)}
            model_columns = {col.name for col in model.__table__.columns}

            missing = model_columns - db_columns
            assert not missing, (
                f"Model {model.__name__} has columns {missing} "
                f"not found in DB table '{table_name}'"
            )
