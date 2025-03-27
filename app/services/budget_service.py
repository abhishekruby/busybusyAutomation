import httpx
import asyncio
import logging
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from ..config import settings
from ..models.budget import BudgetHours, BudgetCost, ProgressBudget, CostCode


class BudgetService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 1000
        self.max_concurrent = 3  # Limit concurrent requests

    def _build_project_title(self, project: Dict, ancestors: List[Dict]) -> str:
        """Build hierarchical project title with proper ancestor ordering"""
        # Sort ancestors by depth in ascending order to get the correct hierarchy
        sorted_ancestors = sorted(ancestors, key=lambda x: x['depth'])

        # Start with root project title
        if not sorted_ancestors:
            return project['title'].strip()

        # Build hierarchy path
        path = []
        for anc in sorted_ancestors:
            path.append(anc['title'].strip())
        path.append(project['title'].strip())

        # Join with / and ensure no extra spaces around separators
        return " / ".join(filter(None, path)).strip()

    async def fetch_all_budgets(self, api_key: str, is_archived: bool) -> List[Dict]:
        """Fetch budget data for either archived or active projects"""
        try:
            # Fetch only projects matching archive status
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

            # Only fetch data for requested projects
            project_ids = list(project_info.keys())

            # Fetch budget data concurrently
            hours, costs, progress = await asyncio.gather(
                self._fetch_all_budget_hours(api_key, project_ids),
                self._fetch_all_budget_costs(api_key, project_ids),
                self._fetch_all_progress_budgets(api_key, project_ids)
            )

            # Get cost codes
            cost_code_ids = {pb.get('costCodeId') for pb in progress if pb.get('costCodeId')}
            cost_codes = await self._fetch_cost_codes(api_key, list(cost_code_ids)) if cost_code_ids else []
            return self._combine_hierarchical_data(hours, costs, progress, cost_codes, project_info)

        except Exception as e:
            logging.error(f"Error fetching budgets: {str(e)}")
            raise

    async def _fetch_all_with_cursor(self, api_key: str, query: dict, key: str) -> List[Dict]:
        """Fetch all records with cursor pagination and concurrency"""
        all_data = []
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_batch(cursor: Optional[str]) -> Tuple[List[Dict], Optional[str]]:
            async with semaphore:
                current_query = {**query}
                current_query["variables"]["after"] = cursor

                data = await self._execute_query(api_key, current_query, key)
                if not data:
                    return [], None

                next_cursor = data[-1].get("cursor") if len(
                    data) == self.batch_size else None
                return data, next_cursor

        cursor = None
        while True:
            batch_data, cursor = await fetch_batch(cursor)
            if not batch_data:
                break

            all_data.extend(batch_data)
            if not cursor:
                break

        return all_data

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
        return await self._fetch_all_with_cursor(api_key, query, "projects")

    async def _fetch_all_budget_hours(self, api_key: str, project_ids: List[str]) -> List[Dict]:
        # Split project IDs into chunks for parallel processing
        chunks = [project_ids[i:i + 50]
                  for i in range(0, len(project_ids), 50)]
        tasks = []

        for chunk in chunks:
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
                        "projectId": {"contains": chunk},
                        "isLatest": {"equal": True}
                    },
                    "sort": [{"createdOn": "desc"}]
                }
            }
            tasks.append(self._fetch_all_with_cursor(
                api_key, query, "budgetHours"))

        results = await asyncio.gather(*tasks)
        return [item for sublist in results for item in sublist]

    async def _fetch_all_budget_costs(self, api_key: str, project_ids: List[str]) -> List[Dict]:
        # Split project IDs into chunks for parallel processing
        chunks = [project_ids[i:i + 50]
                  for i in range(0, len(project_ids), 50)]
        tasks = []

        for chunk in chunks:
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
                        "projectId": {"contains": chunk},
                        "isLatest": {"equal": True}
                    },
                    "sort": [{"createdOn": "desc"}]
                }
            }
            tasks.append(self._fetch_all_with_cursor(
                api_key, query, "budgetCosts"))

        results = await asyncio.gather(*tasks)
        return [item for sublist in results for item in sublist]

    async def _fetch_all_progress_budgets(self, api_key: str, project_ids: List[str]) -> List[Dict]:
        # Split project IDs into chunks for parallel processing
        chunks = [project_ids[i:i + 50]
                  for i in range(0, len(project_ids), 50)]
        tasks = []

        for chunk in chunks:
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
                        "projectId": {"contains": chunk},
                        "deletedOn": {"isNull": True}
                    },
                    "sort": [{"createdOn": "desc"}]
                }
            }
            tasks.append(self._fetch_all_with_cursor(
                api_key, query, "progressBudgets"))

        results = await asyncio.gather(*tasks)
        return [item for sublist in results for item in sublist]

    async def _fetch_cost_codes(self, api_key: str, cost_code_ids: List[str]) -> List[CostCode]:
        query = {
            "query": """
                query GetCostCodes($filter: CostCodeFilter) {
                    costCodes(filter: $filter) {
                        id
                        title
                        costCode
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
        combined_data = []
        cost_code_map = {cc['id']: cc for cc in cost_codes}

        # Group data by project first
        for proj_id, proj_data in project_info.items():
            # Create base project entry first (without cost codes)
            project_hours = sum(h.get('budgetSeconds', 0) / 3600 for h in hours 
                              if h.get('projectId') == proj_id and not h.get('costCodeId'))
            project_costs = sum(float(c.get('costBudget', 0) or 0) for c in costs 
                              if c.get('projectId') == proj_id and not c.get('costCodeId'))
            
            combined_data.append({
                'id': '',
                'project_id': proj_id,
                'project_title': proj_data['title'],
                'cost_code_id': None,
                'cost_code_title': '',
                'labor_hours': project_hours,
                'labor_cost': project_costs,
                'progress_value': 0,
                'quantity': 0,
                'status': 'Archived' if proj_data.get('archivedOn') else 'Active'
            })

            # Find all cost codes with actual data
            project_cost_codes = set()
            
            # Only add cost codes that have progress values or quantities
            for prog in progress:
                if (prog.get('projectId') == proj_id 
                    and prog.get('costCodeId')
                    and (prog.get('value') or prog.get('quantity'))):
                    project_cost_codes.add(prog.get('costCodeId'))

            # Create entries for each valid cost code
            for cc_id in project_cost_codes:
                if cc_id in cost_code_map:
                    cost_code = cost_code_map[cc_id]
                    cc_progress = next((p for p in progress 
                        if p.get('projectId') == proj_id 
                        and p.get('costCodeId') == cc_id), {})
                    
                    if cc_progress:  # Only create entry if there's progress data
                        cc_hours = next((h for h in hours 
                            if h.get('projectId') == proj_id 
                            and h.get('costCodeId') == cc_id), {})
                        cc_costs = next((c for c in costs 
                            if c.get('projectId') == proj_id 
                            and c.get('costCodeId') == cc_id), {})

                        combined_data.append({
                            'id': cc_progress.get('id', ''),
                            'project_id': proj_id,
                            'project_title': proj_data['title'],
                            'cost_code_id': cc_id,
                            'cost_code_title': f"{cost_code.get('costCode', '')} {cost_code.get('title', '')}".strip(),
                            'labor_hours': cc_hours.get('budgetSeconds', 0) / 3600 if cc_hours.get('budgetSeconds') is not None else 0,
                            'labor_cost': float(cc_costs.get('costBudget', 0) or 0),
                            'progress_value': float(cc_progress.get('value', 0) or 0),
                            'quantity': float(cc_progress.get('quantity', 0) or 0),
                            'status': 'Archived' if proj_data.get('archivedOn') else 'Active'
                        })

        # Sort by project title and cost code
        def sort_key(item):
            parts = item['project_title'].split(' / ')
            return tuple([p.lower() for p in parts] + [item.get('cost_code_title', '').lower()])

        return sorted(combined_data, key=sort_key)
