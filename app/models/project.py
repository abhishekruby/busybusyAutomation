from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class ProjectInfo(BaseModel):
    address1: Optional[str]
    address2: Optional[str]
    city: Optional[str]
    country: Optional[str]
    customer: Optional[str]
    id: str
    latitude: Optional[float]
    longitude: Optional[float]
    number: Optional[str]
    phone: Optional[str]
    postalCode: Optional[str]
    reminder: Optional[bool]
    state: Optional[str]
    locationRadius: Optional[float]
    requireTimeEntryGps: Optional[str]
    additionalInfo: Optional[str]

class ProjectGroup(BaseModel):
    id: str
    groupName: Optional[str]

class Project(BaseModel):
    id: str
    title: str
    archivedOn: Optional[datetime]
    createdOn: datetime
    updatedOn: datetime
    depth: int
    projectInfo: Optional[ProjectInfo]
    projectGroup: Optional[ProjectGroup]
    children: Optional[List['Project']] = []
    cursor: Optional[str]
