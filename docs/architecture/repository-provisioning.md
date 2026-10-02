# Repository Provisioning Architecture

## Technical Design, Reliability, Security, and Recovery Requirements

**Project:** `SCSSA-UoK/project-requests`
**System:** Automated Student Project Repository Provisioning
**Status:** Proposed
**Related Issue:** #56 — GitHub Organization Limitations
**Last Updated:** 2026-10-02

---

## 1. Overview

The `project-requests` system automates the provisioning of GitHub repositories for approved student projects.

The system receives project requests through GitHub Issues and, after validation and authorization, provisions the required GitHub repository and project members.

The current provisioning process performs several independent operations through the GitHub API:

1. Validate the request.
2. Authorize the approving administrator.
3. Determine the repository/project identifier.
4. Create the repository.
5. Add the project lead.
6. Add project members.
7. Update the central project registry.
8. Report the result.

Because these operations are separate API calls, the workflow is **not transactional**. A failure can occur after some operations have succeeded.

Therefore, the provisioning system must be designed around the following principles:

> **The provisioning workflow must be stateful, idempotent, recoverable, auditable, and verifiable.**

A failed workflow should be safe to retry without creating duplicate repositories, duplicate registry entries, or inconsistent project membership.

---

# 2. Goals

The architecture should provide:

* Reliable repository provisioning.
* Safe concurrent request handling.
* Idempotent workflow execution.
* Recovery from partial failures.
* Explicit provisioning states.
* Post-provisioning verification.
* GitHub API retry handling.
* Least-privilege authentication.
* Registry consistency.
* Auditability.
* Operational reconciliation.
* Safe workflow re-runs.

---

# 3. Non-Goals

The provisioning system is not intended to:

* Give students organization-level administrative privileges.
* Automatically perform destructive cleanup without authorization.
* Act as a general GitHub organization management platform.
* Guarantee zero failures.
* Treat GitHub Actions as a transactional database.
* Depend on manual intervention for normal recovery.

---

# 4. Current Architecture

The current system consists primarily of:

```text
GitHub Issue
     │
     ▼
Validation Workflow
     │
     ▼
Approval
     │
     ▼
Provisioning Workflow
     │
     ├── Create Repository
     │
     ├── Add Project Lead
     │
     ├── Add Members
     │
     └── Update Project Registry
```

Relevant components include:

```text
.github/workflows/issue-validate.yml
.github/workflows/issue-provision.yml

scripts/issue_validate.py
scripts/issue_provision.py
```

The project registry is maintained separately in the `scssa-project-records` repository.

---

# 5. Architectural Risks

The main risks identified in the current approach are:

| Risk                                         | Impact                              |
| -------------------------------------------- | ----------------------------------- |
| Concurrent provisioning                      | Duplicate project/group identifiers |
| Workflow timeout                             | Unknown provisioning state          |
| Repository created but member addition fails | Partial project configuration       |
| Registry update fails                        | GitHub/registry inconsistency       |
| Workflow re-run                              | Duplicate operations                |
| API rate limiting                            | Provisioning failure                |
| Transient API errors                         | Unnecessary workflow failures       |
| Manual repository modification               | State drift                         |
| Token over-permission                        | Security risk                       |
| Lack of verification                         | False successful provisioning       |

These risks should be addressed as part of the provisioning architecture.

---

# 6. Billing and Capacity

## 6.1 GitHub Actions

The system is intended to operate within GitHub's available free-tier resources.

Provisioning workflows are expected to be lightweight because they primarily execute Python code and GitHub API requests.

However, the number of repositories that can be provisioned should not be calculated purely from the nominal workflow duration.

Actual Actions consumption can vary because of:

* Runner startup time.
* Workflow overhead.
* API retries.
* Failed executions.
* Repeated workflow runs.
* Future workflow changes.
* Dependency installation.
* Debugging/recovery runs.

Therefore:

> Repository-per-month estimates should be treated as approximate capacity estimates, not guaranteed limits.

