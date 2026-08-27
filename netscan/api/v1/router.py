from fastapi import APIRouter
from netscan.api.v1.auth_keys import router as auth_router
from netscan.api.v1.ips import router as ips_router
from netscan.api.v1.scans import router as scans_router
from netscan.api.v1.subnets import router as subnets_router
from netscan.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(subnets_router)
api_v1_router.include_router(ips_router)
api_v1_router.include_router(scans_router)
api_v1_router.include_router(webhooks_router)
