from pydantic import BaseModel, Field
from typing import Optional, Literal

class Entry(BaseModel):
    """
    Diary entries collection schema
    Collection name: "entry"
    """
    title: str = Field(..., description="Title of the media")
    media_type: Literal['movie', 'series', 'anime'] = Field(..., description="Type of media")
    year: Optional[int] = Field(None, ge=1800, le=2100, description="Release year")
    image: Optional[str] = Field(None, description="Poster or cover image URL")
    external_id: Optional[str] = Field(None, description="External API ID (e.g., MAL, TVMaze, iTunes)")
    source: Optional[str] = Field(None, description="Source API name")
    status: Literal['Planned', 'Watching', 'Completed', 'Dropped'] = Field('Planned', description="Watching status")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Personal rating 1-5")
    review: Optional[str] = Field(None, description="Short personal review")