The organization should monitor GitHub Actions usage as project volume increases.

---

## 6.2 Repository Storage

The project registry contains lightweight structured data such as:

* CSV files.
* Excel files.
* Markdown documentation.
* Configuration files.

These should not normally create significant storage pressure.

However, large generated files, binaries, build artifacts, logs, or unnecessary workflow artifacts should not be stored in the project registry repository.

Repository storage and GitHub Actions artifact storage should be treated as separate resource categories.

---

# 7. Concurrency Control

## 7.1 Problem

Multiple project approvals may occur at approximately the same time.

For example:

```text
Current highest group = G04

Request A:
calculate next group → G05

Request B:
calculate next group → G05
```

Both workflows may attempt to provision the same logical group.

This can result in:

```text
Request A → G05 → SUCCESS

Request B → G05 → CONFLICT
```

---

## 7.2 GitHub Actions Concurrency

The provisioning workflow should use a concurrency group:

```yaml
concurrency:
  group: repository-provisioning
  cancel-in-progress: false
```

This causes provisioning workflows to wait for one another instead of running simultaneously.

`cancel-in-progress: false` is important because an approved provisioning request should not be silently cancelled when another request is approved.

---

## 7.3 Concurrency Is Not the Complete Solution

Concurrency control should not be treated as the only protection.

Before repository creation, the workflow must re-check the desired repository name.

Recommended flow:

```text
Acquire provisioning lock
        │
        ▼
Determine expected repository
        │
        ▼
Check whether repository exists
        │
        ├── YES → Reconcile existing state
        │
        └── NO → Create repository
```

This protects against repositories created:

* By previous workflow executions.
* Manually by administrators.
* By recovery attempts.
* By other automation.

---

# 8. Repository Identifier Allocation

## 8.1 Problem

A strategy such as:

```text
highest existing group number + 1
```

is simple but creates a dependency on the current GitHub repository state.

Example:

```text
G01
G02
G03

Next = G04
```

This becomes problematic when:

* A repository is deleted.
* A workflow partially succeeds.
* A repository exists but is missing from the registry.
* A group number is skipped.
* A previous workflow is retried.
* Manual changes occur.

---

## 8.2 Stable Allocation

Each request should receive a stable provisioning identifier.

For example:

```text
REQ-2026-0056
```

The same request must retain the same identifier across workflow retries.

The workflow should never allocate a different project identifier merely because provisioning was retried.

---

## 8.3 Allocation Requirements

The allocation process should:

1. Identify the request.
2. Validate the requested project information.
3. Determine the required project/group identifier.
4. Check whether that identifier is already associated with another request.
5. Persist the allocation.
6. Reuse the same allocation on subsequent executions.

---

# 9. Provisioning Request ID

Every provisioning request should have a stable unique identifier.

Example:

```text
REQ-2026-0056
```

This identifier should be associated with:

* GitHub Issue.
* Repository.
* Project/group identifier.
* Provisioning state.
* Workflow runs.
* Registry entry.
* Audit information.

Example:

```text
Request ID:
REQ-2026-0056

Issue:
#56

Repository:
e26-3yp-G05-example

Status:
COMPLETED
```

The request ID provides a correlation mechanism across the entire provisioning lifecycle.

---

# 10. Idempotent Provisioning

## 10.1 Definition

An operation is idempotent when executing it multiple times produces the same intended final state.

For example:

```text
First run:
Repository does not exist
        ↓
Create repository
        ↓
SUCCESS
```

Second run:

```text
Repository already exists
        ↓
Verify existing repository
        ↓
Continue provisioning
```

The second run must not attempt to create an unnecessary duplicate repository.

---

## 10.2 Repository Creation

The workflow should check whether the repository already exists before creation.

Conceptually:

```python
repository = get_repository(repository_name)

if repository:
    verify_repository(repository)
else:
    create_repository(repository_name)
```

The exact implementation should follow the existing project coding standards.

---

## 10.3 Collaborator Configuration

