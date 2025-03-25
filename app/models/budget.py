from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class BudgetHours(BaseModel):
    id: str
    projectId: str
    memberId: Optional[str]
    budgetSeconds: Optional[int]
    costCodeId: Optional[str]
    equipmentId: Optional[str]
    createdOn: datetime
    equipmentBudgetSeconds: Optional[int]
    cursor: Optional[str]

class BudgetCost(BaseModel):
    id: str
    projectId: str
    memberId: Optional[str]
    costBudget: Optional[float]
    costCodeId: Optional[str]
    equipmentId: Optional[str]
    equipmentCostBudget: Optional[float]
    cursor: Optional[str]

class ProgressBudget(BaseModel):
    id: str
    cursor: str
    quantity: Optional[float]
    value: Optional[float]
    projectId: str
    costCodeId: Optional[str]

class CostCode(BaseModel):
    id: str
    cursor: str
    title: str
    costCode: str
    archivedOn: Optional[datetime]
    unitTitle: Optional[str]
