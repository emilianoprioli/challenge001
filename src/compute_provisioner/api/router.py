from fastapi import APIRouter

from compute_provisioner.api.routes.health import router as health_router
from compute_provisioner.api.routes.resource_requests import router as resource_requests_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(resource_requests_router)