Collaborator operations should also be idempotent.

Instead of assuming:

```text
add collaborator
```

always needs to happen, the workflow should determine the current state.

Example:

```text
Member 1 → already configured
Member 2 → already configured
Member 3 → missing
Member 4 → already configured
```

The workflow should only perform the required correction:

```text
Member 3 → add/configure
```

---

## 10.4 Registry Updates

Registry updates should not blindly append records.

Avoid a model equivalent to:

```text
append(project)
```

without checking whether the project already exists.

Instead:

```text
Find project by stable identifier
        │
        ├── Exists → verify/update
        │
        └── Missing → create
```

This prevents duplicate registry entries after workflow retries.

---

# 11. Provisioning State Machine

Provisioning should be represented as a sequence of explicit states.

Recommended lifecycle:

```text
PENDING
   │
   ▼
VALIDATED
   │
   ▼
PROVISIONING
   │
   ▼
REPOSITORY_CREATED
   │
   ▼
MEMBERS_CONFIGURED
   │
   ▼
REGISTERED
   │
   ▼
VERIFIED
   │
   ▼
COMPLETED
```

Failure states:

```text
FAILED
PARTIAL_FAILURE
```

---

# 12. State Definitions

## PENDING

The request exists but provisioning has not started.

---

## VALIDATED

The request has passed:

* Input validation.
* Project information validation.
* Authorization checks.
* Required-field checks.

---

## PROVISIONING

The system is actively creating/configuring project resources.

---

## REPOSITORY_CREATED

The expected GitHub repository exists and basic repository validation has passed.

---

## MEMBERS_CONFIGURED

The project lead and required collaborators have been configured.

---

## REGISTERED

The project registry has been updated successfully.

---

## VERIFIED

All required resources have been checked against the expected state.

---

## COMPLETED

Provisioning and verification have successfully finished.

---

## PARTIAL_FAILURE

Some provisioning operations succeeded while another required operation failed.

Example:

```text
Repository → SUCCESS
Lead → SUCCESS
Member 2 → SUCCESS
Member 3 → FAILURE
Registry → NOT ATTEMPTED
```

---

## FAILED

The workflow cannot safely continue automatically.

This state should include enough information to determine what failed and whether manual intervention is required.

---

# 13. Partial Failure Recovery

## 13.1 Problem

The provisioning process consists of multiple independent API calls.

For example:

```text
Create repository
      ↓
Add lead
      ↓
Add member 2
      ↓
Add member 3
      ↓
Add member 4
      ↓
Update registry
      ↓
Verify
```

There is no single transaction covering all operations.

Therefore, the system must assume that failures can happen between any two steps.

---

## 13.2 Example

Suppose:

```text
Create repository → SUCCESS
Add lead          → SUCCESS
Add member 2      → SUCCESS
Add member 3      → TIMEOUT
```

The repository now exists.

The correct recovery process is not:

```text
Delete everything
Create everything again
```

Instead:

```text
Inspect current state
        ↓
Repository exists
        ↓
Lead exists
        ↓
Member 2 exists
        ↓
Member 3 missing
        ↓
Add member 3
        ↓
Continue provisioning
```

---

# 14. Ambiguous API Failures

A particularly important case occurs when an API request times out.

Example:

```text
Create repository
       ↓
GitHub creates repository
       ↓
Network timeout
       ↓
Workflow receives no response
```

The workflow cannot safely assume that repository creation failed.

It must first check:

```text
Does repository exist?
```

If it exists:

```text
Reuse and continue
```

If it does not:

```text
Attempt creation
```

This pattern should be applied to other operations where the result may be ambiguous.

---

# 15. Manual Recovery

Manual intervention should be an exception.

It may be required when:

* State is ambiguous.
* Conflicting repositories exist.
* Permissions cannot be corrected automatically.
* Registry data conflicts with GitHub state.
* An external administrator changed the project unexpectedly.
* GitHub API behavior prevents safe automated recovery.

