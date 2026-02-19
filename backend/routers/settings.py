"""Settings API router for runtime configuration."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.auth import require_admin
from core.settings import get_use_sonnet, set_use_sonnet

router = APIRouter()


class ModelSettingResponse(BaseModel):
    use_sonnet: bool
    model_name: str


class ModelSettingRequest(BaseModel):
    use_sonnet: bool


@router.get("/model", response_model=ModelSettingResponse)
async def get_model_setting():
    """Get the current model setting."""
    use_sonnet = get_use_sonnet()
    return ModelSettingResponse(
        use_sonnet=use_sonnet,
        model_name="claude-sonnet-4-6" if use_sonnet else "claude-opus-4-6",
    )


@router.put("/model", response_model=ModelSettingResponse, dependencies=[Depends(require_admin)])
async def update_model_setting(body: ModelSettingRequest):
    """Update the model setting (admin only). Takes effect on next conversation turn."""
    set_use_sonnet(body.use_sonnet)
    return ModelSettingResponse(
        use_sonnet=body.use_sonnet,
        model_name="claude-sonnet-4-6" if body.use_sonnet else "claude-opus-4-6",
    )
