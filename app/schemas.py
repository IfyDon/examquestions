from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OptionInput(BaseModel):
    text: str = Field(min_length=1)


class MediaInput(BaseModel):
    source_url: HttpUrl | None = None
    media_type: str = Field(min_length=1)
    local_path: str | None = None
    svg_metadata: dict = Field(default_factory=dict)


class QuestionInput(BaseModel):
    exam: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    year: int | None = Field(default=None, ge=1900, le=2200)
    question: str = Field(min_length=1)
    options: dict[str, str] = Field(default_factory=dict)
    answer: str | None = None
    explanation: str | None = None
    source_url: HttpUrl | None = None
    media: list[MediaInput] = Field(default_factory=list)


class CrawlRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    discovered_count: int
    processed_count: int
    error_count: int
    new_question_count: int
    duplicate_question_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
