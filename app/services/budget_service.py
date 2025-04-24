import httpx
import asyncio
import logging
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from ..config import settings
from ..models.budget import BudgetHours, BudgetCost, ProgressBudget, CostCode
from ..utils.redis_cache import RedisCache


class BudgetService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 500
        self.chunk_size = 100
        self.cache = RedisCache()

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
        """Fetch budget data with caching"""
        cache_key = f"budget_data_{'archive' if is_archived else 'active'}"
        
        # Try to get from cache first
        cached_data = await self.cache.get_cached_data(cache_key)
        if cached_data:
            logging.info(f"Using cached budget data for {cache_key}")
            return cached_data

        try:
            # Fetch projects first
            projects_data = await self._fetch_budget_projects(api_key, is_archived)
            if not projects_data:
                logging.debug("No projects data found for budgets.")
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

            # Get project IDs and split into chunks
            project_ids = list(project_info.keys())
            chunks = [project_ids[i:i + self.chunk_size] 
                     for i in range(0, len(project_ids), self.chunk_size)]

            # Process chunks concurrently
            hours_tasks = [self._fetch_budget_hours_chunk(api_key, chunk) for chunk in chunks]
            costs_tasks = [self._fetch_budget_costs_chunk(api_key, chunk) for chunk in chunks]
            progress_tasks = [self._fetch_progress_budgets_chunk(api_key, chunk) for chunk in chunks]

            # Gather all results
            hours_chunks, costs_chunks, progress_chunks = await asyncio.gather(
                asyncio.gather(*hours_tasks),
                asyncio.gather(*costs_tasks),
                asyncio.gather(*progress_tasks)
            )

            # Combine chunk results
            hours = [item for chunk in hours_chunks for item in chunk]
            costs = [item for chunk in costs_chunks for item in chunk]
            progress = [item for chunk in progress_chunks for item in chunk]

            # Get cost codes
            cost_code_ids = {pb.get('costCodeId') for pb in progress if pb.get('costCodeId')}
            cost_codes = await self._fetch_cost_codes(api_key, list(cost_code_ids)) if cost_code_ids else []

            # Format and return data without timezone conversion
            formatted_data = self._combine_hierarchical_data(hours, costs, progress, cost_codes, project_info)

            # Ensure data is JSON-serializable
            for item in formatted_data:
                for key, value in item.items():
                    if isinstance(value, datetime):
                        item[key] = value.isoformat()

            # Cache the results
            cache_minutes = 720 if is_archived else 10  # 12 hours for archived, 10 minutes for active
            await self.cache.set_cached_data(cache_key, formatted_data, cache_minutes)

            logging.debug(f"Formatted budget data: {formatted_data}")
            return formatted_data

        except Exception as e:
            logging.error(f"Error fetching budgets: {str(e)}", exc_info=True)
            raise

    async def _fetch_with_cursor(self, api_key: str, query: dict, key: str) -> List[Dict]:
        """Fetch all records with cursor pagination"""
        all_data = []
        cursor = None

        async with httpx.AsyncClient() as client:
            while True:
                current_query = {**query}
                current_query["variables"]["after"] = cursor

                data = await self._execute_query(client, api_key, current_query, key)
                if not data:
                    break

                all_data.extend(data)
                if len(data) < self.batch_size:
                    break

                cursor = data[-1].get("cursor")
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
                "filter": {"archivedOn": {"isNull": not is_archived}},
                "sort": [{"title": "asc"}, {"createdOn": "asc"}]
            }
        }
        return await self._fetch_with_cursor(api_key, query, "projects")

    async def _fetch_budget_hours_chunk(self, api_key: str, project_ids: List[str]) -> List[Dict]:
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
        return await self._fetch_with_cursor(api_key, query, "budgetHours")

    async def _fetch_budget_costs_chunk(self, api_key: str, project_ids: List[str]) -> List[Dict]:
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
        return await self._fetch_with_cursor(api_key, query, "budgetCosts")

    async def _fetch_progress_budgets_chunk(self, api_key: str, project_ids: List[str]) -> List[Dict]:
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
        return await self._fetch_with_cursor(api_key, query, "progressBudgets")

    async def _fetch_cost_codes(self, api_key: str, cost_code_ids: List[str]) -> List[CostCode]:
        async with httpx.AsyncClient() as client:
            query = {
                "query": """
                    query GetCostCodes($filter: CostCodeFilter) {
                        costCodes(filter: $filter) {
                            id title costCode
                        }
                    }
                """,
                "variables": {
                    "filter": {"id": {"contains": cost_code_ids}}
                }
            }
            return await self._execute_query(client, api_key, query, "costCodes")

    async def _execute_query(self, client: httpx.AsyncClient, api_key: str, query: dict, result_key: str):
        """Execute GraphQL query asynchronously"""
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
                error_messages = [error.get('message', 'Unknown error') for error in data["errors"]]
                raise Exception(f"GraphQL errors: {', '.join(error_messages)}")

            result = data.get("data", {}).get(result_key)
            if result is None:
                logging.warning(f"No {result_key} found in response")
                return []

            return result

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
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
