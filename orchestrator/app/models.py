from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel


@dataclass
class UEInfo:
    ue_id: str
    current_slice: str
    target_slice: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class SliceInfo(BaseModel):
    sst: int
    sd: Optional[str] = None


class MigrationRequest(BaseModel):
    ue_id: str
    current_slice: str
    target_slice: str
    slice_a_baseurl: str
    slice_b_baseurl: str
    flexran_baseurl: str
    upf_baseurl: str


class TriggerMigrationRequest(BaseModel):
    ue_id: str
    current_slice: str
    target_slice: str