When manual intervention occurs, the issue/workflow should document:

* What failed.
* What state already exists.
* What was manually corrected.
* What remains to be verified.

---

# 16. Post-Provisioning Verification

Provisioning should not be considered successful merely because API requests returned successfully.

The workflow should explicitly verify the final state.

---

## 16.1 Repository Verification

Check:

* Repository exists.
* Repository name is correct.
* Repository belongs to the expected organization.
* Repository visibility is correct.
* Required initial files/configuration exist.

---

## 16.2 Project Lead Verification

Check:

* Lead account exists.
* Lead has the expected repository permission.
* Lead corresponds to the approved request.

---

## 16.3 Member Verification

For every requested member:

* Account exists.
* Member has the expected permission.
* Member is associated with the correct repository.

---

## 16.4 Registry Verification

Check:

* Project exists in the registry.
* Repository name matches.
* Request ID matches.
* Project/group identifier matches.
* Lead/member information is consistent.

---

# 17. Verification as a Separate Stage

The recommended flow is:

```text
Provision
    ↓
Verify
    ↓
COMPLETED
```

Not:

```text
API calls succeeded
    ↓
COMPLETED
```

Example:

```text
Repository creation → SUCCESS
Members             → SUCCESS
Registry            → SUCCESS

Verification:
Repository           → PASS
Lead                 → PASS
Members              → PASS
Registry             → PASS

Final state:
COMPLETED
```

If verification fails:

```text
PARTIAL_FAILURE
```

or:

```text
FAILED
```

depending on whether automated recovery is possible.

---

# 18. GitHub API Resilience

GitHub API requests can fail because of transient conditions.

Potential failures include:

* HTTP 429.
* HTTP 500.
* HTTP 502.
* HTTP 503.
* HTTP 504.
* Network timeout.
* Connection failure.

The provisioning system should implement bounded retry logic where retrying is safe.

---

# 19. Retry Strategy

Recommended conceptual flow:

```text
API request
    │
    ▼
Success?
 ├── YES → Continue
 │
 └── NO
      │
      ▼
Is failure retryable?
 ├── NO → Handle failure
 │
 └── YES
      │
      ▼
Wait using backoff
      │
      ▼
Retry
```

Use bounded exponential backoff.

Example:

```text
Attempt 1
   ↓
1 second
   ↓
Attempt 2
   ↓
2 seconds
   ↓
Attempt 3
   ↓
4 seconds
```

The exact limits should be selected based on GitHub API behavior and workflow runtime constraints.

---

# 20. Safe Retry Rules

Not every operation should simply be repeated.

Safe example:

```text
GET repository
```

can normally be retried.

More sensitive example:

```text
POST create repository
```

should be handled carefully.

If the request times out:

```text
Create repository
       ↓
TIMEOUT
       ↓
Check whether repository exists
       │
       ├── YES → Treat as created
       │
       └── NO → Retry creation
```

This prevents duplicate-resource attempts.

---

# 21. Authentication and Authorization

The provisioning workflow should use a tightly scoped authentication mechanism.

The project already uses a GitHub App installation token model.

The implementation should maintain least privilege.

Credentials must never be:

* Hard-coded.
* Committed to the repository.
* Printed in logs.
* Included in issue comments.
* Stored in generated documentation.
* Included in workflow output.

---

# 22. Secret Handling

Workflow secrets should be passed only to the processes that require them.

Avoid unnecessarily exposing secrets through:

```yaml
env:
  TOKEN: ...
```

at the job level when only one step needs the credential.

Prefer the smallest practical scope.

Never log the value of a credential for debugging.

---

# 23. Student Permission Boundaries

Students should receive only the repository-level permissions required by the project.

The provisioning system must not grant:

```text
Organization Owner
Organization Administrator
Organization-wide administrative access
```

to student accounts.

Expected model:

