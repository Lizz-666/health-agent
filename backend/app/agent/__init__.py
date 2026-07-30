"""Phase 5 Agent MVP package (Batch A / Task 1).

Task 1 delivers only the read-side boundary: a closed entry enum and strict
typed schemas, keyed-HMAC fingerprints, a deterministic pre-provider safety
text router, the minimal owned Context Resolver, the static read Tool Registry,
and read adapters that reuse existing domain services.

No provider/orchestrator, no write/proposal execution, no persistence models,
and no HTTP router live here yet; those arrive in later gated batches. Nothing
in this package performs a live model call or accepts a client-supplied
identity/authority value.

Submodules are imported explicitly by callers to keep import edges narrow and
avoid eager coupling between the strict schemas and the service adapters.
"""
