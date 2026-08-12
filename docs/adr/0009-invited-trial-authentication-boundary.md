# ADR-0009: Invited Trial Authentication Boundary

## Status

Accepted by product decision for Phase 9 Gate 0 on 2026-08-12. The decision is
not implementation acceptance and remains bound to exact-SHA Gate verification.

## Context

Phase 8 authenticates a fixed synthetic developer identity in a test-only
acceptance harness. Phase 9 needs a production-intent identity design for a
future small, non-public Android trial without purchasing SMS or email delivery,
handling real contact details, or exposing development credentials.

The approved trial shape is invitation-only, one independent account per tester,
credentials distributed out of band, and one active enrolled device per account.
SMS verification may replace the credential mechanism later. Identity,
authorization, data ownership, deletion, and consent must not be coupled to a
phone number or to a specific delivery vendor.

## Decision

Use five separate concepts:

1. **Invitation:** a high-entropy, single-use, expiring and revocable capability
   that authorizes one account activation. Store only a verifier/digest where
   practical. An invitation never grants API data access.
2. **Account:** an internal stable subject identified by an opaque `user_id`.
   Each tester has a distinct account; shared or universal accounts are forbidden.
3. **Credential provider:** a narrow application port that verifies the current
   credential and reports bounded failure states. Phase 9 can use a pre-provisioned
   local-test credential adapter; a later SMS adapter verifies one-time codes.
4. **Device enrollment:** a revocable record allowing one active trial device per
   account. Device change is an explicit operator-assisted recovery operation;
   no immutable hardware fingerprint is used as identity.
5. **Session:** short-lived access plus rotating/revocable refresh state issued
   only after account, credential and device checks. API authorization derives
   the subject from the verified server session.

The domain and API contracts use internal identity and stable auth failure codes.
They do not expose provider SDK types, delivery receipts, phone-number ownership,
or vendor-specific errors. Replacing the local credential adapter with SMS must
not change `user_id`, invitation rules, authorization, consent, data ownership,
export, deletion or audit semantics.

Candidate configuration fails closed when it finds a default JWT secret,
development login, shared credentials, missing issuer/audience/expiry settings,
or an unconfigured credential adapter. Provider failure never falls back to a
development login.

## Alternatives Considered

1. **Integrate SMS in Phase 9.** Deferred because it introduces real phone
   numbers, vendor credentials, template/qualification review, cost, delivery
   failure and abuse operations before real-data trial authorization exists.
2. **Use email magic links or codes.** Deferred for the same provider and contact
   data reasons, with additional domain reputation and deliverability work.
3. **Use invitation code as every login credential.** Rejected because forwarding
   one reusable capability would combine enrollment and authentication, prevent
   meaningful revocation, and weaken account attribution.
4. **Use one shared test account.** Rejected because it destroys tester-level
   isolation, consent, audit, deletion and incident containment.
5. **Bind identity directly to phone number.** Rejected because provider changes,
   number recycling and account recovery would alter the domain identity.

## Consequences

- Phase 9 can implement and test production-intent authentication without
  external delivery cost or real contact data.
- Credential distribution and recovery remain manual and are suitable only for
  a very small controlled group.
- Invitation entropy, atomic consumption, rate limiting, credential hashing,
  session rotation/revocation and device recovery require dedicated tests.
- The local-test credential adapter is not public-release authentication and
  must be disabled outside the explicitly approved trial mode.
- A future SMS adapter still requires user authorization for provider cost,
  credentials and real phone-number processing, plus provider and privacy review.

## Follow-Up

- Gate 1 defines the exact state model, API schema, environment profile, audit
  events, recovery flow and rollback, then implements them under Codex ownership.
- Gate 2 includes identity and contact-data flows in the privacy/threat model.
- Gate 4 proves no development credential or provider-specific assumption enters
  the controlled-trial candidate.