```text
Organization
    │
    ├── Automation Identity
    │
    └── Project Repository
           │
           ├── Project Lead
           │      └── Expected administrative permission
           │
           ├── Member 2
           │      └── Expected write permission
           │
           ├── Member 3
           │      └── Expected write permission
           │
           └── Member 4
                  └── Expected write permission
```

The exact permission model must follow the organization's approved policy.

---

# 24. Registry Consistency

The project registry and GitHub organization can temporarily become inconsistent.

Example:

```text
GitHub:
Repository EXISTS

Registry:
Entry MISSING
```

Another example:

```text
GitHub:
e26-3yp-G05-project-a

Registry:
e26-3yp-G05-project-b
```

The architecture must define how these inconsistencies are handled.

---

# 25. Registry as a Source of Truth

The system should explicitly document which component is authoritative.

Possible approaches:

### Model A — GitHub as Source of Truth

GitHub repository state is authoritative.

The registry becomes a record/report generated from GitHub state.

### Model B — Registry as Source of Truth

The registry defines the expected project configuration.

GitHub is configured to match the registry.

### Model C — Dedicated Database

A database becomes the authoritative state store.

The database tracks:

```text
Request
Project
Repository
Members
Provisioning State
Workflow Attempts
Errors
Verification
```

The CSV can then be generated as an export.

For the current system, continuing with the existing project registry is reasonable, but the source-of-truth policy should be explicitly documented.

---

# 26. Registry Update Strategy

Registry writes should be idempotent.

Conceptually:

```text
Find project by Request ID
        │
        ├── Found
        │     ↓
        │   Verify/update
        │
        └── Not Found
              ↓
            Create
```

Do not blindly append a new record during every retry.

---

# 27. Auditability

Every provisioned project should be traceable back to its original request.

Recommended audit information:

```text
Request ID
Issue Number
Repository
Project/Group ID
Project Lead
Members
Provisioning timestamp
Workflow run
Current state
Final status
```

Example:

```text
Request ID: REQ-2026-0056
Issue: #56
Repository: e26-3yp-G05-example
Status: COMPLETED
```

This makes troubleshooting and administrative auditing easier.

---

# 28. Issue and Repository Correlation

The originating GitHub Issue should remain associated with the provisioned repository.

The system should be able to answer:

```text
Which request created this repository?
```

and:

```text
Which repository belongs to this request?
```

The stable request ID provides this relationship.

---

# 29. Scheduled Reconciliation

Even if provisioning succeeds, project state can change later.

For example:

```text
Provisioning completed
       ↓
Administrator modifies collaborators
       ↓
Expected state != actual state
```

A scheduled reconciliation workflow can identify these differences.

---

# 30. Reconciliation Process

Conceptual architecture:

```text
Expected State
      │
      ├── Repository exists?
      ├── Correct name?
      ├── Correct visibility?
      ├── Lead exists?
      ├── Members exist?
      ├── Correct permissions?
      └── Registry entry exists?
              │
              ▼
         Reconciliation
              │
        ┌─────┴─────┐
        ▼           ▼
      Match      Mismatch
        │           │
        ▼           ▼
     Report     Repair/Review
```

The reconciliation workflow should be conservative.

Destructive actions should not be performed automatically unless explicitly authorized.

---

# 31. Recommended End-to-End Architecture

The target architecture is:

```text
                         GitHub Issue
                              │
                              ▼
                         Validation
                              │
                              ▼
                        Authorization
                              │
                              ▼
                     Request / State ID
                              │
                              ▼
                       ID Allocation
                              │
                              ▼
                  Acquire Concurrency Lock
                              │
                              ▼
                  Reconcile Existing State
                              │
                              ▼
                   Create/Verify Repository
                              │
                              ▼
                    Configure Collaborators
                              │
                              ▼
                       Update Registry
                              │
                              ▼
                          Verify
                              │
                              ▼
                         COMPLETED
```

Failure path:

```text
                      Any Failure
                           │
                           ▼
                  Identify Current State
                           │
                           ▼
                    Is Recovery Safe?
                       /          \
                     YES            NO
                      │              │
                      ▼              ▼
                Retry / Resume     FAILED
                      │
                      ▼
                   Verify
                      │
                      ▼
                  COMPLETED
```

