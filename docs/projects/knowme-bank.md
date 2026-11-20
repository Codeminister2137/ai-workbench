# KnowMe bank

Local-first personal knowledge bank: atomic curated facts with
provenance, an interview importer, and consumers (trainer, matching,
dashboard).

Key areas: `packages/knowme_bank`, KnowMe dashboard tab.

Current state: storage + atomic ingest + grouped view done. Owner approved
the bank-first trainer slice (A, inbox `f12017f8`, 2026-11-18): missing facts
trigger questions to the owner to populate the bank rather than guesses.
Consumer helpers shipped (`consumer.py` plan context); missing facts are
requested through inbox clarification and answers banked for reuse.
Personal-data inference remains local-only. See the Roadmap.
