from compute_provisioner.core.config import Settings


def test_railway_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgresql://user:password@postgres.railway.internal:5432/railway"
    )

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_local_psycopg_url_is_unchanged() -> None:
    database_url = "postgresql+psycopg://compute:compute@localhost:5432/compute"

    settings = Settings(database_url=database_url)

    assert settings.database_url == database_url
