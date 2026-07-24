from typing import List, Optional
from pydantic import BaseModel

class BulkAssignPayload(BaseModel):
    lead_ids: List[int]
    assigned_rep_id: int
    overwrite_existing: bool = False

class BulkAssignResponse(BaseModel):
    assigned_count: int
    transferred_count: int
    skipped_count: int

class BulkImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    errors: List[str]

class BulkDeletePayload(BaseModel):
    lead_ids: List[int]

class BulkDeleteResponse(BaseModel):
    deleted_count: int
