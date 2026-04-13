"""Pydantic schemas (DTOs) for slide templates subdomain."""

from uuid import UUID

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SlideTemplateBase(BaseModel):
    """Base model for slide templates."""

    slide_template_name: str = Field(..., description="Name of the template")
    slide_content: str = Field(..., description="String content holding template data")
    slide_template_images: Optional[List[str]] = Field(
        None, description="List of URLs or paths to template preview images"
    )


class SlideTemplateCreate(SlideTemplateBase):
    """Model for creating a slide template."""

    pass


class SlideTemplateUpdate(BaseModel):
    """Model for updating a slide template."""

    slide_template_name: Optional[str] = None
    slide_content: Optional[str] = None
    slide_template_images: Optional[List[str]] = None


class SlideTemplateInfo(SlideTemplateBase):
    """Model for slide template with all information."""

    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SlideTemplatesListResponse(BaseModel):
    """Response model for paginated slide templates."""

    templates: List[SlideTemplateInfo]
    total: int
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total_pages: int
