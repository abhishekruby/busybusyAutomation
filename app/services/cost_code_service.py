import httpx
import asyncio
import logging
from typing import List, Optional, Dict
from datetime import datetime
from ..config import settings
from ..models.cost_code import CostCode
from ..utils.timezone_utils import convert_utc_to_timezone

class CostCodeService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 1000
        self.max_concurrent = 3

    async def fetch_cost_codes(self, api_key: str, is_archived: bool, timezone: str) -> List[Dict]:
        try:
            all_cost_codes = []
            after_cursor = None

            while True:
                query = {
                    "query": """
                        query QueryCostCodes($filter: CostCodeFilter!, $first: Int, $after: String, $sort: [CostCodeSort!]) {
                            costCodes(filter: $filter, first: $first, after: $after, sort: $sort) {
                                id
                                cursor
                                costCode
                                title
                                unitTitle
                                costCodeGroup {
                                    groupName
                                }
                                createdOn
                                updatedOn
                                archivedOn
                            }
                        }
                    """,
                    "variables": {
                        "filter": {
                            "archivedOn": {"isNull": not is_archived}
                        },
                        "sort": [
                            {"costCode": "asc"},
                            {"title": "asc"}
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

                    cost_codes = data.get("data", {}).get("costCodes", [])
                    if not cost_codes:
                        break

                    all_cost_codes.extend(cost_codes)

                    if len(cost_codes) < self.batch_size:
                        break

                    after_cursor = cost_codes[-1].get("cursor")
                    if not after_cursor:
                        break

            return self.prepare_cost_code_data(all_cost_codes, timezone)

        except Exception as e:
            logging.error(f"Error fetching cost codes: {str(e)}", exc_info=True)
            raise

    def prepare_cost_code_data(self, cost_codes: List[Dict], timezone: str) -> List[Dict]:
        formatted_data = []
        
        for cc in cost_codes:
            if not isinstance(cc, dict):
                logging.warning(f"Invalid cost code data: {cc}")
                continue
                
            try:
                # Safely handle nested group data
                cost_code_group = cc.get('costCodeGroup') or {}
                if not isinstance(cost_code_group, dict):
                    cost_code_group = {}
                
                formatted_data.append({
                    'id': cc.get('id', ''),
                    'cost_code': cc.get('costCode', ''),
                    'title': cc.get('title', ''),
                    'unit_title': cc.get('unitTitle', ''),
                    'group_name': cost_code_group.get('groupName', ''),
                    'created_on': convert_utc_to_timezone(cc.get('createdOn', ''), timezone),
                    'updated_on': convert_utc_to_timezone(cc.get('updatedOn', ''), timezone),
                    'status': 'Archived' if cc.get('archivedOn') else 'Active'
                })
            except Exception as e:
                logging.error(f"Error processing cost code data: {str(e)}", exc_info=True)
                continue

        return formatted_data
