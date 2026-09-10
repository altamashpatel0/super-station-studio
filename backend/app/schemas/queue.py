"""
app/schemas/queue.py
======================

Pydantic request/response models for the runtime Playback Queue
(V0.3). Wire formats only, kept independent of the SQLAlchemy models
in `database/models.py` - mirrors the split used by
`schemas/playlist.py`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .library import SongOut


class QueueItemOut(BaseModel):
    id: int
    song_id: Optional[int] = None
    asset_id: Optional[int] = None
    item_type: str = "SONG"
    position: int
    status: str
    added_at: Optional[str] = None
    song: Optional[SongOut] = None
    asset: Optional[dict] = None


class AddQueueItemRequest(BaseModel):
    song_id: int
    # If true, insert immediately after whatever is currently PLAYING
    # (or at the very front, if nothing is) instead of appending to the
    # end. Repeated play_next calls stack, most-recent-first - see
    # QueueRepository.add_track.
    play_next: bool = False


class ReorderQueueRequest(BaseModel):
    """`queue_item_ids` must be a permutation of the queue's current
    `queue_items.id` values, in the desired new order."""

    queue_item_ids: list[int] = Field(..., min_length=1)