---

# 32. Recommended Provisioning Algorithm

Conceptually:

```text
1. Receive approved request.

2. Validate request.

3. Verify approving actor is authorized.

4. Obtain stable request ID.

5. Determine expected repository/project identifier.

6. Acquire provisioning concurrency lock.

7. Inspect current GitHub state.

8. If repository does not exist:
       create repository.

9. If repository exists:
       verify it belongs to the expected request.

10. Configure project lead.

11. Configure project members.

12. Update project registry idempotently.

13. Verify repository.

14. Verify collaborators.

15. Verify registry.

16. Record COMPLETED state.

17. Report result.
```

If any step fails:

```text
1. Record failure.

2. Determine what operations already succeeded.

3. Determine whether the failure is retryable.

4. If safe:
       retry/resume.

5. Otherwise:
       mark PARTIAL_FAILURE or FAILED.

6. Provide enough information for recovery.
```

---

# 33. State-Aware Recovery Example

Suppose the workflow ends in:

```text
Request:
REQ-2026-0056

Repository:
EXISTS

Lead:
EXISTS

Member 2:
EXISTS

Member 3:
MISSING

Member 4:
MISSING

Registry:
MISSING
```

A retry should execute:

```text
Repository → SKIP
Lead       → SKIP
Member 2   → SKIP
Member 3   → ADD
Member 4   → ADD
Registry   → CREATE
Verification → RUN
```

Final state:

```text
COMPLETED
```

This is the expected behavior of an idempotent system.

---

# 34. Recommended Error Classification

Errors should be classified rather than treated identically.

## Validation Error

The request itself is invalid.

Example:

```text
Missing project lead
```

Action:

```text
Stop provisioning.
Request correction.
```

---

## Authorization Error

The actor does not have permission to approve/provision.

Action:

```text
Stop immediately.
```

---

## Conflict Error

The expected repository/project identifier is already associated with another project.

Action:

```text
Do not overwrite.
Require resolution.
```

---

## Transient API Error

Example:

```text
429
503
Timeout
```

Action:

```text
Retry with backoff.
```

---

## Partial Failure

Some operations succeeded.

Action:

```text
Inspect state.
Resume safely.
```

---

## Permanent Failure

The workflow cannot safely recover automatically.

Action:

```text
FAILED
Require administrator review.
```

---

# 35. Workflow Re-Run Policy

Re-running a provisioning workflow should be safe.

A re-run must not:

* Create a second repository.
* Create duplicate registry entries.
* Add duplicate collaborators unnecessarily.
* Allocate a different project identifier.

Instead, it should:

```text
Observe
   ↓
Compare
   ↓
Repair missing state
   ↓
Verify
```

---

# 36. Security Requirements

The provisioning implementation must follow these rules:

* Use least-privileged credentials.
* Never expose tokens.
* Never log secrets.
* Validate all user-provided project data.
* Validate GitHub usernames before using them.
* Validate repository names.
* Verify the organization before performing operations.
* Never allow a student request to control organization-level permissions.
* Do not trust external state without verification.
* Avoid destructive automatic recovery.
* Audit provisioning actions.

---

# 37. Logging Requirements

Logs should provide enough information for debugging without exposing secrets.

Good:

```text
Provisioning request REQ-2026-0056 started
Repository e26-3yp-G05-example verified
Member configuration completed
Registry update completed
Provisioning verification passed
```

Bad:

```text
GitHub token: ghp_xxxxxxxxx
```

Sensitive values must never appear in workflow logs.

---

# 38. Observability

The provisioning system should make it possible to determine:

```text
What happened?
When did it happen?
Which request caused it?
Which step failed?
What state already exists?
Can it be retried?
```

At minimum, logs and issue comments should expose the operational state without exposing secrets.

---

# 39. Implementation Checklist

