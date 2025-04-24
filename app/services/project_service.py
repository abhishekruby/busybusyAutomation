import httpx
import asyncio
from typing import List, Optional, Generator, Dict, Any
from datetime import datetime
import logging
import json
from itertools import islice
from concurrent.futures import ThreadPoolExecutor
from ..config import settings
from ..models.project import Project
from ..utils.timezone_utils import convert_utc_to_timezone
from ..utils.redis_cache import RedisCache

class ProjectService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 500
        self.cache = RedisCache()
        self.processing_batch_size = 2000
        self.max_concurrent_batches = 2
        self.progress_logger = logging.getLogger("project_progress")

    def _batch_generator(self, items: list, batch_size: int) -> Generator:
        """Generate batches from items"""
        iterator = iter(items)
        while batch := list(islice(iterator, batch_size)):
            yield batch

    async def fetch_projects(self, api_key: str, is_archived: bool, timezone: str) -> List[Project]:
        """Fetch projects with Redis caching and batch processing"""
        cache_key = f"project_data_{'archive' if is_archived else 'active'}"
        
        # Try cache first
        cached_data = await self.cache.get_cached_data(cache_key)
        if cached_data:
            self.progress_logger.info(f"Using cached project data for {cache_key}")
            # Convert timezone for cached data
            return self._convert_timezone_for_projects(cached_data, timezone)

        try:
            # Fetch all projects
            all_projects = await self._fetch_all_projects(api_key, is_archived)
            
            if not all_projects:
                return []

            # Process projects in batches (without timezone conversion)
            processed_projects = await self._process_projects_in_batches(all_projects, is_archived)

            # Cache results (in UTC)
            cache_minutes = 720 if is_archived else 10
            await self.cache.set_cached_data(cache_key, processed_projects, cache_minutes)
            
            # Convert timezone before returning
            return self._convert_timezone_for_projects(processed_projects, timezone)

        except Exception as e:
            logging.error(f"Error in fetch_projects: {str(e)}", exc_info=True)
            raise

    def _convert_timezone_for_projects(self, projects: List[Dict], timezone: str) -> List[Dict]:
        """Convert UTC timestamps to specified timezone"""
        converted_projects = []
        for project in projects:
            project_copy = project.copy()
            project_copy['created_on'] = convert_utc_to_timezone(project['created_on'], timezone)
            project_copy['updated_on'] = convert_utc_to_timezone(project['updated_on'], timezone)
            converted_projects.append(project_copy)
        return converted_projects

    async def _fetch_all_projects(self, api_key: str, is_archived: bool) -> List[Dict]:
        """Fetch all projects from API with pagination"""
        all_projects = []
        after_cursor = None
        total_fetched = 0

        while True:
            try:
                query = self._build_graphql_query(is_archived, after_cursor)
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url,
                        json=query,
                        headers={"key-authorization": api_key},
                        timeout=60.0
                    )
                    
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text}")

                    data = response.json()
                    projects_data = data.get("data", {}).get("projects", [])
                    
                    if not projects_data:
                        break

                    total_fetched += len(projects_data)
                    self.progress_logger.info(f"Fetched {total_fetched} projects so far")
                    
                    all_projects.extend(projects_data)

                    if len(projects_data) < self.batch_size:
                        break

                    after_cursor = projects_data[-1].get("cursor")
                    if not after_cursor:
                        break

            except Exception as e:
                logging.error(f"Error fetching projects batch: {str(e)}")
                raise

        return all_projects

    async def _process_projects_in_batches(self, projects: List[Dict], is_archived: bool) -> List[Dict]:
        """Process projects in batches using thread pool"""
        result = []
        batches = list(self._batch_generator(projects, self.processing_batch_size))
        total_batches = len(batches)
        
        self.progress_logger.info(f"Processing {len(projects)} projects in {total_batches} batches")

        # Process batches with limited concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent_batches)
        tasks = []

        for batch_idx, batch in enumerate(batches):
            # Create task for each batch
            task = asyncio.create_task(
                self._process_batch(batch, batch_idx, total_batches, semaphore, is_archived)
            )
            tasks.append(task)

        # Wait for all batches to complete and collect results
        batch_results = await asyncio.gather(*tasks)
        
        # Combine results in order
        for batch_result in batch_results:
            result.extend(batch_result)

        return result

    async def _process_batch(self, batch: List[Dict], batch_idx: int, 
                           total_batches: int, semaphore: asyncio.Semaphore,
                           is_archived: bool) -> List[Dict]:
        """Process a single batch of projects using a thread"""
        async with semaphore:
            self.progress_logger.info(f"Processing batch {batch_idx + 1}/{total_batches}")
            
            # Process the batch in a thread
            result = await asyncio.to_thread(
                self._process_projects_sync, 
                batch,
                is_archived
            )
            
            self.progress_logger.info(f"Completed batch {batch_idx + 1}/{total_batches}")
            return result

    def _process_projects_sync(self, projects: List[Dict], is_archived: bool) -> List[Dict]:
        """Synchronous processing of a batch of projects"""
        result = []
        for project in projects:
            processed = self._process_single_project(project, is_archived)
            if processed:
                result.extend(processed)
        return result

    def _process_single_project(self, project: Dict, is_archived: bool) -> List[Dict]:
        """Process a single project and its hierarchy"""
        try:
            return self.prepare_hierarchy([project], is_archived)
        except Exception as e:
            logging.error(f"Error processing project {project.get('id')}: {str(e)}")
            return []

    def prepare_hierarchy(self, projects: List[dict], is_archived: bool) -> List[dict]:
        def format_project_data(project: dict, project_names: List[str]) -> dict:
            if not isinstance(project, dict):
                logging.warning(f"Invalid project data received: {project}")
                return None
            
            info = project.get('projectInfo') or {}
            group = project.get('projectGroup') or {}

            try:
                # Fill empty project names with empty strings and clean spaces
                cleaned_names = [name.strip() if name else '' for name in project_names]
                cleaned_names.extend([''] * (7 - len(cleaned_names)))

                return {
                    "id": project.get('id', ''),
                    "number": info.get('number', ''),
                    "customer": info.get('customer', ''),
                    "address1": info.get('address1', ''),
                    "address2": info.get('address2', ''),
                    "city": info.get('city', ''),
                    "state": info.get('state', ''),
                    "postal_code": info.get('postalCode', ''),
                    "phone": info.get('phone', ''),
                    "project_names": cleaned_names[:7],
                    "group_name": group.get('groupName', ''),
                    "latitude": info.get('latitude',''),
                    "longitude": info.get('longitude', ''),
                    "has_reminder": "Yes" if info.get('reminder') else "No",
                    "location_radius": info.get('locationRadius',''),
                    "additional_info": info.get('additionalInfo', ''),
                    "created_on": project.get('createdOn'),  # Store UTC time
                    "updated_on": project.get('updatedOn'),  # Store UTC time
                    "requires_gps": "Yes" if info.get('requireTimeEntryGps') in ["self", "self_and_children"] else "No",
                    "requires_gps_children": "Yes" if info.get('requireTimeEntryGps') == "self_and_children" else "No",
                    "status": "Archived" if is_archived else "Active"
                }
            except Exception as e:
                logging.error(f"Error formatting project data: {e}")
                return None

        def filter_children(project: dict) -> dict:
            """Recursively filter out archived children from active parents"""
            children = project.get('children', [])
            if not children:
                return project
            
            # Keep only non-archived children and process them recursively
            filtered_children = []
            for child in children:
                if is_archived:
                    if child.get('archivedOn'):
                        # Recursively filter this child's children
                        filtered_child = filter_children(child.copy())
                        filtered_children.append(filtered_child)
                else:
                    if not child.get('archivedOn'):
                        # Recursively filter this child's children
                        filtered_child = filter_children(child.copy())
                        filtered_children.append(filtered_child)
            
            # Replace original children with filtered list
            project['children'] = filtered_children
            return project

        def process_hierarchy(project: dict, depth: int, project_names: List[str]) -> List[dict]:
            result = []
            if not project:
                return result

            current_names = project_names.copy()
            current_names[depth] = project.get('title', '')

            # Pass is_root flag to format_project_data
            if formatted_data := format_project_data(project, current_names):
                result.append(formatted_data)
            
            # Filter is_archived children from project
            project = filter_children(project)
            
            children = project.get('children', [])
            if not children:
                return result

            # Sort children by title
            children = sorted(children, key=lambda x: x.get('title', '',))
            for child in children:
                # Children are never root projects
                result.extend(process_hierarchy(child, depth + 1, current_names))

            return result

        try:
            # Process hierarchy
            result = []
            for project in projects:
                result.extend(process_hierarchy(project, 0, [""] * 7))

            return result

        except Exception as e:
            logging.error(f"Error in prepare_hierarchy: {e}")
            return []

    def _build_graphql_query(self, is_archived: bool, after_cursor: Optional[str]) -> dict:
        return {
            "query": """
                query FetchProjects($filter: ProjectFilter, $first: Int, $after: String, $sort: [ProjectSort!]) {
                    projects(filter: $filter, first: $first, after: $after, sort: $sort) {
                        cursor
                        id
                        title
                        archivedOn
                        depth
                        createdOn
                        updatedOn
                        children {              
                            ...ProjectDetails
                            children {                
                                ...ProjectDetails
                                children {                  
                                    ...ProjectDetails
                                    children {                    
                                        ...ProjectDetails
                                        children {                      
                                            ...ProjectDetails
                                            children {                        
                                                ...ProjectDetails
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        ...ProjectDetails
                    }
                }
                fragment ProjectDetails on Project {
                    id
                    title
                    archivedOn
                    depth
                    createdOn
                    updatedOn
                    projectInfo {
                        projectId
                        number
                        customer
                        address1
                        address2
                        city
                        state
                        postalCode
                        phone
                        reminder
                        requireTimeEntryGps
                        additionalInfo
                        latitude
                        locationRadius
                        longitude
                    }
                    projectGroup {
                        groupName
                    }
                }
            """,
            "variables": {
                "filter": {
                    "archivedOn": {"isNull": not is_archived},
                    "depth": {"equal": 1},
                },
                "sort": [
                    {"title": "asc"},
                    {"projectInfo": {"projectId": "asc"}},
                    {"createdOn": "asc"}
                ],
                "first": self.batch_size,
                "after": after_cursor
            }
        }
