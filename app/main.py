from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional
from .services.project_service import ProjectService
import logging
import asyncio
import json

app = FastAPI(
    title="Your API",
    description="Your API Description",
    version="1.0.0"
)

# Configure CORS
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
            
        formatted = service.prepare_hierarchy(projects, timezone)
        logging.info(f"Formatted {len(formatted)} projects")
        
        return formatted
        
    except Exception as e:
        logging.exception("Error in get_projects")
        raise HTTPException(status_code=500, detail=str(e))