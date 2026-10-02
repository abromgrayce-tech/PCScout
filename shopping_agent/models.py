"""Minimal shared Pydantic base model."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Reject unknown fields instead of silently losing model output."""

    model_config = ConfigDict(extra="forbid")
