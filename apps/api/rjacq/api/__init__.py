"""HTTP routers implementing the design doc §9 surface.

Phase 0 ships these as **typed stubs**: full request/response models (so the generated
OpenAPI schema + TypeScript types freeze the contract) with bodies that return
``501 Not Implemented``. The domain streams replace the bodies in Phases 1–4 without
changing the signatures.
"""

from fastapi import APIRouter

from . import auth, comps, deals, feedback, gates, mapping, webhooks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(deals.router)
api_router.include_router(mapping.router)
api_router.include_router(comps.router)
api_router.include_router(gates.router)
api_router.include_router(feedback.router)
api_router.include_router(webhooks.router)

__all__ = ["api_router"]
