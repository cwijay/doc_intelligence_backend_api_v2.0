# Multi-Tenancy Evaluation Report

**Date**: 2025-12-16
**Compared To**: Glean.com-style enterprise SaaS
**Overall Rating**: 6/10 - Solid foundation, needs improvements for production multi-tenant SaaS

---

## Executive Summary

This document management platform has a solid foundation for multi-tenancy but is not enterprise-ready for a Glean.com-style SaaS deployment. The current implementation is appropriate for a small number of trusted organizations but requires architectural improvements for true multi-tenant isolation.

---

## What's Working Well

### 1. Database-Level Organization Scoping
- All core entities (Users, Documents, Folders, AuditLogs) have `organization_id` foreign key constraints
- CASCADE delete ensures clean tenant removal
- Composite indexes on `(organization_id, ...)` columns for performant tenant-scoped queries
- **Files**: `app/core/db_models.py:129-131, 192, 251, 331`

### 2. Session-Based Tenant Context
- `org_id` is embedded in session at login time and immutable
- Dependency injection pattern (`get_current_user_dict`) propagates org_id consistently
- Users cannot manipulate org_id in requests - it's server-side session state
- **Files**: `app/core/simple_auth.py:571-592`

### 3. Service Layer Query Filtering
- Every service method receives `org_id` as first parameter
- All database queries include `WHERE organization_id = :org_id`
- Consistent pattern across document, folder, and user services
- **Files**: `app/services/document/document_crud_service.py`, `app/services/folder_service.py`

### 4. Cache Tenant Isolation (Excellent)
- Cache keys include org_id: `{namespace}:{org_id}:{function_name}:{params_hash}`
- Pattern-based invalidation scoped to organization
- No cross-tenant cache pollution possible
- **File**: `app/core/cache.py:190-238`

### 5. GCS Storage Path Isolation
- Storage paths use org name as root prefix: `{org_name}/original/{folder}/{filename}`
- Folder operations maintain org-scoped paths
- **File**: `app/core/gcs_client.py`

---

## Critical Issues (Must Fix)

### Issue 1: Global Email Uniqueness

**Location**: `app/core/db_models.py:132`
```python
email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
```

**Problem**: Email is globally unique across ALL organizations. This means:
- A user cannot have accounts in multiple organizations
- Competitors can block each other's employees from signing up by registering their emails first
- Creates user enumeration vulnerability (login reveals if email exists anywhere)
- Breaks the multi-tenant model - Glean/Slack/etc. allow same email in different workspaces

**Glean Comparison**: Glean allows users to belong to multiple workspaces with the same email. Each workspace is isolated.

**Recommendation**: Change to composite unique constraint `(organization_id, email)`:
```python
__table_args__ = (
    UniqueConstraint("organization_id", "email", name="uq_user_org_email"),
    ...
)
```

### Issue 2: No Row-Level Security (RLS)

**Problem**: Tenant isolation is enforced ONLY at the application layer. A single bug in any service method could leak data across tenants.

**Risk**: If a developer forgets to add `org_id` filter in a new query, cross-tenant data access occurs silently.

**Glean Comparison**: Enterprise multi-tenant systems implement database-level RLS as defense-in-depth:
```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON documents
  USING (organization_id = current_setting('app.current_org_id'));
```

### Issue 3: Global Auth Lookup Without Org Context

**Location**: `app/services/user_service.py` - `_get_user_by_email_simple()`

**Problem**: Login searches for users by email across ALL organizations:
```python
stmt = select(UserModel).where(UserModel.email == email.lower())
# No org_id filter!
```

**Risk**: Combined with Issue 1, this could cause authentication confusion if the same email existed in multiple orgs (not currently possible, but would be after fixing Issue 1).

**Recommendation**: Require organization identifier during login (domain, org slug, or org selection).

### Issue 4: In-Memory Session Storage

**Location**: `app/core/simple_auth.py:90-93`

**Problem**: Sessions are stored in an in-memory dictionary with threading lock. This means:
- Cannot scale horizontally (multiple API instances don't share sessions)
- Server restart logs out all users
- No session persistence or clustering

**Glean Comparison**: Production multi-tenant systems use Redis/Memorystore for distributed session storage.

---

## Medium Issues (Should Fix)

### Issue 5: Users Can Only Belong to One Organization

**Current Design**: Users are scoped to exactly one organization via FK.

**Glean Model**: Glean allows users to be members of multiple workspaces and switch between them.

**Impact**: This limits your market - consultants, freelancers, and enterprise users often need access to multiple organizations.

### Issue 6: Minimal Role-Based Authorization

**Problem**: Roles exist (`admin`, `user`) but are not consistently enforced at endpoints.

**Example**: User creation endpoint doesn't validate `current_user["role"] == "admin"`:
```python
@router.post("/organizations/{org_id}/users")
async def create_user(...):
    # No role check - any authenticated user can create users?
```

### Issue 7: GCS Path Validation Gap

**Location**: `app/core/gcs_client.py:703-739` - `upload_file_to_path()`

**Problem**: Method accepts arbitrary `storage_path` without validating org ownership:
```python
def upload_file_to_path(self, storage_path: str, ...):
    blob = self.bucket.blob(storage_path)  # No org validation!
```

**Mitigation**: Currently, paths are constructed server-side, but this is an architectural weakness.

---

## Comparison to Glean.com Architecture

| Feature | Your System | Glean.com Style | Gap |
|---------|-------------|-----------------|-----|
| Tenant Isolation | App-layer filtering | Database RLS + App | Missing RLS |
| User Identity | Single-org binding | Multi-workspace | Major gap |
| Email Uniqueness | Global | Per-organization | Critical gap |
| Session Storage | In-memory | Distributed (Redis) | Scalability gap |
| Org Context in Login | None (email only) | Domain/subdomain/selector | UX gap |
| RBAC Enforcement | Partial | Consistent middleware | Gap |
| Data Residency | Single region | Per-org configuration | Future concern |
| Audit Compliance | Basic logging | Full compliance suite | Enterprise gap |

---

## Recommendations by Priority

### P0 - Critical (Before Production)
1. Change email uniqueness to per-organization
2. Add org context to login flow (subdomain, org selector, or domain lookup)
3. Move sessions to Redis/Memorystore for horizontal scaling

### P1 - High (Before Enterprise Customers)
4. Implement PostgreSQL Row-Level Security policies
5. Add consistent RBAC middleware/decorators
6. Validate GCS paths include correct org prefix

### P2 - Medium (Product Maturity)
7. Support users belonging to multiple organizations
8. Add organization switching capability
9. Implement per-org configuration/settings
10. Add rate limiting per organization

### P3 - Future (Enterprise Features)
11. Data residency controls (store org data in specific regions)
12. SSO/SAML per organization
13. Organization-level encryption keys (BYOK)
14. Compliance certifications (SOC 2, etc.)

---

## Summary

This platform has the **right architectural patterns** for multi-tenancy:
- Organization-scoped database schema
- Consistent org_id propagation via dependency injection
- Tenant-isolated caching

However, it lacks the **defense-in-depth** and **flexibility** required for a true SaaS platform:
- Single email = single org is a fundamental limitation
- Application-only isolation without database RLS is risky
- In-memory sessions don't scale

For a Glean.com-style multi-tenant platform serving diverse organizations, address P0 and P1 issues before production launch.
