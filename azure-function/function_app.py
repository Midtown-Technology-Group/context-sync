"""
Azure Function - TimeBlock Webhook Handler
Receives Exchange calendar change notifications and triggers rebalancing.
"""
import json
import logging
import os
from datetime import datetime, timedelta

import azure.functions as func
from azure.storage.queue import QueueClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("timeblock-webhook")

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main HTTP trigger for webhook handler.
    
    Handles:
    1. Subscription validation (handshake)
    2. Calendar change notifications
    3. Enqueues rebalance requests
    """
    logger.info(f"Received request: {req.method} {req.url}")
    
    # Handle subscription validation (handshake)
    validation_token = req.params.get('validationToken')
    if validation_token:
        logger.info("Subscription validation request")
        return func.HttpResponse(
            validation_token,
            status_code=200,
            headers={'Content-Type': 'text/plain'}
        )
    
    # Process change notifications
    try:
        body = req.get_json()
        notifications = body.get('value', [])
        
        logger.info(f"Processing {len(notifications)} notifications")
        
        processed = 0
        for notification in notifications:
            if _process_notification(notification):
                processed += 1
        
        logger.info(f"Enqueued {processed} rebalance requests")
        
        # Return 202 Accepted (async processing)
        return func.HttpResponse(
            json.dumps({"processed": processed}),
            status_code=202,
            headers={'Content-Type': 'application/json'}
        )
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers={'Content-Type': 'application/json'}
        )


def _process_notification(notification: dict) -> bool:
    """
    Process a single notification.
    
    Returns:
        True if rebalance was enqueued, False otherwise
    """
    try:
        # Extract notification details
        change_type = notification.get('changeType')  # created, updated, deleted
        resource_id = notification.get('resource')  # Event ID
        client_state = notification.get('clientState')  # User identifier
        event_data = notification.get('resourceData', {})
        
        logger.debug(f"Notification: {change_type} on {resource_id}")
        
        # Skip if no user identifier
        if not client_state:
            logger.warning("No clientState (user_id) in notification, skipping")
            return False
        
        # Check if this is a conflict-worthy change
        if not _is_conflicting_change(change_type, event_data):
            logger.debug("Not a conflicting change, skipping")
            return False
        
        # Get event details for deduplication
        event_id = event_data.get('id', resource_id.split('/')[-1] if resource_id else 'unknown')
        
        # Build rebalance request
        request = {
            "user_id": client_state,
            "event_id": event_id,
            "change_type": change_type,
            "timestamp": datetime.utcnow().isoformat(),
            "event_subject": event_data.get('subject', 'Unknown'),
            "event_start": event_data.get('start', {}).get('dateTime'),
            "event_end": event_data.get('end', {}).get('dateTime'),
            "strategy": "hybrid"  # Minimal for <3 conflicts, full for >=3
        }
        
        # Enqueue
        _enqueue_rebalance_request(request)
        
        logger.info(f"Enqueued rebalance for user {client_state}, event {event_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing notification: {e}", exc_info=True)
        return False


def _is_conflicting_change(change_type: str, event_data: dict) -> bool:
    """
    Determine if this change should trigger a rebalance.
    
    Rules:
    - Meeting duration must be >30 minutes
    - Skip if it's our own timeblock (we created it)
    - Only 'created' and 'updated' (time changes) trigger rebalance
    """
    # Only care about creates and time-change updates
    if change_type not in ['created', 'updated']:
        return False
    
    # Skip our own timeblocks
    categories = event_data.get('categories', [])
    if 'TimeBlock' in categories:
        logger.debug("Skipping TimeBlock category event")
        return False
    
    # Check duration >30 minutes
    try:
        start = event_data.get('start', {}).get('dateTime')
        end = event_data.get('end', {}).get('dateTime')
        
        if start and end:
            from datetime import datetime as dt
            start_dt = dt.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = dt.fromisoformat(end.replace('Z', '+00:00'))
            duration_minutes = (end_dt - start_dt).total_seconds() / 60
            
            if duration_minutes < 30:
                logger.debug(f"Meeting too short ({duration_minutes} min), skipping")
                return False
    except Exception as e:
        logger.warning(f"Could not parse event times: {e}")
        # If we can't parse, assume it's a potential conflict
        pass
    
    # Check if this is just a subject change (not time change)
    if change_type == 'updated':
        # Graph change notifications for calendar don't always include old values
        # We'll be conservative and assume any update could be a time change
        pass
    
    return True


def _enqueue_rebalance_request(request: dict) -> bool:
    """Add rebalance request to Azure Queue."""
    try:
        # Get queue connection from environment
        queue_name = os.environ.get('REBALANCE_QUEUE_NAME', 'rebalance-requests')
        
        # Use AzureWebJobsStorage connection string
        conn_str = os.environ.get('AzureWebJobsStorage')
        if not conn_str:
            # Fallback for local dev
            conn_str = os.environ.get('STORAGE_CONNECTION_STRING')
        
        if not conn_str:
            logger.error("No storage connection string found")
            # In dev mode, just log and return success
            logger.info(f"DEV MODE: Would enqueue: {json.dumps(request)}")
            return True
        
        # Connect to queue
        queue = QueueClient.from_connection_string(
            conn_str=conn_str,
            queue_name=queue_name
        )
        
        # Send message with 10-min TTL (deduplication window)
        message_text = json.dumps(request)
        queue.send_message(
            message_text,
            time_to_live=timedelta(minutes=10)
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to enqueue request: {e}", exc_info=True)
        return False
