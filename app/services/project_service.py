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
        self.batch_size = 1000

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

    def prepare_hierarchy(self, projects: List[dict], timezone: str, is_archived: bool) -> List[dict]:
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

                # Format dates
                created_on = convert_utc_to_timezone(project.get('createdOn'), timezone)
                updated_on = convert_utc_to_timezone(project.get('updatedOn'), timezone)

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
                    "latitude": info.get('latitude',''),  # Only set default for root
                    "longitude": info.get('longitude', ''),  # Only set default for root
                    "has_reminder": "Yes" if info.get('reminder') else "No",
                    "location_radius": info.get('locationRadius',''),  # Only set default for root
                    "additional_info": info.get('additionalInfo', ''),
                    "created_on": created_on,
                    "updated_on": updated_on,
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
