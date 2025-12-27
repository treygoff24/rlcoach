   1 # Project Context — Account Exclusion Feature
   2 
   3 **Last Updated**: Phase 1 - Implementation (IN PROGRESS)
   4 
   5 ## Protocol Reminder
   6 
   7 **The Loop**: IMPLEMENT → TYPECHECK → LINT → BUILD → TEST → REVIEW → FIX → COMMIT
   8 
   9 **Quality gates:**
  10 ```bash
  11 source .venv/bin/activate
  12 PYTHONPATH=src pytest -q
  13 ruff check src/
  14 black --check src/
  15 ```
  16 
  17 **How to call Codex:**
  18 ```bash
  19 codex exec --model gpt-5.2-codex --config model_reasoning_effort="xhigh" --yolo "[PROMPT]"
  20 ```
  21 
  22 If context feels stale, re-read AUTONOMOUS_BUILD_CLAUDE.md for the full protocol.
  23 
  24 ## Build Context
  25 
  26 **Type**: Feature addition
  27 **Spec location**: docs/plans/2025-12-25-account-exclusion-design.md
  28 **Branch**: feature/account-exclusion
  29 
  30 ## Project Setup
  31 
  32 - Language: Python 3.14
  33 - Testing: pytest
  34 - Linting: ruff, black
  35 - Config: TOML-based (tomllib)
  36 
  37 ## Current Phase
  38 
  39 Implementing account exclusion feature:
  40 1. Add `excluded_names` to IdentityConfig
  41 2. Add `should_exclude()` to PlayerIdentityResolver
  42 3. Add exclusion check in pipeline
  43 4. Update config template
  44 5. Write tests
  45 
  46 ## Files to Modify
  47 
  48 - `src/rlcoach/config.py` - Add excluded_names field, validation
  49 - `src/rlcoach/identity.py` - Add should_exclude(), improve normalization
  50 - `src/rlcoach/pipeline.py` - Add exclusion check at ingest
  51 - `src/rlcoach/config_templates.py` - Add excluded_names to template
  52 - `tests/test_identity.py` - Test exclusion logic
  53 - `tests/test_config.py` - Test overlap validation
  54 
  55 ## Design Decisions
  56 
  57 - Exclusion only checks "me" (via find_me), not opponents/teammates
  58 - Use `.casefold().strip()` for Unicode-safe case-insensitive matching
  59 - Validation rejects overlap between display_names and excluded_names
  60 - Skip replays silently (no deletion)
