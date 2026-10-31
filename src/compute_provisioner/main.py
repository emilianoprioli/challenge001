from fastapi import FastAPI

from compute_provisioner.api.router import api_router
from compute_provisioner.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.include_router(api_router)
    return application


app = create_app()
