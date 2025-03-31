import httpx
import asyncio
import logging
from typing import List, Optional, Dict
from datetime import datetime
from ..config import settings
from ..models.equipment import Equipment
from ..utils.timezone_utils import convert_utc_to_timezone

class EquipmentService:
    def __init__(self):
        self.url = settings.BUSYBUSY_GRAPHQL_URL
        self.batch_size = 1000

    async def fetch_equipment(self, api_key: str, is_deleted: bool, timezone: str) -> List[Dict]:
        try:
            all_equipment = []
            after_cursor = None

            while True:
                query = {
                    "query": """
                        query GetEquipment($filter: EquipmentFilter, $first: Int, $after: String, $sort: [EquipmentSort!]) {
                            equipment(filter: $filter, first: $first, after: $after, sort: $sort) {
                                id
                                equipmentName
                                year
                                model {
                                    id
                                    type
                                    title
                                    unknown
                                    make {
                                        id
                                        title
                                        unknown
                                    }
                                    category {
                                        id
                                        title
                                    }
                                }
                                lastHours {
                                    id
                                    runningHours
                                }
                                costHistory {
                                    id
                                    operatorCostRate
                                    createdOn
                                    deletedOn
                                }
                                cursor
                                createdOn
                                updatedOn
                                deletedOn
                            }
                        }
                    """,
                    "variables": {
                        "filter": {
                            "deletedOn": {"isNull": not is_deleted}
                        },
                        "sort": [
                            {"equipmentName": "asc"},
                            {"createdOn": "desc"}
                        ],
                        "first": self.batch_size,
                        "after": after_cursor
                    }
                }

                async with httpx.AsyncClient() as client:
                    try:
                        response = await client.post(
                            self.url,
                            json=query,
                            headers={"key-authorization": api_key},
                            timeout=60.0
                        )
                        response.raise_for_status()
                        data = response.json()

                        if "errors" in data:
                            error_messages = [e.get('message', 'Unknown error') for e in data["errors"]]
                            if error_messages:
                                raise Exception(f"GraphQL errors: {', '.join(error_messages)}")
                            
                        equipment_data = data.get("data", {}).get("equipment", [])
                        if not equipment_data:
                            break

                        all_equipment.extend(equipment_data)

                        if len(equipment_data) < self.batch_size:
                            break

                        after_cursor = equipment_data[-1].get("cursor")
                        if not after_cursor:
                            break

                    except httpx.HTTPError as http_err:
                        logging.error(f"HTTP error occurred: {http_err}")
                        raise Exception(f"HTTP error: {http_err}")
                    except Exception as e:
                        logging.error(f"Error during request: {str(e)}")
                        raise

            return self.prepare_equipment_data(all_equipment, timezone)

        except Exception as e:
            logging.error(f"Error fetching equipment: {str(e)}", exc_info=True)
            raise

    def prepare_equipment_data(self, equipment_list: List[Dict], timezone: str) -> List[Dict]:
        formatted_data = []
        
        for equip in equipment_list:
            if not isinstance(equip, dict):
                continue

            try:
                model = equip.get('model') or {}
                make = model.get('make') or {}
                category = model.get('category') or {}
                last_hours = equip.get('lastHours') or {}
                
                # Filter and sort cost history
                cost_history = [
                    ch for ch in (equip.get('costHistory') or [])
                    if ch and not ch.get('deletedOn')
                ]
                cost_history.sort(
                    key=lambda x: datetime.fromisoformat(x.get('createdOn', '1970-01-01T00:00:00')),
                    reverse=True
                )
                latest_cost = cost_history[0] if cost_history else {}

                formatted_data.append({
                    'id': equip.get('id', ''),
                    'equipment_name': equip.get('equipmentName', ''),
                    'type': model.get('type', ''),
                    'category': category.get('title', ''),
                    'make': '' if make.get('unknown', True) else make.get('title', ''),
                    'model': '' if model.get('unknown', True) else model.get('title', ''),
                    'year': equip.get('year', ''),
                    'running_hours': last_hours.get('runningHours', ''),
                    'operator_cost_rate': latest_cost.get('operatorCostRate', ''),
                    'created_on': convert_utc_to_timezone(equip.get('createdOn', ''), timezone),
                    'updated_on': convert_utc_to_timezone(equip.get('updatedOn', ''), timezone),
                    'status': 'Deleted' if equip.get('deletedOn') else 'Active'
                })
            except Exception as e:
                logging.error(f"Error processing equipment data: {str(e)}", exc_info=True)
                continue

        return formatted_data
