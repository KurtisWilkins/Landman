"""GL mapping engine (design doc §5.3): map messy seller financial lines into the RJourney
chart. Embed gl_accounts once (pgvector), shortlist candidates by cosine similarity, let
Claude pick the account + the level it can justify (leaf vs subgroup) + a confidence + NOI
placement; degrade to the subgroup ('coarse') when granularity is missing; persist unmapped
lines for review; learn confirmed mappings and reuse them.

The embedding + classification providers are unresolved (§14 C-20) and are mockable seams;
they return None until configured, so the engine degrades gracefully rather than guessing.
"""
