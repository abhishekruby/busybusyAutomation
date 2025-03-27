import httpx
import asyncio
import logging
from typing import List, Optional, Dict
from datetime import datetime
from ..config import settings
from ..models.employee import Employee
from ..utils.timezone_utils import convert_utc_to_timezone


class EmployeeService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 1000
        self.max_concurrent = 3

    async def fetch_employees(self, api_key: str, is_archived: bool, timezone: str) -> List[Dict]:
        try:
            all_employees = []
            after_cursor = None

            while True:
                query = {
                    "query": """
                        query QueryEmployeesList($filter: MemberFilter!, $first: Int, $after: String, $sort: [MemberSort!]) {
                            members(filter: $filter, first: $first, after: $after, sort: $sort) {
                                id firstName lastName username email phone memberNumber
                                position { title }
                                memberGroup { groupName }
                                wageHistories {
                                    wage wageRate overburden effectiveRate
                                    createdOn updatedOn deletedOn changeDate
                                }
                                isSubContractor timeLocationRequired
                                createdOn updatedOn archivedOn cursor
                            }
                        }
                    """,
                    "variables": {
                        "filter": {
                            "archivedOn": {"isNull": not is_archived},
                            "permissions": {
                                "permissions": ["manageEmployees"],
                                "operationType": "and"
                            }
                        },
                        "sort": [
                            {"firstName": "asc"},
                            {"lastName": "asc"}
                        ],
                        "first": self.batch_size,
                        "after": after_cursor
                    }
                }

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
                    
                    # Check for GraphQL errors
                    if data.get("errors"):
                        error_messages = [error.get('message', 'Unknown error') 
                                       for error in data["errors"]]
                        if error_messages:
                            raise Exception(f"GraphQL errors: {', '.join(error_messages)}")
                    
                    # Verify data structure
                    if "data" not in data:
                        raise Exception("Invalid GraphQL response: missing data field")
                        
                    members = data.get("data", {}).get("members")
                    if members is None:
                        raise Exception("Invalid GraphQL response: missing members field")

                    if not members:  # Empty list is ok, just break the loop
                        break

                    all_employees.extend(members)

                    if len(members) < self.batch_size:
                        break

                    after_cursor = members[-1].get("cursor")
                    if not after_cursor:
                        break

            return self.prepare_employee_data(all_employees, timezone)

        except Exception as e:
            logging.error(f"Error fetching employees: {str(e)}", exc_info=True)
            raise

    def prepare_employee_data(self, employees: List[Dict], timezone: str) -> List[Dict]:
        payroll_types = {10: 'Hourly', 30: 'Weekly', 40: 'Monthly', 50: 'Yearly'}
        gps_settings = {"YES": 'required', "AUTO": 'not required', "NO": 'off'}
        formatted_data = []

        for emp in employees:
            if not isinstance(emp, dict):
                logging.warning(f"Invalid employee data: {emp}")
                continue

            try:
                # Safely get nested values with fallbacks
                member_group = emp.get('memberGroup') or {}
                position = emp.get('position') or {}
                
                # Get latest valid wage history
                wage_histories = emp.get('wageHistories') or []
                valid_histories = [h for h in wage_histories if h and not h.get('deletedOn')]
                
                # Sort by changeDate and updatedOn
                valid_histories.sort(key=lambda x: (
                    datetime.fromisoformat(x.get('changeDate', '1970-01-01T00:00:00')) if x.get('changeDate') else datetime.min,
                    datetime.fromisoformat(x.get('updatedOn', '1970-01-01T00:00:00')) if x.get('updatedOn') else datetime.min
                ), reverse=True)

                latest_wage = valid_histories[0] if valid_histories else {}

                formatted_data.append({
                    'id': emp.get('id', ''),
                    'member_number': emp.get('memberNumber', ''),
                    'first_name': emp.get('firstName', ''),
                    'last_name': emp.get('lastName', ''),
                    'username': emp.get('username', ''),
                    'wage': latest_wage.get('wage', ''),
                    'wage_rate': payroll_types.get(latest_wage.get('wageRate'), ''),
                    'overburden': latest_wage.get('overburden', ''),
                    'phone': (emp.get('phone', '') or '').replace('+', ''),
                    'email': emp.get('email', ''),
                    'group_name': member_group.get('groupName', ''),
                    'position': position.get('title', ''),
                    'is_subcontractor': 'Yes' if emp.get('isSubContractor') else 'No',
                    'gps_setting': gps_settings.get(emp.get('timeLocationRequired'), ''),
                    'created_on': convert_utc_to_timezone(emp.get('createdOn', ''), timezone),
                    'updated_on': convert_utc_to_timezone(emp.get('updatedOn', ''), timezone),
                    'status': 'Archived' if emp.get('archivedOn') else 'Active'
                })

            except Exception as e:
                logging.error(f"Error processing employee data: {str(e)}", exc_info=True)
                continue

        return formatted_data
