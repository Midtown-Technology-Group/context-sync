# Azure Function for TimeBlock Webhook Handler
# This directory contains the Azure Function that receives Exchange webhooks
# and triggers rebalancing when calendar conflicts are detected.

## Structure

```
azure-function/
├── function_app.py          # Main function app with HTTP trigger
├── host.json                # Function host configuration
├── local.settings.json      # Local development settings (not committed)
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Deployment

1. Install Azure Functions Core Tools:
   ```bash
   npm install -g azure-functions-core-tools@4
   ```

2. Create virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Test locally:
   ```bash
   func start
   ```

4. Deploy to Azure:
   ```bash
   func azure functionapp publish <function-app-name>
   ```

## Webhook Registration

After deployment, register the webhook with Microsoft Graph:

```powershell
# Get the function URL
$webhookUrl = "https://<function-app-name>.azurewebsites.net/api/webhook"

# Register subscription (run from work-context-sync with valid token)
POST https://graph.microsoft.com/v1.0/subscriptions
{
  "changeType": "created,updated,deleted",
  "notificationUrl": "<webhookUrl>",
  "resource": "/me/events",
  "expirationDateTime": "2026-05-22T11:00:00.0000000Z",
  "clientState": "<user-id-or-secret>"
}
```

## Environment Variables

Required in Azure Portal > Function App > Configuration:

- `REBALANCE_QUEUE_NAME` - Name of the queue (default: "rebalance-requests")
- `AzureWebJobsStorage` - Storage connection string (auto-set by ARM template)
- `WEBHOOK_SECRET` - Secret for validating webhooks
