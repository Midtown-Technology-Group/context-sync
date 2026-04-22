# TimeBlock Power Automate Flows

These Power Automate flows handle user notifications and interactions for the TimeBlock system.

## Flow 1: Missed Block Notification

### Trigger
HTTP Request from work-context-sync CLI (when `--check-missed` detects passed blocks)

### Flow Steps

```
1. When a HTTP request is received
   Method: POST
   Request Body JSON Schema:
   {
     "type": "object",
     "properties": {
       "user_teams_id": {"type": "string"},
       "missed_blocks": {
         "type": "array",
         "items": {
           "type": "object",
           "properties": {
             "title": {"type": "string"},
             "scheduled_start": {"type": "string"},
             "scheduled_end": {"type": "string"},
             "block_id": {"type": "string"}
           }
         }
       }
     }
   }

2. Delay (Wait 15 minutes for grace period)
   Count: 15
   Unit: Minute

3. For each missed_block in missed_blocks:
   
   a. Post adaptive card in chat or channel (Teams)
      Post As: Flow bot
      Post In: Chat with Flow bot
      Recipient: user_teams_id
      
      Adaptive Card JSON:
      {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
          {
            "type": "TextBlock",
            "text": "⏰ Missed Time Block",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Attention"
          },
          {
            "type": "TextBlock",
            "text": "You didn't get to: **@{items('missed_blocks')?['title']}**",
            "wrap": true
          },
          {
            "type": "TextBlock",
            "text": "Scheduled: @{items('missed_blocks')?['scheduled_start']} - @{items('missed_blocks')?['scheduled_end']}",
            "isSubtle": true,
            "spacing": "Small"
          },
          {
            "type": "TextBlock",
            "text": "What would you like to do?",
            "weight": "Bolder",
            "spacing": "Medium"
          }
        ],
        "actions": [
          {
            "type": "Action.Submit",
            "title": "📅 Reschedule Today",
            "data": {
              "action": "reschedule_today",
              "block_id": "@{items('missed_blocks')?['block_id']}",
              "user_id": "@{triggerBody()?['user_teams_id']}"
            },
            "style": "positive"
          },
          {
            "type": "Action.Submit",
            "title": "📆 Move to Tomorrow",
            "data": {
              "action": "reschedule_tomorrow",
              "block_id": "@{items('missed_blocks')?['block_id']}",
              "user_id": "@{triggerBody()?['user_teams_id']}"
            }
          },
          {
            "type": "Action.Submit",
            "title": "✅ Mark Done Anyway",
            "data": {
              "action": "mark_complete",
              "block_id": "@{items('missed_blocks')?['block_id']}",
              "user_id": "@{triggerBody()?['user_teams_id']}"
            }
          },
          {
            "type": "Action.Submit",
            "title": "🗑️ Delete Block",
            "data": {
              "action": "delete",
              "block_id": "@{items('missed_blocks')?['block_id']}",
              "user_id": "@{triggerBody()?['user_teams_id']}"
            },
            "style": "destructive"
          }
        ]
      }

4. (Optional) Send email if no Teams response
   
5. Response (for webhook caller)
   Status Code: 200
   Body: {"notified": true, "blocks_count": @{length(body('missed_blocks'))}}
```

## Flow 2: Rebalance Complete Notification

### Trigger
Azure Function HTTP call after rebalancing completes

### Flow Steps

```
1. When a HTTP request is received
   
2. Post message in chat or channel (Teams)
   Recipient: @{triggerBody()?['user_teams_id']}
   
   Message:
   🔄 Auto-rebalanced @{length(triggerBody()?['changes'])} blocks
   
   @{join(
     map(
       triggerBody()?['changes'], 
       concat(
         '🔄 **', item()?['block']?['title'], '**', 
         '\n   ', 
         if(equals(item()?['old_time'], null), 'unscheduled', item()?['old_time']),
         ' → ',
         if(equals(item()?['new_time'], null), 'tomorrow', item()?['new_time'])
       )
     ), 
     '\n\n'
   )}
   
   [View Calendar] button linking to Outlook

3. (Optional) If unscheduled_tasks > 0:
   Add text: "⚠️ @{length(triggerBody()?['unscheduled_tasks'])} tasks deferred to tomorrow"
```

## Flow 3: Handle User Response (Teams Button Click)

### Trigger
When someone responds to an adaptive card (Teams)

### Flow Steps

```
1. When someone responds to an adaptive card
   
2. Parse response data:
   - action: reschedule_today | reschedule_tomorrow | mark_complete | delete
   - block_id
   - user_id

3. Switch based on action:
   
   Case "reschedule_today":
   - HTTP POST to Azure Function: /api/reblock
     Body: {user_id, block_id, action: "reschedule", target: "today"}
   - Send confirmation: "📅 Finding time for you today..."
   
   Case "reschedule_tomorrow":
   - HTTP POST to Azure Function: /api/reblock
     Body: {user_id, block_id, action: "reschedule", target: "tomorrow"}
   - Send confirmation: "📆 Moved to tomorrow's schedule"
   
   Case "mark_complete":
   - HTTP POST to work-context-sync API (or direct Graph call)
     Update Exchange event extended properties: outcome=completed
   - Send confirmation: "✅ Marked complete!"
   
   Case "delete":
   - HTTP POST to Graph API: DELETE /me/events/{block_id}
   - Send confirmation: "🗑️ Block deleted"

4. Log action for learning system
```

## Import Instructions

### Method 1: Manual Build (Recommended)

1. Go to https://make.powerautomate.com
2. Create > Instant cloud flow
3. Add the triggers and actions as described above
4. Save and test with work-context-sync CLI

### Method 2: Package Import (When Export Available)

1. Download `TimeBlock-Flows.zip` (when available)
2. Solutions > Import
3. Select the ZIP file
4. Configure connections (Teams, Outlook)
5. Activate

## Connection Requirements

- Microsoft Teams (Bot or Flow)
- Outlook (for email fallback)
- HTTP (for callbacks to Azure Function)

## Testing

Test the flows with curl:

```bash
# Test missed block notification
curl -X POST https://your-flow-trigger-url \
  -H "Content-Type: application/json" \
  -d '{
    "user_teams_id": "thomas@midtowntg.com",
    "missed_blocks": [
      {
        "title": "SonarQube analysis",
        "scheduled_start": "10:00",
        "scheduled_end": "11:30",
        "block_id": "abc-123"
      }
    ]
  }'
```

## Integration with work-context-sync

Add to `config.json`:

```json
{
  "timeblock": {
    "power_automate": {
      "missed_block_webhook_url": "https://prod-XX.westus.logic.azure.com/workflows/...",
      "rebalance_webhook_url": "https://prod-XX.westus.logic.azure.com/workflows/...",
      "enabled": true
    }
  }
}
```