## Concurrency

* [ ] Add GitHub Actions concurrency group.
* [ ] Use `cancel-in-progress: false`.
* [ ] Re-check repository existence before creation.
* [ ] Review identifier allocation for race conditions.

## Request Identity

* [ ] Introduce stable request/provisioning ID.
* [ ] Associate request ID with issue.
* [ ] Associate request ID with repository.
* [ ] Associate request ID with registry entry.

## Idempotency

* [ ] Check repository before creation.
* [ ] Check collaborators before configuration.
* [ ] Make registry updates idempotent.
* [ ] Make workflow re-runs safe.

## State Management

* [ ] Define provisioning states.
* [ ] Record state transitions.
* [ ] Distinguish `FAILED` and `PARTIAL_FAILURE`.
* [ ] Support safe resume.

## Recovery

* [ ] Detect partial provisioning.
* [ ] Determine current state.
* [ ] Resume from the missing operation.
* [ ] Handle ambiguous API results.
* [ ] Document manual recovery.

## Verification

* [ ] Verify repository.
* [ ] Verify repository configuration.
* [ ] Verify lead.
* [ ] Verify members.
* [ ] Verify permissions.
* [ ] Verify registry.
* [ ] Only mark `COMPLETED` after verification.

## API Resilience

* [ ] Handle HTTP 429.
* [ ] Handle transient 5xx errors.
* [ ] Handle timeouts.
* [ ] Implement bounded retries.
* [ ] Implement exponential backoff.
* [ ] Re-check state after ambiguous operations.

## Security

* [ ] Use least-privileged GitHub App credentials.
* [ ] Never log secrets.
* [ ] Never hard-code credentials.
* [ ] Keep student permissions repository-scoped.
* [ ] Validate all externally supplied values.

## Registry

* [ ] Define source-of-truth policy.
* [ ] Use stable request IDs.
* [ ] Make registry updates idempotent.
* [ ] Detect inconsistent records.

## Operations

* [ ] Add audit information.
* [ ] Add failure reporting.
* [ ] Add reconciliation workflow.
* [ ] Document manual recovery.
* [ ] Monitor provisioning failures.

---

# 40. Suggested Implementation Order

Implementation should be incremental.

Recommended order:

```text
Phase 1
Documentation and architecture
        │
        ▼
Phase 2
Stable request/provisioning identity
        │
        ▼
Phase 3
Concurrency control
        │
        ▼
Phase 4
Idempotent provisioning
        │
        ▼
Phase 5
Provisioning state management
        │
        ▼
Phase 6
Partial-failure recovery
        │
        ▼
Phase 7
API retry/resilience
        │
        ▼
Phase 8
Post-provisioning verification
        │
        ▼
Phase 9
Registry consistency
        │
        ▼
Phase 10
Reconciliation
```

This order reduces implementation complexity because later features depend on the earlier state-management mechanisms.

---

# 41. Testing Strategy

The provisioning system should be tested against failure scenarios, not only the happy path.

## Happy Path

```text
Valid request
    ↓
Repository created
    ↓
Members configured
    ↓
Registry updated
    ↓
Verification passed
    ↓
COMPLETED
```

---

## Repository Creation Failure

```text
Repository creation
        ↓
Failure
        ↓
No repository exists
        ↓
Retry
```

Expected result:

```text
Repository eventually created
```

---

## Member Configuration Failure

```text
Repository → SUCCESS
Lead       → SUCCESS
Member 2   → SUCCESS
Member 3   → FAILURE
```

Retry should produce:

```text
Repository → SKIP
Lead       → SKIP
Member 2   → SKIP
Member 3   → CONFIGURE
```

---

## Registry Failure

```text
Repository → SUCCESS
Members    → SUCCESS
Registry   → FAILURE
```

Retry should:

```text
Repository → SKIP
Members    → VERIFY
Registry   → UPDATE
```

---

## API Timeout During Creation

```text
Create repository
       ↓
Timeout
       ↓
Check repository
       ↓
Exists
       ↓
Continue
```

