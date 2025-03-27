from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class CostCodeGroup(BaseModel):
    groupName: Optional[str]

class CostCode(BaseModel):
    id: str
    cursor: Optional[str]
    costCode: str
    title: str
    unitTitle: Optional[str]
    costCodeGroup: Optional[CostCodeGroup]
    createdOn: datetime
    updatedOn: datetime
    archivedOn: Optional[datetime]
