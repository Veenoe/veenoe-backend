"""Stored curriculum snapshots, independent of HTTP validation and active catalogs.

Names record what the session used. Missing provenance stays unknown on older
records; it must not be silently attributed to today's catalog revision.
"""

from pydantic import BaseModel, Field


class SelectedTopic(BaseModel):
    """The ID and name used for a catalog topic or a student-defined focus."""

    id: str
    name: str


class SelectedChapter(BaseModel):
    """Stored chapter snapshot; no topics means entire-chapter coverage."""

    id: str
    name: str
    topics: list[SelectedTopic] = Field(default_factory=list)


class CurriculumSelection(BaseModel):
    """Client-supplied session scope, preserved independently of catalog changes."""

    catalog_id: str | None = None
    catalog_version: str | None = None
    class_level: int
    subject_id: str
    subject_name: str
    chapters: list[SelectedChapter]