The workflow must not blindly create another repository.

---

## Concurrent Requests

Submit two provisioning requests simultaneously.

Expected behavior:

```text
Request A → provisioning
Request B → queued
```

After A completes:

```text
Request B → provisioning
```

The two requests must not receive the same project identifier.

---

# 42. Acceptance Criteria

The architecture can be considered implemented when:

### Reliability

* [ ] A failed provisioning workflow can be safely re-run.
* [ ] Existing resources are detected instead of recreated.
* [ ] Partial failures can be recovered.
* [ ] Ambiguous API operations are reconciled.

### Consistency

* [ ] Repository and registry state can be compared.
* [ ] Duplicate registry entries are prevented.
* [ ] Request IDs remain stable.

### Security

* [ ] Secrets are not exposed.
* [ ] Students receive only approved permissions.
* [ ] Authentication follows least privilege.

### Verification

* [ ] Final repository state is verified.
* [ ] Collaborators are verified.
* [ ] Registry state is verified.
* [ ] `COMPLETED` is only reported after successful verification.

### Operations

* [ ] Failures are observable.
* [ ] Manual recovery is documented.
* [ ] Reconciliation can identify drift.

---

# 43. Architectural Principle

The provisioning system should not be designed as:

```text
Run script once
     ↓
All API calls succeed
     ↓
Done
```

Instead, it should follow:

```text
Desired State
      ↓
Observe Current State
      ↓
Apply Missing Changes
      ↓
Verify
      ↓
Record State
      ↓
Recover / Resume if Required
```

The system should always be able to answer:

> **What state is this project currently in, and what is the next safe operation?**

---

# 44. Final Recommendation

The current repository provisioning approach is viable for the organization's requirements, but the workflow should evolve from a sequence of one-time API calls into a **state-aware provisioning system**.

The highest-priority improvements are:

1. **Concurrency control**
2. **Stable request/provisioning identifiers**
3. **Idempotent provisioning**
4. **Explicit provisioning states**
5. **Partial-failure recovery**
6. **Post-provisioning verification**
7. **Safe GitHub API retries**
8. **Least-privilege authentication**
9. **Registry consistency**
10. **Auditability**
11. **Scheduled reconciliation**

The central architectural requirement is:

> **A failed provisioning run must be safe to retry without creating duplicate or inconsistent resources.**

This architecture allows the system to recover from common GitHub API failures, workflow interruptions, partial configuration, and registry inconsistencies while keeping the implementation understandable and maintainable.

---

# 45. Relationship to Issue #56

This document provides the detailed technical architecture associated with **Issue #56 — GitHub Organization Limitations**.

Issue #56 should remain the primary location for:

* Architecture discussion.
* Design decisions.
* Questions.
* Approval/rejection of proposed changes.
* Links to implementation work.

This document should remain the technical reference for:

* Reliability requirements.
* Provisioning states.
* Recovery behavior.
* Security requirements.
* Verification requirements.
* Implementation guidance.

Implementation changes should be tracked through separate issues and pull requests.

---

# 46. Future Improvements

The following improvements may be considered after the core architecture is implemented:

* Dedicated persistent provisioning database.
* Stronger allocation/reservation mechanism.
* Centralized audit records.
* Automated dashboards.
* More advanced reconciliation.
* Automatic drift detection.
* Metrics for provisioning success/failure rates.
* GitHub App permission refinement.
* Automated architecture compliance checks.
* Formal state-transition validation.

These are not prerequisites for the initial implementation but can be introduced as project volume increases.

---

## Document Status

**Status:** Proposed

**Related Issue:** `#56`

**Primary Repository:** `SCSSA-UoK/project-requests`

**Primary Workflow:** `.github/workflows/issue-provision.yml`

**Primary Provisioning Script:** `scripts/issue_provision.py`

**Architecture Principle:**

> **Stateful + Idempotent + Recoverable + Verifiable + Auditable**
