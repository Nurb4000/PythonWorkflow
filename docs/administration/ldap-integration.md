# LDAP Integration

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

LDAP integration allows you to:
- **Authenticate** users against an existing LDAP directory
- **Synchronize** user accounts from LDAP to local database
- **Maintain** local admin/service accounts separately

Users can authenticate via LDAP (primary) or local credentials (fallback).

---

## Configuration

### Admin Settings

Navigate to **Admin → Settings → LDAP Integration**.

| Setting | Description | Required |
|---------|-------------|----------|
| **LDAP Server URL** | Connection string (e.g., `ldap://ldap.example.com:389`) | Yes |
| **Base DN** | Root of search tree (e.g., `dc=example,dc=com`) | Yes |
| **Bind DN** | Service account for searching | Yes |
| **Bind Password** | Service account password | Yes |
| **Username Attribute** | Field to search (e.g., `uid`, `sAMAccountName`) | Yes |
| **Email Attribute** | Field for email (e.g., `mail`) | No |
| **Full Name Attribute** | Field for display name (e.g., `cn`, `displayName`) | No |
| **User Filter** | LDAP filter for users (e.g., `(objectClass=person)`) | Yes |
| **Enable Auto-Sync** | Automatically sync on interval | No |
| **Sync Interval** | Hours between automatic syncs | No |

---

## Testing Connection

1. Fill in server URL, base DN, bind credentials
2. Click **Test Connection**
3. Verify success message

**Common Errors:**
- "Authentication failed" — Check bind DN/password
- "Connection refused" — Verify server URL and network access
- "Invalid base DN" — Check DN format

---

## Manual Sync

Click **Sync Users Now** to immediately sync from LDAP.

**What happens:**
1. Searches LDAP for users matching filter
2. For each user:
   - If local account exists: update email/name
   - If not: create local account with LDAP data
3. Returns count of created/updated users

**Notes:**
- Synced users cannot change password via web UI (authenticates via LDAP)
- Local admin accounts remain unaffected
- Sync is idempotent (safe to run multiple times)

---

## Authentication Flow

When a user logs in:

1. **Try LDAP authentication:**
   - Bind to LDAP with username/password
   - If successful: log in user (create local account if needed)
   
2. **Fallback to local authentication:**
   - If LDAP not configured or bind fails
   - Check local username/password

**Result:** Users can log in via LDAP OR local credentials.

---

## User Attributes Mapping

| LDAP Attribute | Local Field | Example |
|----------------|-------------|---------|
| `uid` / `sAMAccountName` | `username` | `jdoe` |
| `mail` | `email` | `jdoe@example.com` |
| `cn` / `displayName` | `full_name` | `John Doe` |
| `memberOf` | `groups` | `CN=Staff,OU=Groups,...` |

**Custom mapping:** Edit attributes in Settings to match your LDAP schema.

---

## Security Considerations

1. **Use LDAPS (LDAP over SSL):** Change URL to `ldaps://` for encrypted connections
2. **Service account permissions:** Bind DN should have read-only access to user objects
3. **Password policy:** LDAP passwords not stored locally (auth via bind)
4. **Sync frequency:** Balance between freshness and directory load

---

## Troubleshooting

### Users not appearing after sync

**Check:**
- User filter matches your LDAP schema
- Bind DN has read access to user objects
- Base DN is correct root for user search

### Authentication fails for LDAP users

**Check:**
- LDAP server URL is accessible from backend container
- Bind credentials are valid
- Username attribute matches your LDAP schema

### Sync creates duplicate users

**Check:**
- Username attribute is unique in LDAP
- No manual local accounts with same username

---

## Mock LDAP for Testing

Use the included mock LDAP server for development:

```bash
# Start mock LDAP
docker compose -f docker-compose.ldap-test.yml up -d

# Configuration for mock server
Server URL: ldap://localhost:1389
Base DN: dc=test,dc=example,dc=com
Bind DN: cn=admin,dc=test,dc=example,dc=com
Bind Password: admin

# Test users
Username: jdoe, Password: password123
Username: jsmith, Password: password456
```

See `docker-compose.ldap-test.yml` and `tests/ldap/users.ldif`.

---

## Related Documentation

- [User Management](./user-management.md)
- [AI Configuration](./ai-configuration.md)
- [Settings Guide](../getting-started/settings.md)

---

*Next: [User Management](./user-management.md)*
