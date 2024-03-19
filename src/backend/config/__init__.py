from pydantic import BaseSettings


class CommonSettings(BaseSettings):
    APP_NAME: str = "CSC - Catalogue of Second Chances"


class DatabaseSettings(BaseSettings):
    DB_URL: str
    DB_NAME: str


class Settings(CommonSettings, DatabaseSettings):
    pass


settings = Settings()
