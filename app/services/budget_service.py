import httpx
import logging
from typing import List, Optional, Dict
from datetime import datetime
from ..config import settings
from ..models.budget import BudgetHours, BudgetCost, ProgressBudget, CostCode


class BudgetService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 50  # Reduced batch size for project fetch

    def _build_project_title(self, project: Dict, ancestors: List[Dict]) -> str:
        """Build hierarchical project title with proper ancestor ordering"""
        # Sort ancestors by depth in ascending order to get the correct hierarchy
        sorted_ancestors = sorted(ancestors, key=lambda x: x['depth'])

        # Start with root project title
        if not sorted_ancestors:
            return project['title']

        # Build hierarchy path
        path = []
        for anc in sorted_ancestors:
            path.append(anc['title'])
        path.append(project['title'])

        return " / ".join(path)

    async def fetch_all_budgets(self, api_key: str, is_archived: bool) -> List[Dict]:
        """Fetch all budget data starting with projects"""
        try:
            # First fetch all projects with ancestors
            projects_data = await self._fetch_budget_projects(api_key, is_archived)
            if not projects_data:
                return []

            # Store project hierarchy info
            project_info = {}
            for project in projects_data:
                ancestors = project.get('ancestors', [])
                project_title = self._build_project_title(project, ancestors)
                project_info[project['id']] = {
                    'title': project_title,
                    'archivedOn': project.get('archivedOn'),
                    'ancestors': ancestors
                }

            # Extract all relevant project IDs
            project_ids = list(project_info.keys())

            # Fetch budget data for all projects
            hours = await self._fetch_all_budget_hours(api_key, project_ids)
            costs = await self._fetch_all_budget_costs(api_key, project_ids)
            progress = await self._fetch_all_progress_budgets(api_key, project_ids)

            # Get cost codes
            cost_code_ids = {pb.get('costCodeId')
                             for pb in progress if pb.get('costCodeId')}
            cost_codes = await self._fetch_cost_codes(api_key, list(cost_code_ids)) if cost_code_ids else []

            return self._combine_hierarchical_data(hours, costs, progress, cost_codes, project_info)

        except Exception as e:
            logging.error(f"Error fetching all budgets: {str(e)}")
            raise

    async def _fetch_budget_projects(self, api_key: str, is_archived: bool) -> List[Dict]:
        """Fetch all projects for budget with fixed query"""
        query = {
            "query": """
                query GetBudgetProjectReimport(
                    $after: String
                    $filter: ProjectFilter
                    $sort: [ProjectSort!]
                    $first: Int
                ) {
                    projects(after: $after, first: $first, filter: $filter, sort: $sort) {
                        id
                        title
                        archivedOn
                        cursor
                        ancestors {
                            id
                            archivedOn
                            createdOn
                            title
                            depth
                        }
                    }
                }
            """,
            "variables": {
                "first": self.batch_size,
                "filter": {
                    "archivedOn": {"isNull": not is_archived},
                },
                "sort": [
                    {"title": "asc"},
                    {"createdOn": "asc"}
                ]
            }
        }

        all_projects = []
        after_cursor = None

        while True:
            try:
                current_query = {**query}
                current_query["variables"] = {
                    **query["variables"], "after": after_cursor}

                projects_data = await self._execute_query(api_key, current_query, "projects")
                if not projects_data:
                    break

                all_projects.extend(projects_data)

                if len(projects_data) < self.batch_size:
                    break

                after_cursor = projects_data[-1].get("cursor")
                if not after_cursor:
                    break

            except Exception as e:
                logging.error(f"Error fetching batch of projects: {str(e)}")
                break

        logging.info(f"Fetched {len(all_projects)} projects")
        return all_projects

    async def _fetch_all_budget_hours(self, api_key: str, project_ids: List[str]) -> List[BudgetHours]:
        query = {
            "query": """
                query budgetHoursQuery($filter: BudgetHoursFilter, $sort: [BudgetHoursSort!], $first: Int, $after: String) {
                    budgetHours(filter: $filter, sort: $sort, first: $first, after: $after) {
                        id projectId memberId budgetSeconds costCodeId equipmentId createdOn cursor equipmentBudgetSeconds
                    }
                }
            """,
            "variables": {
                "first": self.batch_size,
                "filter": {
                    "projectId": {"contains": project_ids},
                    "isLatest": {"equal": True}
                },
                "sort": [{"createdOn": "desc"}]
            }
        }
        return await self._execute_query(api_key, query, "budgetHours")

    async def _fetch_all_budget_costs(self, api_key: str, project_ids: List[str]) -> List[BudgetCost]:
        query = {
            "query": """
                query budgetCostQuery($filter: BudgetCostFilter, $sort: [BudgetCostSort!], $first: Int, $after: String) {
                    budgetCosts(filter: $filter, sort: $sort, first: $first, after: $after) {
                        id projectId memberId costBudget costCodeId equipmentId cursor equipmentCostBudget
                    }
                }
            """,
            "variables": {
                "first": self.batch_size,
                "filter": {
                    "projectId": {"contains": project_ids},
                    "isLatest": {"equal": True}
                },
                "sort": [{"createdOn": "desc"}]
            }
        }
        return await self._execute_query(api_key, query, "budgetCosts")

    async def _fetch_all_progress_budgets(self, api_key: str, project_ids: List[str]) -> List[ProgressBudget]:
        query = {
            "query": """
                query GetProgressBudget($filter: ProgressBudgetFilter, $first: Int, $after: String, $sort: [ProgressBudgetSort!]) {
                    progressBudgets(first: $first, after: $after, filter: $filter, sort: $sort) {
                        id cursor quantity value projectId costCodeId
                    }
                }
            """,
            "variables": {
                "first": self.batch_size,
                "filter": {
                    "projectId": {"contains": project_ids},
                    "deletedOn": {"isNull": True}
                },
                "sort": [{"createdOn": "desc"}]
            }
        }
        return await self._execute_query(api_key, query, "progressBudgets")

    async def _fetch_cost_codes(self, api_key: str, cost_code_ids: List[str]) -> List[CostCode]:
        query = {
            "query": """
                query GetCostCodes($filter: CostCodeFilter) {
                    costCodes(filter: $filter) {
                        id
                        title
                    }
                }
            """,
            "variables": {
                "filter": {
                    "id": {"contains": cost_code_ids}
                }
            }
        }
        return await self._execute_query(api_key, query, "costCodes")

    async def _execute_query(self, api_key: str, query: dict, result_key: str):
        """Execute GraphQL query with better error handling"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.url,
                    json=query,
                    headers={
                        "key-authorization": api_key,
                        "Content-Type": "application/json"
                    },
                    timeout=60.0
                )

                response.raise_for_status()
                data = response.json()

                if "errors" in data and data["errors"]:
                    error_messages = [
                        error.get('message', 'Unknown error') for error in data["errors"]]
                    raise Exception(
                        f"GraphQL errors: {', '.join(error_messages)}")

                result = data.get("data", {}).get(result_key)
                if result is None:
                    logging.warning(f"No {result_key} found in response")
                    return []

                return result

            except httpx.HTTPStatusError as e:
                logging.error(
                    f"HTTP error: {e.response.status_code} - {e.response.text}")
                raise Exception(f"HTTP error {e.response.status_code}")
            except Exception as e:
                logging.error(f"Error executing query: {str(e)}")
                raise

    def _combine_hierarchical_data(self, hours: List[Dict], costs: List[Dict],
                                   progress: List[Dict], cost_codes: List[Dict],
                                   project_info: Dict[str, Dict]) -> List[Dict]:
        """Combine all budget data with hierarchy support"""
        combined_data = {}
        cost_code_map = {cc['id']: cc for cc in cost_codes}

        # Store depth info for sorting
        project_depth = {}
        for proj_id, proj_data in project_info.items():
            ancestors = proj_data.get('ancestors', [])
            path_length = len(ancestors)
            project_depth[proj_id] = path_length

        # First create entries for all projects
        for proj_id, proj_data in project_info.items():

            key = (proj_id, '')
            combined_data[key] = {
                'id': '',
                'project_id': proj_id,
                'project_title': proj_data['title'],
                'cost_code_id': None,
                'cost_code_title': '',
                'labor_hours': 0,
                'labor_cost': 0,
                'progress_value': 0,
                'quantity': 0,
                'status': 'Archived' if proj_data.get('archivedOn') else 'Active'
            }

        # Update with actual budget data
        for prog in progress:
            proj_id = prog.get('projectId', '')
            cost_code_id = prog.get('costCodeId', '')
            key = (proj_id, cost_code_id)

            if proj_id in project_info:
                cost_code = cost_code_map.get(
                    cost_code_id, {}) if cost_code_id else {}
                project_data = project_info[proj_id]

                combined_data[key] = {
                    'id': prog.get('id', ''),
                    'project_id': proj_id,
                    'project_title': project_data['title'],
                    'cost_code_id': cost_code_id,
                    'cost_code_title': cost_code.get('title', ''),
                    'labor_hours': 0,
                    'labor_cost': 0,
                    'progress_value': float(prog.get('value', 0) or 0),
                    'quantity': float(prog.get('quantity', 0) or 0),
                    'status': 'Archived' if project_data.get('archivedOn') else 'Active'
                }

        # Add hours data
        for hour in hours:
            key = (hour.get('projectId', ''), hour.get('costCodeId', '') or '')
            if key in combined_data:
                budget_seconds = hour.get('budgetSeconds')
                combined_data[key]['labor_hours'] = (
                    budget_seconds / 3600) if budget_seconds is not None else 0

        # Add costs data
        for cost in costs:
            key = (cost.get('projectId', ''), cost.get('costCodeId', '') or '')
            if key in combined_data:
                combined_data[key]['labor_cost'] = float(
                    cost.get('costBudget', 0) or 0)

        # Sort results by project hierarchy title
        def sort_key(item):
            segments = item['project_title'].split(' / ')
            
            # Create normalized keys for each segment
            key_parts = []
            for segment in segments:
                # Split segment into parts, preserving order
                parts = []
                current = ''
                is_num = False
                
                for char in segment.lower():  # Convert to lowercase for case-insensitive sorting
                    if char.isdigit():
                        if not is_num:
                            if current:
                                parts.append(('', current))
                            current = char
                            is_num = True
                        else:
                            current += char
                    else:
                        if is_num:
                            if current:
                                parts.append(('0', int(current)))
                            current = char
                            is_num = False
                        else:
                            current += char
                
                # Add remaining part
                if current:
                    if is_num:
                        parts.append(('0', int(current)))
                    else:
                        parts.append(('', current))
                        
                key_parts.append(parts)
            
            # Ensure all entries have same number of parts for stable sorting
            max_segments = max(len(p) for p in key_parts) if key_parts else 0
            for parts in key_parts:
                while len(parts) < max_segments:
                    parts.append(('', ''))
                    
            return tuple(tuple(p) for p in key_parts)

        return sorted(combined_data.values(), key=sort_key)
