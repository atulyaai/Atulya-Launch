"""Versioned API v1 scaffold.

Provides the versioned discovery surface: `/api/v1/meta` describes the installed
API version, feature groups, and registered routers. Formal `/api/v1/<resource>`
endpoints and an OpenAPI 3.1 spec file land here as features graduate to stable.
The interactive docs live at `/api/docs`.
"""

from fastapi import APIRouter, Depends

from atulya_launch import __version__
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["v1"])


def _api_modules() -> list[str]:
    import pkgutil
    import atulya_launch.web.api as api_pkg
    return [
        mod.name for mod in pkgutil.iter_modules(api_pkg.__path__)
        if not mod.name.startswith("_")
    ]


@router.get("/meta")
def api_meta(user: dict = Depends(get_current_user)):
    """Return the panel API version and the set of mounted API modules."""
    return {
        "version": str(__version__),
        "api_version": "v1",
        "openapi_url": "/api/openapi.json",
        "docs_url": "/api/docs",
        "modules": sorted(_api_modules()),
        "module_count": len(_api_modules()),
    }


@router.get("/health")
def v1_health(user: dict = Depends(get_current_user)):
    return {"status": "ok", "version": str(__version__), "api_version": "v1"}