from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from compute_provisioner.api.router import api_router
from compute_provisioner.core.config import get_settings
from compute_provisioner.core.instance import instance_id, public_instance_id


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["X-Instance-ID"],
    )
    application.include_router(api_router)

    @application.middleware("http")
    async def identify_instance(request, call_next):
        response = await call_next(request)
        response.headers["X-Instance-ID"] = public_instance_id(instance_id())
        return response

    simulator_directory = Path(__file__).parent / "web" / "simulator"
    application.mount(
        "/simulator",
        StaticFiles(directory=simulator_directory, html=True),
        name="simulator",
    )

    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/simulator/")

    return application


app = create_app()
