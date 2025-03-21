import httpx
import asyncio
from typing import List, Optional, Generator
from datetime import datetime
import logging
import json
from itertools import islice
from ..config import settings
from ..models.project import Project
from ..utils.timezone_utils import convert_utc_to_timezone

class ProjectService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 500  # Reset to smaller batch size for stability
        self.process_batch_size = 2000
        self.max_concurrent = 5  # Increased concurrent requests

    def _batch_generator(self, items: list, batch_size: int) -> Generator:
        """Generate batches from items"""
        iterator = iter(items)
        while batch := list(islice(iterator, batch_size)):
            yield batch

    async def fetch_projects(self, api_key: str, is_archived: bool) -> List[Project]:
        logging.info(f"Fetching projects from BusyBusy API... {api_key} {is_archived}")
        try:
            all_projects = []
            after_cursor = None

            while True:
                query = self._build_graphql_query(is_archived, after_cursor)
                logging.info(f"Fetching batch with cursor: {after_cursor}")

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url,
                        json=query,
                        headers={
                            "key-authorization": api_key,
                            "Content-Type": "application/json"
                        },
                        timeout=60.0
                    )

                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text}")

                    data = response.json()
                    if "errors" in data and data["errors"]:
                        raise Exception(f"GraphQL errors: {data['errors']}")

                    projects_data = data.get("data", {}).get("projects", [])
                    if not projects_data:
                        break

                    logging.info(f"Received batch of {len(projects_data)} projects")
                    all_projects.extend(projects_data)
                    logging.info(f"Total projects so far: {len(all_projects)}")

                    # Check if we have all projects
                    if len(projects_data) < self.batch_size:
                        logging.info("Last batch received (less than batch size)")
                        break

                    # Get cursor from the last project
                    last_project = projects_data[-1]
                    after_cursor = last_project.get("cursor")
                    if not after_cursor:
                        logging.info("No more cursor available")
                        break

            logging.info(f"Total projects fetched: {len(all_projects)}")
            return all_projects

        except Exception as e:
            logging.error(f"Error in fetch_projects: {str(e)}", exc_info=True)
            raise

    def prepare_hierarchy(self, projects: List[dict], timezone: str) -> List[dict]:
        def format_project_data(project: dict, project_names: List[str]) -> dict:
            if not isinstance(project, dict):
                logging.warning(f"Invalid project data received: {project}")
                return None

            info = project.get('projectInfo') or {}
            group = project.get('projectGroup') or {}

            try:
                # Fill empty project names with empty strings
                project_names.extend([""] * (7 - len(project_names)))
                
                # Default values for India if lat/long are missing
                default_lat = 20.593684
                default_long = 78.96288
                default_radius = 100

                # Format dates properly
                created_on = convert_utc_to_timezone(project.get('createdOn'), timezone)
                updated_on = convert_utc_to_timezone(project.get('updatedOn'), timezone)
                
                if not created_on or not updated_on:
                    logging.error(f"Date conversion failed for project {project.get('id')}")
                    logging.error(f"createdOn: {project.get('createdOn')}, updatedOn: {project.get('updatedOn')}")

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
                    "project_names": project_names[:7],  # Ensure exactly 7 elements
                    "group_name": group.get('groupName', ''),
                    "latitude": info.get('latitude', default_lat),
                    "longitude": info.get('longitude', default_long),
                    "has_reminder": "Yes" if info.get('reminder') else "No",
                    "location_radius": info.get('locationRadius', default_radius),
                    "additional_info": info.get('additionalInfo', ''),
                    "created_on": created_on,
                    "updated_on": updated_on,
                    "requires_gps": "Yes" if info.get('requireTimeEntryGps') in ["self", "self_and_children"] else "No",
                    "requires_gps_children": "Yes" if info.get('requireTimeEntryGps') == "self_and_children" else "No",
                    "status": "Archived" if project.get('archivedOn') else "Active"
                }
            except Exception as e:
                logging.error(f"Error formatting project data: {e}")
                return None

        def _process_children(parent: dict, depth: int, project_names: List[str]) -> List[dict]:
            result = []
            if not parent or not isinstance(parent, dict):
                return result

            current_names = project_names.copy()
            current_names[depth] = parent.get('title', '')

            if formatted_data := format_project_data(parent, current_names):
                result.append(formatted_data)

            children = parent.get('children') or []
            if children and isinstance(children, list):
                try:
                    children = sorted(
                        children,
                        key=lambda x: x.get('createdOn', ''),
                        reverse=True
                    )
                    
                    if not parent.get('archivedOn'):
                        children = [c for c in children if not c.get('archivedOn')]

                    for child in children:
                        result.extend(_process_children(child, depth + 1, current_names))
                except Exception as e:
                    logging.error(f"Error processing children: {e}")

            return result

        try:
            result = []
            for project_batch in self._batch_generator(projects, self.process_batch_size):
                batch_result = []
                for project in project_batch:
                    if project:
                        batch_result.extend(_process_children(project, 0, [""] * 7))
                result.extend(batch_result)
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
                    }
                    projectGroup {
                        groupName
                    }
                }
            """,
            "variables": {
                "filter": {
                    "archivedOn": {"isNull": not is_archived},
                    "depth": {"equal": 1}
                },
                "sort": [{"title": "asc"}],
                "first": self.batch_size,
                "after": after_cursor
            }
        }
