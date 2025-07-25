import uvicorn

from .settings import UvicornSettings


def main():
    uvicorn_settings = UvicornSettings()
    uvicorn.run(
        app="pdf_parser.app:create_app",
        factory=True,
        host=uvicorn_settings.host,
        port=uvicorn_settings.port,
        reload=uvicorn_settings.reload,
        workers=uvicorn_settings.workers,
        root_path=uvicorn_settings.root_path,
        proxy_headers=uvicorn_settings.proxy_headers,
        timeout_keep_alive=uvicorn_settings.timeout_keep_alive,
    )


if __name__ == "__main__":
    main()
