"""Calendar writer - creates actual Exchange Online events via Graph API."""
from __future__ import annotations

import json
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from uuid import uuid4

from ..graph_client import GraphClient
from .models import TimeBlock, Task, BlockOutcome

logger = logging.getLogger("work_context_sync.timeblock.calendar_writer")


class CalendarWriter:
    """Creates and manages Exchange calendar events for timeblocks."""
    
    # Extended property schema name (MS Graph format)
    EXT_PROP_NAME = "timeblock_meta"
    
    def __init__(self, graph_client: GraphClient, timezone: str = "America/Indiana/Indianapolis"):
        self.client = graph_client
        self.timezone = timezone
        self.app_guid = "timeblock-sync-1.0"  # For extended properties
    
    def create_timeblock_event(self, block: TimeBlock) -> str:
        """
        Create Exchange event for a timeblock.
        
        Returns:
            Exchange event ID
        """
        event_payload = block.to_exchange_event(self.timezone)
        
        # Add extended properties for tracking
        extended_props = {
            "timeblock_id": block.id,
            "source_task_id": block.task.id if block.task else None,
            "source_type": block.task.source_type.value if block.task else None,
            "original_priority": block.task.priority if block.task else 0,
            "confidence_score": block.confidence,
            "auto_scheduled": True,
            "strategy": "aggressive",
            "created_at": datetime.now().isoformat(),
            "reschedule_count": 0,
            "outcome": None,
        }
        
        event_payload["singleValueExtendedProperties"] = [
            {
                "id": f"String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}",
                "value": json.dumps(extended_props)
            }
        ]
        
        try:
            response = self.client.post("/me/events", json=event_payload)
            event_id = response.get("id")
            
            if event_id:
                block.event_id = event_id
                logger.info(f"Created event '{block.title}' at {block.start.strftime('%H:%M')} (ID: {event_id[:20]}...)")
                return event_id
            else:
                logger.error(f"Failed to create event: no ID in response")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create event '{block.title}': {e}")
            raise
    
    def create_batch(self, blocks: List[TimeBlock]) -> List[str]:
        """Create multiple timeblock events."""
        event_ids = []
        
        for block in blocks:
            try:
                event_id = self.create_timeblock_event(block)
                if event_id:
                    event_ids.append(event_id)
            except Exception as e:
                logger.error(f"Failed to create block '{block.title}': {e}")
                # Continue with other blocks
        
        logger.info(f"Created {len(event_ids)}/{len(blocks)} timeblock events")
        return event_ids
    
    def move_event(self, block: TimeBlock, new_start: datetime, new_end: datetime) -> bool:
        """Move an existing timeblock to new time."""
        if not block.event_id:
            logger.error(f"Cannot move block without event_id: {block.title}")
            return False
        
        update_payload = {
            "start": {
                "dateTime": new_start.isoformat(),
                "timeZone": self.timezone
            },
            "end": {
                "dateTime": new_end.isoformat(),
                "timeZone": self.timezone
            }
        }
        
        # Update extended props with reschedule count
        current_props = self._get_extended_props(block.event_id)
        if current_props:
            current_props["reschedule_count"] = current_props.get("reschedule_count", 0) + 1
            current_props["last_moved"] = datetime.now().isoformat()
            
            update_payload["singleValueExtendedProperties"] = [
                {
                    "id": f"String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}",
                    "value": json.dumps(current_props)
                }
            ]
        
        try:
            self.client.patch(f"/me/events/{block.event_id}", json=update_payload)
            
            # Update block object
            block.start = new_start
            block.end = new_end
            block.reschedule_count += 1
            
            logger.info(f"Moved '{block.title}' to {new_start.strftime('%H:%M')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move event '{block.title}': {e}")
            return False
    
    def mark_tentative(self, block: TimeBlock) -> bool:
        """Mark a timeblock as tentative (soft delete)."""
        if not block.event_id:
            return False
        
        try:
            self.client.patch(
                f"/me/events/{block.event_id}",
                json={"showAs": "tentative"}
            )
            logger.info(f"Marked '{block.title}' as tentative")
            return True
        except Exception as e:
            logger.error(f"Failed to mark tentative: {e}")
            return False
    
    def delete_event(self, block: TimeBlock) -> bool:
        """Delete a timeblock event."""
        if not block.event_id:
            logger.warning(f"No event_id to delete for '{block.title}'")
            return False
        
        try:
            self.client.delete(f"/me/events/{block.event_id}")
            logger.info(f"Deleted event '{block.title}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return False
    
    def get_today_timeblocks(self, target_date: date) -> List[TimeBlock]:
        """Retrieve all timeblock events for today."""
        from datetime import time as dt_time
        
        start = datetime.combine(target_date, dt_time.min)
        end = datetime.combine(target_date, dt_time.max)
        
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": "id,subject,start,end,showAs,categories,singleValueExtendedProperties",
            "$expand": f"singleValueExtendedProperties($filter=id eq 'String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}')",
            "$orderby": "start/dateTime"
        }
        
        try:
            response = self.client.get_all("/me/calendarView", params=params)
            events = response.get("value", [])
            
            blocks = []
            for event in events:
                # Check if it's a timeblock
                categories = event.get("categories", [])
                if "TimeBlock" not in categories:
                    continue
                
                # Extract extended properties
                ext_props = self._extract_extended_props(event)
                
                block = TimeBlock(
                    id=ext_props.get("timeblock_id", str(uuid4())),
                    event_id=event.get("id"),
                    start=datetime.fromisoformat(event["start"]["dateTime"]),
                    end=datetime.fromisoformat(event["end"]["dateTime"]),
                    extended_props=ext_props
                )
                
                # Restore task info if available
                if ext_props.get("source_task_id"):
                    block.task = Task(
                        id=ext_props["source_task_id"],
                        title=event.get("subject", "").replace("🎯 ", "").replace("📧 ", "").replace("🤝 ", "").replace("📋 ", ""),
                        source_type=ext_props.get("source_type", "unknown"),
                        category=ext_props.get("category", "focus_block"),
                        priority=ext_props.get("original_priority", 0.5),
                        estimated_duration=block.duration
                    )
                
                blocks.append(block)
            
            logger.info(f"Found {len(blocks)} existing timeblocks for {target_date}")
            return blocks
            
        except Exception as e:
            logger.error(f"Failed to get today's timeblocks: {e}")
            return []
    
    def mark_tentative_all_today(self, target_date: date) -> int:
        """Mark all timeblocks for today as tentative (panic button)."""
        blocks = self.get_today_timeblocks(target_date)
        
        count = 0
        for block in blocks:
            if self.mark_tentative(block):
                count += 1
        
        logger.info(f"Marked {count} timeblocks as tentative")
        return count
    
    def _get_extended_props(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get extended properties for an event."""
        try:
            response = self.client.get(
                f"/me/events/{event_id}",
                params={
                    "$expand": f"singleValueExtendedProperties($filter=id eq 'String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}')"
                }
            )
            return self._extract_extended_props(response)
        except Exception as e:
            logger.error(f"Failed to get extended props: {e}")
            return None
    
    def _extract_extended_props(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract timeblock extended properties from event."""
        ext_props_list = event.get("singleValueExtendedProperties", [])
        
        for prop in ext_props_list:
            if self.EXT_PROP_NAME in prop.get("id", ""):
                try:
                    return json.loads(prop.get("value", "{}"))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse extended properties")
                    return {}
        
        return {}
    
    def update_outcome(self, block: TimeBlock, outcome: BlockOutcome) -> bool:
        """Update the outcome of a completed/missed timeblock."""
        if not block.event_id:
            return False
        
        current_props = self._get_extended_props(block.event_id)
        if not current_props:
            return False
        
        current_props["outcome"] = outcome.value
        current_props["completed_at"] = datetime.now().isoformat()
        
        try:
            self.client.patch(
                f"/me/events/{block.event_id}",
                json={
                    "singleValueExtendedProperties": [
                        {
                            "id": f"String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}",
                            "value": json.dumps(current_props)
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update outcome: {e}")
            return False
