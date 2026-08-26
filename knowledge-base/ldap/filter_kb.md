# LDAP Filter Knowledge Base

## Purpose
Generate and validate LDAP filters for user search and synchronization.

## Common LDAP Filters

### By Username
```
(uid=jdoe)
(sAMAccountName=jdoe)
(cn=John Doe)
```

### By Email
```
(mail=jdoe@example.com)
(proxyAddresses=smtp:jdoe@example.com)
```

### By Group Membership
```
(memberOf=CN=Staff,OU=Groups,DC=example,DC=com)
(memberOf:1.2.840.113519.1.1.1:=CN=Developers,OU=Groups,DC=example,DC=com)
```

### By Status
```
(userAccountControl:1.2.840.113519.1.1.1.512:=512)  # Enabled accounts (Windows)
(!(accountExpires=9223372036854775807))  # Non-expiring (Active Directory)
```

### Combined Filters
```
(&(uid=*)(mail=*@example.com)(memberOf=CN=Staff,OU=Groups,DC=example,DC=com))
(|(uid=jdoe)(uid=jsmith))(objectClass=person)
```

## Attribute Mapping

### Common Attributes
| Purpose | LDAP Attribute | Example |
|---------|---------------|---------|
| Username | `uid`, `sAMAccountName` | `jdoe` |
| Email | `mail`, `proxyAddresses` | `jdoe@example.com` |
| Full Name | `cn`, `displayName`, `givenName + sn` | `John Doe` |
| Department | `department`, `company` | `Engineering` |
| Title | `title`, `jobTitle` | `Software Engineer` |
| Phone | `telephoneNumber`, `mobile` | `+1-555-0100` |
| Manager | `manager` | `cn=Jane Smith,ou=users,...` |
| Groups | `memberOf` | `CN=Staff,OU=Groups,...` |

### Custom Attributes
Map custom LDAP attributes to local fields:
```json
{
  "employee_id": "employeeNumber",
  "cost_center": "c",
  "location": "l"
}
```

## Filter Generation Patterns

### "Find users in group X"
```
(memberOf=CN={group_name},OU=Groups,DC=example,DC=com)
```

### "Find users with email at domain"
```
(&(mail=*@{domain})(objectClass=person))
```

### "Find enabled users not in disabled group"
```
(&(&(userAccountControl:1.2.840.113519.1.1.1.512:=512))(!(memberOf=CN=Disabled,OU=Groups,DC=example,DC=com))))
```

### "Find users hired after date"
```
(&(objectClass=person)(whenCreated>=20260101000000Z))
```

## Validation Rules

1. **Must start with `(` and end with `)`**
2. **Operators:** `&` (AND), `|` (OR), `!` (NOT)
3. **Conditions:** `(attr=value)`, `(attr>=value)`, `(attr<=value)`
4. **Escape special chars:** `\28` for `(`, `\29` for `)`, `\5c` for `\`
5. **Limit depth:** Maximum 10 nested conditions (performance)

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `(uid=jdoe)` without parentheses around value | `(uid=jdoe)` ✓ |
| Missing `objectClass` filter | `(&(objectClass=person)(uid=jdoe))` |
| Wrong attribute name | Check LDAP schema first |
| Unescaped special characters | Use `\28`, `\29`, `\5c` |

## AI Assistance Prompts

### Generate Filter
"Generate an LDAP filter to find all users in the 'Engineering' group"

### Validate Filter
"Validate this LDAP filter: `(&(uid=*)(mail=*@example.com))`"

### Map Attributes
"What LDAP attributes map to username, email, and full name?"

## Output Format

AI responses should include:
- Generated filter string
- Explanation of what the filter does
- Sample LDAP search command
- Expected results (if known)

Example:
```json
{
  "filter": "(memberOf=CN=Staff,OU=Groups,DC=example,DC=com)",
  "description": "Find all users who are members of the Staff group",
  "search_command": "ldapsearch -x -H ldap://dc.example.com -D 'cn=admin,dc=example,dc=com' -W '(memberOf=CN=Staff,OU=Groups,DC=example,DC=com)' uid mail cn",
  "expected_results": "All users in the Staff group"
}
```
