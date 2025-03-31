from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, List
from .services.project_service import ProjectService
from .services.budget_service import BudgetService
from .services.employee_service import EmployeeService
from .services.cost_code_service import CostCodeService
from .services.equipment_service import EquipmentService
import logging
import asyncio
import json
from datetime import datetime
from pytz import timezone
from .config import settings

app = FastAPI(
    title="BusyBusy API",
    description="API for BusyBusy Project Management",
    version="1.0.0"
)

# Update CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI"}

@app.get("/api/projects")
async def get_projects(
    is_archived: bool = Query(...),
    timezone: str = Query(...),
    api_key: str = Header(..., alias="key-authorization")
):
    try:
        if not api_key or len(api_key) < 20:  # Basic validation
            raise HTTPException(
                status_code=401, 
                detail="Invalid API key format"
            )
            
        if not timezone.startswith("GMT"):
            raise HTTPException(
                status_code=400, 
                detail="Timezone must be in GMT format (e.g. GMT+05:30)"
            )

        service = ProjectService()
        logging.info(f"Starting project fetch. Archived: {is_archived}")
        
        projects = await service.fetch_projects(api_key, is_archived)
        logging.info(f"Fetched {len(projects)} projects")
        
        if not projects:
            return []
            
        formatted = service.prepare_hierarchy(projects, timezone, is_archived)
        logging.info(f"Formatted {len(formatted)} projects")
        
        return formatted
        
    except Exception as e:
        logging.exception("Error in get_projects")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/budgets")
async def get_budgets(
    is_archived: bool = Query(...),
    api_key: str = Header(..., alias="key-authorization")
):
    """Fetch budget data with timeout handling"""
    try:
        if not api_key or len(api_key) < 20:
            raise HTTPException(status_code=401, detail="Invalid API key format")

        service = BudgetService()
        logging.info(f"Starting budget fetch. Archived: {is_archived}")
        
        budgets = await service.fetch_all_budgets(api_key, is_archived)
        logging.info(f"Fetched budget data")
        
        if not budgets:
            return []
            
        return budgets
        
    except Exception as e:
        logging.exception("Error in get_budgets")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/employees")
async def get_employees(
    is_archived: bool = Query(...),
    timezone: str = Query(...),
    api_key: str = Header(..., alias="key-authorization")
):
    """Fetch employee data with timezone support"""
    try:
        if not api_key or len(api_key) < 20:
            raise HTTPException(status_code=401, detail="Invalid API key format")
            
        if not timezone.startswith("GMT"):
            raise HTTPException(
                status_code=400, 
                detail="Timezone must be in GMT format (e.g. GMT+05:30)"
            )

        service = EmployeeService()
        logging.info(f"Starting employee fetch. Archived: {is_archived}")
        
        # Add timeout
        timeout = 180  # 3 minutes
        try:
            employees = await asyncio.wait_for(
                service.fetch_employees(api_key, is_archived, timezone), 
                timeout=timeout
            )
            
            logging.info(f"Fetched {len(employees)} employee records")
            return employees
            
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail=f"Request timed out after {timeout} seconds"
            )
        
    except Exception as e:
        logging.exception("Error in get_employees")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cost-codes")
async def get_cost_codes(
    is_archived: bool = Query(...),
    timezone: str = Query(...),
    api_key: str = Header(..., alias="key-authorization")
):
    """Fetch cost code data with timezone support"""
    try:
        if not api_key or len(api_key) < 20:
            raise HTTPException(status_code=401, detail="Invalid API key format")
            
        if not timezone.startswith("GMT"):
            raise HTTPException(
                status_code=400, 
                detail="Timezone must be in GMT format (e.g. GMT+05:30)"
            )

        service = CostCodeService()
        logging.info(f"Starting cost code fetch. Archived: {is_archived}")
        
        timeout = 180
        try:
            cost_codes = await asyncio.wait_for(
                service.fetch_cost_codes(api_key, is_archived, timezone),
                timeout=timeout
            )
            logging.info(f"Fetched {len(cost_codes)} cost code records")
            return cost_codes
            
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail=f"Request timed out after {timeout} seconds"
            )
        
    except Exception as e:
        logging.exception("Error in get_cost_codes")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/equipment")
async def get_equipment(
    is_deleted: bool = Query(...),
    timezone: str = Query(...),
    api_key: str = Header(..., alias="key-authorization")
):
    """Fetch equipment data with timezone support"""
    try:
        if not api_key or len(api_key) < 20:
            raise HTTPException(status_code=401, detail="Invalid API key format")
            
        if not timezone.startswith("GMT"):
            raise HTTPException(
                status_code=400, 
                detail="Timezone must be in GMT format (e.g. GMT+05:30)"
            )

        service = EquipmentService()
        logging.info(f"Starting equipment fetch. Deleted: {is_deleted}")
        
        timeout = 180
        try:
            equipment = await asyncio.wait_for(
                service.fetch_equipment(api_key, is_deleted, timezone),
                timeout=timeout
            )
            logging.info(f"Fetched {len(equipment)} equipment records")
            return equipment
            
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail=f"Request timed out after {timeout} seconds"
            )
        
    except Exception as e:
        logging.exception("Error in get_equipment")
        raise HTTPException(status_code=500, detail=str(e))