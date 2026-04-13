# GoatSearch: AI Code Guidelines

GoatSearch is a Splunk custom command for Cribl Search integration. This
document defines mandatory standards for all AI-generated code contributions.

## Code Understanding Mandate

**Non-negotiable**: Every line of code must be justifiable by human
reasoning. AI-generated code lacking clear human purpose will be rejected at
review.

- No "because the AI suggested it" rationales
- Each function must have explicit business purpose
- Complex logic requires explanation comments
- If Jacob cannot articulate the purpose, it fails review

## Performance Requirements

### Per-Job Impact

- No net increase in search execution time between main/develop without
  documented justification
- Memory consumption must remain bounded regardless of result set size
- CPU usage per job must scale linearly or better with event count

### Per-Event Impact

- Understand the cost per event processed
- Example: hash computation adds X ms per event - document and justify
- Cumulative effect: 1M events × 1ms overhead = 1000s added time

### Validation

- Benchmark before/after on representative data
- Use `_time` and processing metadata to measure actual impact
- Report findings in commit message or code comment

## Testing Criteria for AI Code

### Holistic 1:1 Matching

- Results from Cribl must exactly match results via GoatSearch
- No unjustified differences in event ordering, filtering, or field
  transformation
- Deviation must be explained (e.g., "removed duplicates per business logic")

### Performance Validation

- No unjustifiable performance degradation vs. direct Cribl API calls
- Acceptable overhead: credential retrieval + OAuth token acquisition
- Unacceptable overhead: inefficient pagination, redundant API calls

### Test Execution

- Live E2E tests use real Cribl API (credentials required)
- Tests detect pagination bugs via row_number() sequencing
- Artifacts capture analysis for review

### Test Integrity

**Tests must fail honestly.** When a test fails, the correct response is to
investigate and fix the root cause—never to bypass, suppress, or mark tests
as expected failures.

Prohibited practices:

- Using `xfail`, `skip`, or similar to hide legitimate failures
- Adjusting assertions to match broken behavior
- Disabling tests that expose real bugs
- Adding logic to ignore known issues

If a test fails, either:

1. Fix the underlying bug in the code
2. Fix the test if it contains an error
3. Document the investigation if the cause is unclear

Failing CI is the correct outcome when code has defects.

## Environment Requirements

### Python Version

Splunk embeds Python 3.9. All code must be compatible:

- No walrus operators (`:=` - use explicit assignments)
- No 3.10+ features (match statements, etc.)
- Test with Python 3.9 first

## Gitflow Workflow

VisiCore repositories use gitflow:

- **main**: Release-ready code, protected branch
- **develop**: Integration branch for features/fixes
- Feature branches: `feature/*` from develop
- Release branches: `release/*` from develop
- Hotfix branches: `hotfix/*` from main

All development work on feature/fix branches before PR to develop or main.

## Test Infrastructure

### Live E2E Tests

Located in `tests/test_e2e.py`, executed on main/develop pushes:

- Requires credentials: `CRIBL_CLIENT_ID`, `CRIBL_CLIENT_SECRET`,
  `CRIBL_TENANT`, `CRIBL_WORKSPACE`
- Fetches ~10k events to validate pagination and uniqueness
- Saves analysis artifacts for review

### Test Markers

- `@pytest.mark.live` - Real Cribl API calls (credentials required)
- `@pytest.mark.timeout(300)` - 5-minute maximum per test

### Mocking Strategy

Splunk objects are stubbed via `tests/conftest.py`:

- `MockService` - storage_passwords, kvstore, users
- `MockMetadata` - search time ranges
- `MockRecordWriter` - output messages

No HTTP calls are mocked—Cribl API interaction is live.

## Known Issues

### Duplicate Events at Scale

Live testing at 10k+ events reveals pagination bugs manifesting as ~30%
duplicates. Detection method: sequential row IDs via `row_number(1)` in
queries. Same row_id appearing twice indicates repeated API offset requests.

## Review Criteria Checklist

Before committing AI-generated code, verify:

- [ ] Every function has documented business purpose
- [ ] No performance increase without justification
- [ ] Per-job and per-event costs understood and documented
- [ ] E2E test passes with 1:1 Cribl↔Splunk matching
- [ ] No unjustified performance degradation
- [ ] Python 3.9 compatible (no 3.10+ features)
- [ ] Test coverage for new functionality
