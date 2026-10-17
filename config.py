# config.py
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Core ---
    BOT_TOKEN: str = Field(..., validation_alias="BOT_TOKEN")
    ADMIN_ID: int | None = Field(None, validation_alias="ADMIN_ID")
    ENV: str = Field("dev", validation_alias="ENV")

    # --- DB ---
    DB_URL: str = Field("sqlite+aiosqlite:///./data/bot.db", validation_alias="DB_URL")
    PATH_DB: str = Field("data/database.db", validation_alias="PATH_DB")

    # --- Webhook / server ---
    WEBHOOK_URL: str | None = Field(None, validation_alias="WEBHOOK_URL")
    WEBHOOK_PATH: str = Field("/sepay/webhook", validation_alias="WEBHOOK_PATH")
    PORT: int = Field(5051, validation_alias="PORT")

    # --- Misc info ---
    USER_NAME: str | None = Field(None, validation_alias="USER_NAME")
    SEPAY_WEBHOOK_KEY: str | None = Field(
        None,
        validation_alias=AliasChoices("SEPAY_WEBHOOK_KEY", "SEPAY_KEY"),
    )

    # --- Binance ---
    BINANCE_API_KEY: str | None = Field(None, validation_alias="BINANCE_API_KEY")
    BINANCE_API_SECRET: str | None = Field(None, validation_alias="BINANCE_API_SECRET")
    BINANCE_ID: str | None = Field(None, validation_alias="BINANCE_ID")

    # --- Wallets ---
    TRC20_ADDRESS: str | None = Field(None, validation_alias="TRC20_ADDRESS")
    BEP20_ADDRESS: str | None = Field(None, validation_alias="BEP20_ADDRESS")

    # --- VN Bank ---
    VN_BANK_ACCOUNT: str | None = Field(None, validation_alias="BANK_ACC")
    VN_BANK_CODE: str | None = Field(None, validation_alias="BANK_CODE")
    VN_BANK_NAME: str | None = Field(None, validation_alias="BANK_NAME")
    VN_OWNER_NAME: str | None = Field(None, validation_alias="ACC_OWNER")

    # --- Orders ---
    ORDER_TTL_SECONDS: int = Field(900, validation_alias="ORDER_TTL_SECONDS")

    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # ✅ không crash nếu env có thêm key
        case_sensitive=False,    # ✅ USERNAME / username đều đọc được
    )

settings = Settings()
