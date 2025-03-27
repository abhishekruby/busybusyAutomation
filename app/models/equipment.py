from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class EquipmentMemberInfo(BaseModel):
    id: str
    firstName: Optional[str]
    lastName: Optional[str]

class EquipmentMake(BaseModel):
    deletedOn: Optional[datetime]
    id: str
    imageId: Optional[str]
    review: Optional[str]
    submittedOn: Optional[datetime]
    title: str
    unknown: Optional[bool]
    updatedOn: datetime

class EquipmentType(BaseModel):
    id: str
    title: str

class EquipmentCategory(BaseModel):
    deletedOn: Optional[datetime]
    equipmentTypeId: str
    id: str
    imageId: Optional[str]
    imageUrl: Optional[str]
    review: Optional[str]
    submittedOn: Optional[datetime]
    title: str
    updatedOn: datetime
    type: EquipmentType

class EquipmentModel(BaseModel):
    type: Optional[str]
    category: Optional[EquipmentCategory]
    deletedOn: Optional[datetime]
    equipmentCategoryId: Optional[str]
    equipmentMakeId: Optional[str]
    id: str
    imageId: Optional[str]
    imageUrl: Optional[str]
    make: Optional[EquipmentMake]
    modelNumber: Optional[str]
    submittedOn: Optional[datetime]
    title: str
    unknown: Optional[bool]
    updatedOn: datetime
    year: Optional[int]

class EquipmentHours(BaseModel):
    id: str
    runningHours: Optional[float]

class EquipmentCostHistory(BaseModel):
    id: str
    machineCostRate: Optional[float]
    operatorCostRate: Optional[float]
    changeDate: datetime
    createdOn: datetime
    updatedOn: datetime
    deletedOn: Optional[datetime]

class Equipment(BaseModel):
    archivedOn: Optional[datetime]
    createdOn: datetime
    cursor: Optional[str]
    deletedOn: Optional[datetime]
    equipmentGroupId: Optional[str]
    equipmentModelId: Optional[str]
    equipmentName: str
    fuelCapacity: Optional[float]
    id: str
    imageId: Optional[str]
    imageUrl: Optional[str]
    importTtlSeconds: Optional[int]
    importType: Optional[str]
    lastHoursId: Optional[str]
    lastLocationId: Optional[str]
    year: Optional[int]
    updatedByMember: Optional[EquipmentMemberInfo]
    model: Optional[EquipmentModel]
    organizationId: str
    serialNumber: Optional[str]
    submittedOn: Optional[datetime]
    trackManualHours: Optional[bool]
    updatedOn: datetime
    lastHours: Optional[EquipmentHours]
    costHistory: Optional[List[EquipmentCostHistory]]
