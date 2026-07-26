"""Phase 3 Training Knowledge And Safety Engine.

A pure backend training domain backed by versioned curated JSON and typed
Pydantic contracts. Phase 3 ships:

- ``schemas``     : strict catalog / exercise / provenance / illustration /
                    prescription / source-manifest contracts (Task 2).
- ``knowledge``   : fail-closed catalog + source-manifest loaders and the
                    recommendation-ready invariant / relation-graph checks
                    (Task 2, extended by Task 3).
- ``importers``   : deterministic non-media upstream-metadata import adapter
                    that can only emit ``needs_review`` drafts (Task 2).

Safety context / decision, policy / candidates and the validator Tool are added
by Tasks 4-6. Nothing here depends on HTTP, a database session, or an LLM.
"""
from __future__ import annotations

__all__ = ["schemas", "knowledge", "importers"]
