# Specialization Filter — Cherry-Picking by Agent Role

## Table of Contents

- [Domain Overlap Check](#domain-overlap-check)
- [Duty Matching](#duty-matching)
- [Practical Usage Test](#practical-usage-test)
- [Filter Decision Table](#filter-decision-table)
- [Examples by Agent Type](#examples-by-agent-type)
- [Cherry-Pick Checklist](#cherry-pick-checklist)

---

## Domain Overlap Check

For each requirements candidate, compare its domain(s) to the agent's domain(s):

| Candidate domain | Agent domain | Decision |
|-----------------|--------------|----------|
| Same domain | Same domain | PASS → evaluate further |
| Sub-domain of agent | Agent covers parent | PASS |
| Unrelated domain | Different domain | REJECT |
| Cross-cutting (security, testing, devops) | Any domain | PASS if agent's duties include it |

**Domain taxonomy examples:**
- `backend` overlaps with: `database`, `api`, `microservices`, `devops`
- `frontend` overlaps with: `ui`, `ux`, `accessibility`, `animation`
- `security` is cross-cutting: overlaps with any domain if agent does security
- `data` overlaps with: `database`, `analytics`, `ml`, `etl`

## Duty Matching

For each requirements candidate that passed the domain check, verify it matches at least one of the agent's declared duties:

```
Agent duties: ["database design", "query optimization", "data migration"]
Candidate: postgresql-best-practices → MATCHES "database design" → ACCEPT
Candidate: react-hooks → NO MATCH to any duty → REJECT
```

**Matching is semantic, not literal.** "Database design" matches:
- postgresql-best-practices (database tool)
- sql-optimization (query-related)
- data-modeling (design-related)
- orm-prisma (database access layer)

But does NOT match:
- react-hooks (UI framework)
- stripe-integration (payments)
- docker-deployment (infrastructure)

## Practical Usage Test

Final sanity check: Would this agent realistically invoke/use this element in its daily work?

Ask: "If I were this agent working on this project, would I ever need to reference this skill/tool/rule?"

- Database agent + `postgresql-best-practices` → YES, references it daily
- Database agent + `react-query` → NO, never touches the frontend
- Security agent + `owasp-security` → YES, core reference material
- Security agent + `figma-integration` → NO, never does design work

## Filter Decision Table

| Domain overlap? | Duty match? | Practical use? | Decision |
|----------------|-------------|----------------|----------|
| YES | YES | YES | **ACCEPT** — add to profile |
| YES | YES | NO | REJECT — theoretical match but no practical use |
| YES | NO | — | REJECT — domain matches but not agent's job |
| NO | — | — | REJECT — outside agent's scope entirely |

## Examples by Agent Type

### Database Specialist on E-Commerce Project

Requirements suggest: React, Stripe, shipping APIs, PostgreSQL, Redis, Elasticsearch, cart management, product catalog, payment processing, search indexing

| Candidate | Domain | Duty match | Decision |
|-----------|--------|------------|----------|
| postgresql-best-practices | database ✓ | database design ✓ | **ACCEPT** |
| redis-best-practices | database ✓ | caching/performance ✓ | **ACCEPT** |
| elasticsearch-best-practices | database ✓ | search indexing ✓ | **ACCEPT** |
| sql-best-practices | database ✓ | query optimization ✓ | **ACCEPT** |
| react | frontend ✗ | — | REJECT |
| stripe | payments ✗ | — | REJECT |
| shipping-api | logistics ✗ | — | REJECT |
| cart-management | frontend ✗ | — | REJECT |

### Security Reviewer on Healthcare App

Requirements suggest: FHIR/HL7, patient portal, HIPAA, encryption, appointment scheduling, lab results, auth/authz, audit logging

| Candidate | Domain | Duty match | Decision |
|-----------|--------|------------|----------|
| owasp-security | security ✓ | vulnerability review ✓ | **ACCEPT** |
| jwt-security | security ✓ | auth review ✓ | **ACCEPT** |
| security-best-practices | security ✓ | general security ✓ | **ACCEPT** |
| hipaa-compliance | security ✓ | compliance review ✓ | **ACCEPT** |
| fhir-integration | healthcare ✗ | — | REJECT |
| appointment-ui | frontend ✗ | — | REJECT |
| lab-results-api | backend ✗ | — | REJECT |

### DevOps Engineer on Microservices Platform

Requirements suggest: Kubernetes, Docker, CI/CD, monitoring, PostgreSQL, Redis, gRPC, API gateway, service mesh, load balancing

| Candidate | Domain | Duty match | Decision |
|-----------|--------|------------|----------|
| kubernetes | devops ✓ | container orchestration ✓ | **ACCEPT** |
| docker | devops ✓ | containerization ✓ | **ACCEPT** |
| ci-cd-best-practices | devops ✓ | pipeline management ✓ | **ACCEPT** |
| monitoring-guidelines | devops ✓ | observability ✓ | **ACCEPT** |
| grpc-development | backend ✗ | — | REJECT |
| postgresql-best-practices | database ✗ | — | REJECT |

## Multi-Domain and Ambiguous Agents

### Multi-Domain Agents (3+ domains)

When an agent covers 3+ domains (e.g., a full-stack developer covering frontend + backend + database + devops):

1. **Union of domains**: The domain overlap check passes if the candidate matches ANY of the agent's domains
2. **Duty matching remains strict**: Even with broad domain coverage, the candidate must match a declared duty
3. **Tier demotion for peripheral domains**: Elements matching non-primary domains go to specialized tier, not secondary
4. **Cap enforcement**: Multi-domain agents hit tier caps faster — apply stricter practical usage test to keep counts manageable

### Agents with No Clear Specialization

When an agent has no declared domains or vague duties (e.g., "general assistant", "project helper"):

1. **Default to requirements context**: Use the project requirements as the domain source instead
2. **Conservative acceptance**: Only accept candidates that score HIGH in the requirements pass AND pass a strict practical usage test
3. **Limit cherry-picks**: Cap at 5 cherry-picked elements to avoid profile bloat
4. **Flag for review**: Mark the profile for interactive review since automated specialization filtering cannot be reliable

## Cherry-Pick Checklist

- [ ] Every `REQS_CANDIDATES` element has been individually evaluated
- [ ] Domain overlap check applied to each candidate
- [ ] Duty matching applied to domain-passing candidates
- [ ] Practical usage test applied to duty-matching candidates
- [ ] Multi-domain agents: union of domains used, peripheral domain elements go to specialized tier
- [ ] Ambiguous agents: conservative mode applied (max 5 cherry-picks, flagged for review)
- [ ] Accepted elements: list with tier assignment (secondary or specialized)
- [ ] Rejected elements: list with specific rejection reason
- [ ] No duplicate elements (already in agent baseline → skip)
- [ ] Cherry-picked count recorded for reporting
