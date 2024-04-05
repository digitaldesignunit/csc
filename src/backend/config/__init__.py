from pydantic import BaseSettings


class CommonSettings(BaseSettings):
    APP_NAME: str = "CSC - Catalogue of Second Chances"


class DatabaseSettings(BaseSettings):
    DB_SERVER: str
    DB_USER: str
    DB_NAME: str


class Settings(CommonSettings, DatabaseSettings):
    pass


settings = Settings()
