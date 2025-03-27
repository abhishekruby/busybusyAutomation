from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class Position(BaseModel):
    title: Optional[str]

class MemberGroup(BaseModel):
    groupName: Optional[str]

class WageHistory(BaseModel):
    wage: Optional[float]
    wageRate: Optional[int]
    overburden: Optional[float]
    effectiveRate: Optional[float]
    createdOn: Optional[datetime]
    updatedOn: Optional[datetime]
    deletedOn: Optional[datetime]
    changeDate: Optional[datetime]

class Employee(BaseModel):
    id: str
    firstName: Optional[str]
    lastName: Optional[str]
    username: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    memberNumber: Optional[str]
    position: Optional[Position]
    memberGroup: Optional[MemberGroup]
    wageHistories: Optional[List[WageHistory]] = []
    isSubContractor: Optional[bool]
    timeLocationRequired: Optional[str]
    createdOn: datetime
    updatedOn: datetime
    archivedOn: Optional[datetime]
    cursor: Optional[str]
