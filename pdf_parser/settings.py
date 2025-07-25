from typing import Union

from pydantic_settings import BaseSettings, SettingsConfigDict


class UvicornSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UVICORN_", env_file=".env", extra="allow"
    )

    host: str = "0.0.0.0"
    port: int = 6001
    reload: bool = False
    root_path: str = ""
    proxy_headers: bool = True
    timeout_keep_alive: int = 600
    workers: Union[int, None] = None
