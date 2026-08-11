# Public Release Gate

> Status: not approved. Phase 8 synthetic personal-development acceptance does
> not satisfy this gate and must never be presented as deployment, medical,
> privacy, security, accessibility, or regulatory approval.

## Required decisions and evidence

- Define release countries, audience, distribution channel, operator, data
  controller/processor roles, support ownership, and an approved incident owner.
- Obtain qualified legal/privacy review against the official requirements that
  are current at release time. Record applicability, evidence, owner, date, and
  renewal trigger rather than copying a stale legal checklist into code.
- Complete a data inventory and flow map for health records, photos, Agent
  context, provider processing, storage locations, retention, export, deletion,
  backups, logs, analytics, crash reports, and subprocessors.
- Approve user-facing terms, privacy notices, cloud/AI and photo consent,
  withdrawal behavior, age/audience boundaries, health disclaimers, escalation,
  and deletion/export support. Consent must be versioned and independently
  enforceable at runtime.
- Reassess every deterministic health and safety policy against current primary
  sources. Obtain appropriate clinical/fitness/nutrition review for claims and
  escalation copy; AI cannot become the sole safety decision maker.
- Replace development login and synthetic credentials with reviewed production
  authentication, authorization, secret management, rate limiting, abuse
  controls, account recovery, and audit/monitoring controls.
- Complete threat modeling, dependency and supply-chain review, penetration
  testing, encryption/key rotation, backup/restore, deletion verification,
  vulnerability handling, and incident-response exercises.
- Verify provider contracts, processing location, retention, training use,
  availability, safety behavior, cost controls, and current official API terms
  before enabling any live AI or photo path.
- Complete supported-device, OS, network, timezone, localization, large-text,
  screen-reader, contrast, performance, battery, offline/error, upgrade,
  rollback, and destructive account-deletion testing.
- Prepare current app-store/distribution materials, content provenance and
  required AI-generated-content labels/metadata, release notes, support and
  takedown processes, observability, capacity, alerting, and rollback evidence.

## Release decision

Every item requires a named owner and evidence link. Unmet items remain blocked;
they cannot be waived by a green development CI run. Release, deployment, real
data migration, production credentials, external spend, or public distribution
requires separate explicit user authorization after this checklist is reviewed.
