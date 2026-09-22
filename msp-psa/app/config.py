from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://psa:psa@localhost:5432/psa"
    secret_key: str = "dev-only-not-for-production"
    app_name: str = "MSP PSA"
    base_url: str = "http://localhost:8000"
    timezone: str = "America/New_York"

    # Worker tuning. Low poll rate keeps the J1900 idle between jobs.
    worker_poll_seconds: int = 5
    worker_max_attempts: int = 5

    # Microsoft Graph — shared mailbox email connector. Leave blank until
    # the app registration exists; the poll job skips itself when they're
    # empty rather than erroring the worker.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_mailbox: str = "support@adamhiltonracing.com"
    email_poll_seconds: int = 60

    default_ticket_board_slug: str = "triage"

    # Fernet key for encrypting stored credentials. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Required before the Credentials feature can be used; nothing else
    # breaks if it's blank.
    credential_encryption_key: str = ""


settings = Settings()
