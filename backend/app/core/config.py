"""Read deployment configuration without embedding credentials."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configure the API and its initial account."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "portfolio_manager"
    jwt_secret: str = ""
    cors_origins: str = "http://localhost:5173"
    bootstrap_email: str = ""
    bootstrap_name: str = "Initial Administrator"
    bootstrap_password: str = ""

    def validate_security(self) -> None:
        """Reject absent and known example signing keys."""
        known_defaults = {"replace-with-a-unique-random-secret-at-least-32-characters", "dev-secret-change-in-production", "change-me", "dev-secret"}
        if len(self.jwt_secret) < 32 or self.jwt_secret.lower() in known_defaults:
            raise RuntimeError("JWT_SECRET must be a unique random secret of at least 32 characters")
        if bool(self.bootstrap_email) != bool(self.bootstrap_password):
            raise RuntimeError("Set both BOOTSTRAP_EMAIL and BOOTSTRAP_PASSWORD, or neither")
        if self.bootstrap_password and (len(self.bootstrap_password.encode()) > 72 or len(self.bootstrap_password) < 12 or self.bootstrap_password == "replace-with-temporary-credential"):
            raise RuntimeError("BOOTSTRAP_PASSWORD must be a unique temporary credential of 12 characters or more (maximum 72 bytes)")


settings = Settings()
