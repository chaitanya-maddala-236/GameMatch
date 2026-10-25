from gamematch.db import make_engine


def test_neon_postgres_url_uses_psycopg_driver() -> None:
    engine = make_engine("postgres://user:password@host.example/db?sslmode=require")
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.query["sslmode"] == "require"
    finally:
        engine.dispose()
