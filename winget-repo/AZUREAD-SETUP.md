# Azure AD Authentication for Winget Repository

**⚠️ Important**: Winget CLI doesn't natively support OAuth/AzureAD authentication. This configuration enables AzureAD for browser/admin access, but winget CLI requires anonymous access to API endpoints.

## Authentication Strategy

| Access Method | Authentication | Notes |
|--------------|----------------|-------|
| **Winget CLI** | Anonymous (no auth) | Required - CLI can't handle OAuth |
| **Browser** | AzureAD | For admin/debugging |
| **API Direct** | AzureAD optional | Use function key or keep public |

## Setup Instructions

### Step 1: Create App Registration for SWA

You need a separate AzureAD app registration for the SWA authentication:

```powershell
# Create app registration for SWA auth
az ad app create --display-name "MTG Tools Winget Repo" --sign-in-audience AzureADMyOrg
```

Or via Portal:
1. Go to https://portal.azure.com
2. Azure AD → App registrations → New registration
3. Name: `MTG Tools Winget Repo`
4. Supported account types: **Accounts in this organizational directory only**
5. Redirect URI: **Single-page application (SPA)**
6. Redirect URI value: `https://mtg-tools.azurestaticapps.net/.auth/login/aad/callback`
7. Click **Register**

### Step 2: Configure Platform Settings

In the app registration:

1. Go to **Authentication** → **Platform configurations**
2. Add platform → **Single-page application**
3. Add redirect URI:
   - `https://mtg-tools.azurestaticapps.net/.auth/login/aad/callback`
   - `https://mtg-tools.azurestaticapps.net/.auth/login/aad/callback` (with www if using custom domain)

4. Under **Implicit grant and hybrid flows**, check:
   - ✅ Access tokens
   - ✅ ID tokens

5. Click **Save**

### Step 3: Get Client ID and Secret

1. **Application (client) ID**: Copy from Overview page
   - Looks like: `12345678-1234-1234-1234-123456789012`

2. **Client Secret**:
   - Go to **Certificates & secrets**
   - New client secret
   - Description: `SWA Auth`
   - Expires: 24 months
   - Click **Add**
   - **Copy the Value immediately** (you can't see it again!)

### Step 4: Configure SWA Environment Variables

In Azure Portal:
1. Go to your Static Web App → **Configuration**
2. Add these **Application settings**:

| Setting Name | Value |
|--------------|-------|
| `AAD_CLIENT_ID` | Your app registration client ID |
| `AAD_CLIENT_SECRET` | Your client secret value |

3. Click **Save**

### Step 5: Deploy with Updated Config

The `staticwebapp.config.json` already includes AzureAD configuration:

```json
{
  "auth": {
    "identityProviders": {
      "azureActiveDirectory": {
        "registration": {
          "openIdIssuer": "https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0",
          "clientIdSettingName": "AAD_CLIENT_ID",
          "clientSecretSettingName": "AAD_CLIENT_SECRET"
        }
      }
    }
  }
}
```

Deploy:
```powershell
.\scripts\deploy-winget-repo.ps1 -Name mtg-tools -ResourceGroup mtg-apps-rg
```

## Access Patterns

### 1. Browser Access (AzureAD Protected)

Navigate to `https://mtg-tools.azurestaticapps.net/`
- You'll be redirected to AzureAD login
- After login, you can browse the JSON endpoints

### 2. Winget CLI Access (Anonymous)

Winget directly accesses the API without auth:
```powershell
winget source add -n mtg-tools -a https://mtg-tools.azurestaticapps.net
winget install --source mtg-tools MidtownTechnologyGroup.WorkContextSync
```

**Note**: The API endpoints (`/index.json`, `/packageManifests/*`) remain publicly accessible because winget CLI cannot authenticate.

### 3. API Key Alternative (More Secure)

For tighter security, use Azure Functions with function keys:

1. Create Azure Function App (consumption plan - cheap)
2. Proxy requests to SWA
3. Add function key header validation
4. Update winget source to include header:

```powershell
# Not directly supported by winget, but can use:
$env:WINGET_SOURCE_HEADERS = "x-functions-key: your-key"
```

However, this requires a custom winget build or wrapper.

## Alternative: IP Restriction (Simpler)

If your team is office-based, use IP restriction instead:

```json
{
  "networking": {
    "allowedIpRanges": ["203.0.113.0/24", "198.51.100.0/24"]
  }
}
```

Add to `staticwebapp.config.json` at root level.

Get your office IP:
```powershell
Invoke-RestMethod https://api.ipify.org
```

## Security Considerations

| Approach | Pros | Cons |
|----------|------|------|
| **AzureAD (browser only)** | SSO for admin, audit logs | Winget still anonymous |
| **IP Restriction** | Simple, blocks external | Doesn't work for remote/WFH |
| **Public + Obscure** | Works everywhere | URL could leak |
| **Azure Front Door + WAF** | Enterprise grade | Cost, complexity |

## Recommended Setup

**For most teams**:
1. Use **IP restriction** if office-based
2. Add **AzureAD** for admin access/logs
3. Keep winget endpoints anonymous (required)
4. Monitor access logs in Azure

**For high security**:
1. Don't use winget for internal tools
2. Use signed MSI + Intune deployment
3. Or use network share with signed scripts

## Troubleshooting

### "AADSTS50011: The reply URL is not valid"

The redirect URI in your app registration doesn't match. Check:
- Must include: `https://your-site.azurestaticapps.net/.auth/login/aad/callback`
- Must be type: **Single-page application** (not Web!)

### "Login loop" or "Infinite redirect"

Clear browser cookies, or add to `staticwebapp.config.json`:
```json
{
  "auth": {
    "identityProviders": {
      "azureActiveDirectory": {
        "registration": {
          "openIdIssuer": "https://login.microsoftonline.com/common/v2.0"
        }
      }
    }
  }
}
```

### "401 Unauthorized" from winget

Check your `staticwebapp.config.json` - the routes should NOT have `allowedRoles` for `/index` and `/packageManifests/*`:

```json
{
  "route": "/index",
  "rewrite": "/index.json",
  // ❌ Don't add: "allowedRoles": ["authenticated"]
}
```

### Want full AzureAD protection?

You'd need to wrap winget CLI with an auth proxy, which is complex. Consider:
- Azure Virtual Desktop with pre-installed tools
- Intune company portal
- Self-hosted runner with pre-auth

## Verification

Test AzureAD auth:
```powershell
# Should redirect to login
Start-Process "https://mtg-tools.azurestaticapps.net/"

# API should work anonymously (for winget)
Invoke-RestMethod https://mtg-tools.azurestaticapps.net/index.json
```

## References

- [Azure Static Web Apps Authentication](https://docs.microsoft.com/azure/static-web-apps/authentication-custom?tabs=aad)
- [Winget REST Source](https://github.com/microsoft/winget-cli-restsource)
- [AzureAD App Registration](https://docs.microsoft.com/azure/active-directory/develop/quickstart-register-app)
