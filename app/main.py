from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, List
from .services.project_service import ProjectService
from .services.budget_service import BudgetService
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
    api_key: str = Header(..., alias="key-authorization"),
    is_archived: bool = Query(...),
):
    """Fetch all budget data with timezone conversion"""
    try:
        if not api_key or len(api_key) < 20:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key format"
            )

        service = BudgetService()
        logging.info(f"Starting fetch of all budgets with timezone: {timezone}")
        
        budgets = await service.fetch_all_budgets(api_key, is_archived)
        logging.info(f"Fetched {len(budgets)} budget records")
        
        return budgets
        
    except Exception as e:
        logging.exception("Error in get_budgets")
        raise HTTPException(status_code=500, detail=str(e))