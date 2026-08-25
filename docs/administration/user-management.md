# User Management

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Manage users, groups, and permissions for the system. Users authenticate via local credentials or LDAP (if configured). Groups enable role-based access control.

### Access
- **Admin:** `/admin/users` — Full user management
- **Developer/Staff:** Limited to own profile

---

## User Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full system access, user management, settings, deployments |
| **Developer** | Create/edit workflows and forms, manage own content |
| **Staff** | View workflows, submit forms, view own tasks |
| **User** | View published workflows, submit forms, view own tasks |

### Role Assignment

Users are assigned one primary role. Additional group memberships provide granular permissions.

**Set role:** Admin → Users → Edit user → Role dropdown

---

## User Lifecycle

```
Create → Active → Deactivated → Deleted (soft)
                ↑
           Reactivated
```

- **Active:** Can log in and use the system
- **Deactivated:** Cannot log in, data preserved
- **Deleted:** Soft delete (recoverable for 30 days)

### Creating a User

1. Navigate to **Admin → Users**
2. Click **+ New User**
3. Fill in:
   - Username (unique, lowercase)
   - Email
   - Full name
   - Password (or "Send invite" for self-service registration)
   - Role
   - Group memberships (optional)
4. Click **Create**

### Editing a User

1. Find user in list
2. Click **Edit**
3. Update fields as needed
4. Click **Save**

**Restricted fields:**
- Username: Cannot change (unique identifier)
- Role: Admin-only change
- Password: Requires current password or admin reset

### Deactivating a User

1. Open user detail
2. Click **Deactivate**
3. Confirm

User cannot log in but retains:
- Owned workflows/forms (ownership transfers to admin on deactivation)
- Task history
- Audit trail

### Reactivating a User

1. Find deactivated user (filter by status)
2. Click **Reactivate**
3. User can log in again with original password

---

## Groups

Groups organize users for permission management.

### Built-in Groups

| Group | Purpose |
|-------|---------|
| `admin` | System administrators |
| `developer` | Workflow/form creators |
| `staff` | Reviewers and approvers |
| `user` | End users |

### Custom Groups

Create groups for:
- Department-based access (e.g., "HR Team", "IT Support")
- Project-based access (e.g., "Project Alpha")
- Role combinations (e.g., "Approvers")

**Create:** Admin → Groups → + New Group

### Group Permissions

Groups grant:
- **Workflow access:** Which workflows the group can run
- **Task access:** Which tasks group members can see/claim
- **Form access:** Which forms group members can submit

**Configure:** Edit group → Permissions tab

---

## Authentication

### Local Authentication

Username/password stored in database (hashed with bcrypt).

**Password requirements:**
- Minimum 8 characters
- Mixed case recommended
- Special characters encouraged

**Reset password:** Admin → Users → Reset password (sends email or generates temp password)

### LDAP Authentication

If LDAP is configured, users can authenticate with LDAP credentials.

**Flow:**
1. User enters username/password
2. System tries LDAP bind
3. If successful: log in (create local account if new)
4. If fails: fallback to local authentication

**See:** [LDAP Integration](./ldap-integration.md)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/users` | List users (admin/developer) |
| `POST` | `/auth/register` | Register new user |
| `PUT` | `/auth/users/{id}` | Update user (admin) |
| `DELETE` | `/auth/users/{id}` | Deactivate user (admin) |
| `POST` | `/auth/reset-password` | Reset password |
| `GET` | `/auth/me` | Get current user profile |
| `PUT` | `/auth/me/password` | Change own password |

---

## Security Considerations

1. **Strong passwords:** Enforce complexity requirements
2. **Regular audits:** Review active users quarterly
3. **Offboarding:** Deactivate immediately when employees leave
4. **Least privilege:** Assign minimum necessary roles
5. **Audit logging:** All user changes logged
6. **Session management:** Configure timeout in settings

---

## Best Practices

1. **Use groups:** Organize users by function, not just role
2. **Regular reviews:** Audit user access every 3-6 months
3. **Document roles:** Maintain a role permissions matrix
4. **Test before deploy:** Verify permissions in staging first
5. **Backup users:** Export user list before major changes
6. **Monitor logins:** Review login logs for suspicious activity

---

## Related Documentation

- [LDAP Integration](./ldap-integration.md)
- [Roles and Permissions](../features/permissions.md)
- [Security Guide](../security/overview.md)

---

*Next: [Scheduler Configuration](./scheduler.md)*
