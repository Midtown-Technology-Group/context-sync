# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Active |

## Reporting Security Issues

If you discover a security vulnerability, please email **security@midtowntg.com**.

Do NOT open a public issue for security bugs.

## Credentials & Authentication

### Microsoft Graph Authentication

This tool uses Microsoft Authentication Library (MSAL) with these modes:
- **Windows Authentication Manager (WAM)** - Recommended, uses Windows credentials
- **Device Code Flow** - For remote/SSH scenarios
- **Azure CLI** - If already authenticated via `az login`

### Required Credentials

Create `config.json` in the application directory:

```json
{
  "tenant_id": "your-tenant-id",
  "client_id": "your-client-id",
  "vault_path": "/path/to/knowledge/graph"
}
```

**Getting credentials:**
1. Register app at [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Enable Microsoft Graph permissions: `Mail.Read`, `Calendars.Read`, `Chat.Read`
3. Copy Application (client) ID and Directory (tenant) ID

### Credential Storage

- **Tenant ID / Client ID**: Stored in `config.json` (not secrets, but organization identifiers)
- **Access Tokens**: DPAPI-encrypted on Windows, stored in `~/.config/work-context-sync/token_cache.bin`
- **Refresh Tokens**: Encrypted, rotated automatically by MSAL

### Security Best Practices

1. **File Permissions**: Set `config.json` to user-only access (0600 on Linux/macOS)
2. **Token Cache**: Never share `token_cache.bin` between users
3. **Least Privilege**: Use application with minimal required Graph permissions
4. **Rotate**: Periodically revoke and re-authenticate tokens

## Data Handling

### What Data is Accessed

- **Email**: Metadata only (subject, to, from, sent date) unless `include_body: true`
- **Calendar**: Meeting titles, times, attendees
- **Teams Chat**: Message previews only (not full content by default)
- **Tasks**: Microsoft To Do tasks and flagged emails

### Data Storage

All data is stored **locally** in your knowledge graph:
- Markdown files in `pages/work-context___*.md`
- JSON sidecars (optional, for raw API responses)
- No data sent to third parties except Microsoft Graph API

### Retention

- Synced data: Controlled by your knowledge graph retention
- Token cache: Valid until refresh token expires (typically 90 days)
- Logs: No persistent logging of sensitive data

## Network Security

- All API calls use HTTPS/TLS 1.2+
- Certificate validation enabled (no insecure mode)
- Token refresh happens securely via Microsoft identity platform

## Audit & Logging

Sensitive data is masked in logs:
- Email addresses: `th***@example.com`
- Access tokens: `[REDACTED]`
- Client secrets: Never logged

## Dependencies

Key security-related dependencies:
- `msal` - Microsoft Authentication Library (Microsoft maintained)
- `pydantic` - Input validation and serialization
- `cryptography` - Token encryption

Run `pip check` and keep dependencies updated.

## Least Privilege Permissions

This tool requires minimal Graph API permissions:

| Permission | Purpose | Admin Consent Required |
|------------|---------|------------------------|
| `Mail.Read` | Read email metadata | No |
| `Calendars.Read` | Read calendar events | No |
| `Chat.Read` | Read chat message previews | No |
| `Tasks.Read` | Read To Do tasks | No |
| `User.Read` | Read basic profile | No |

No write permissions required.

## Development Security

When developing/contribution:
1. Never commit `config.json` (it's gitignored)
2. Use `config.example.json` as template
3. Run `bandit -r src/` before submitting
4. Test with mock data, not production credentials

## Compliance Notes

- **GDPR**: Data remains in your tenant; local processing only
- **SOX**: No financial data access
- **HIPAA**: No PHI access by default

For enterprise deployments, review with your security team.
