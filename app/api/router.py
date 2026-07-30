from fastapi import APIRouter

from app.api.routes import campaigns, contacts, system, unsubscribe, webhooks

router = APIRouter()
router.include_router(system.router)
router.include_router(contacts.router)
router.include_router(campaigns.router)
router.include_router(unsubscribe.router)
router.include_router(webhooks.router)

