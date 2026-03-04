# Plan: Error Hints + Test Coverage for Untested 6%

## Context
94% test coverage — the untested 6% is error-handling code (KLayout subprocess failures, timeouts, missing decks, OS errors). Some of these paths give users cryptic messages with no actionable guidance. User wants: (1) tests covering these paths, (2) tooltip-style hints in the UI explaining what went wrong and what to do.

## Approach: Centralized Hint Mapping

Instead of adding `hint` fields to each error class, create a single `error_hints.py` with regex-to-hint rules. This keeps hints in one maintainable file, avoids changing 3 error class interfaces, and works with the existing `str(e)` pattern in routes.

## Changes (10 files, ~270 lines)

### 1. NEW: `backend/core/error_hints.py` (~80 lines)
- List of `(regex_pattern, hint_string)` tuples
- `get_hint(error_message: str) -> str | None` — returns first matching hint
- Covers all weak error paths:
  - OSError exec format → "Wrong architecture binary, reinstall for your platform"
  - OSError permission denied → "Check permissions, macOS Gatekeeper bypass"
  - OSError no such file → "KLayout not at configured path, set KLAYOUT_BINARY env var"
  - Generic OSError → "Verify KLayout installed and accessible"
  - Timeout → "Design may be too large/complex. Increase DRC_TIMEOUT_SECONDS or simplify hierarchy"
  - DRC/LVS deck not found → "Expected directory structure: backend/pdk/configs/<pdk_name>/<deck>"
  - KLayout crash (exit != 0) → "Common causes: corrupted GDSII, incompatible deck, missing layers"
  - No report generated → "Deck may be missing report() call or silently failed"
  - Binary not found → "Install instructions + macOS Gatekeeper note"
  - GDSII/netlist not found → "Try re-uploading"
  - PDK not found → "Check available PDKs via dropdown or GET /api/pdks"

### 2. EDIT: `backend/jobs/manager.py` (1 line)
- Add `hint: str | None = None` to Job dataclass after `error` field (line 44)
- `update_status` already accepts `**kwargs` → `hint=` will flow through automatically
- `to_dict`/`from_dict` already use `asdict()`/field filtering → no changes needed

### 3. EDIT: `backend/jobs/database.py` (~5 lines)
- Add `hint TEXT` to `_SCHEMA` after `error TEXT` (line 23)
- Add `"hint"` to `JOB_COLUMNS` tuple (line 64)
- Add `ALTER TABLE jobs ADD COLUMN hint TEXT` migration in `__init__` with try/except for existing DBs

### 4. EDIT: `backend/api/routes/drc.py` (~6 lines)
- Import `get_hint` from `error_hints`
- In each except block of `_run_drc_background`, call `get_hint(str(e))` and pass `hint=` to `update_status`
- 3 catch blocks: PDK FileNotFoundError (line 33), DRCError (line 48), FileNotFoundError (line 52)

### 5. EDIT: `backend/api/routes/lvs.py` (~6 lines)
- Same pattern as drc.py
- 3 catch blocks: PDK FileNotFoundError (line 93), LVSError (line 106), FileNotFoundError (line 110)

### 6. EDIT: `frontend/src/api/client.ts` (1 line)
- Add `hint: string | null;` to `JobSummary` interface after `error`

### 7. EDIT: `frontend/src/App.tsx` (~25 lines)
- Add `hint` state: `const [hint, setHint] = useState<string | null>(null)`
- Clear `hint` alongside `error` in each handler's start (`setHint(null)`)
- In LVS polling path: extract `job.hint` when status is `lvs_failed`
- In DRC/LVS catch blocks: poll job to get hint if jobId exists
- Replace error display (lines 231-235) with error + hint panel:
  - Red error text (unchanged)
  - Below it: amber hint box with `Hint:` label, only shown when hint exists
  - Inline styles: `color: "#f5a623"`, `background: "#2a2a1e"`, `border: "1px solid #f5a62344"`, `borderRadius: 4`
  - Consistent with existing color palette (amber = warning)

### 8. NEW: `tests/unit/test_error_hints.py` (~80 lines)
- Test every regex pattern matches its intended error string
- Test hint content includes actionable keywords (e.g., "install", "permission", "timeout")
- Test unrecognized errors return `None`
- Test empty string returns `None`
- ~16 test cases

### 9. EDIT: `tests/unit/test_drc_runner.py` (~25 lines)
- Add `test_oserror_exec_format` — mock `Popen` with `OSError(8, "Exec format error")`, assert `DRCError` raised
- Add `test_oserror_permission_denied` — mock with `OSError(13, "Permission denied")`
- Add async variants of both

### 10. EDIT: `tests/unit/test_lvs_runner.py` (~25 lines)
- Same OSError tests as drc_runner
- Add `test_oserror_exec_format` (sync + async)
- Add `test_oserror_permission_denied` (sync + async)

## Implementation Order
1. `error_hints.py` + `test_error_hints.py` (no deps)
2. Job model + database (no deps)
3. Route wiring (depends on 1+2)
4. Frontend (depends on 3)
5. Runner OSError tests (no deps, can parallel with anything)

## Verification
1. `cd ~/agentic-drc && .venv/bin/python -m pytest tests/unit/ -q --cov=backend` — should pass 720+ tests, coverage > 95%
2. `cd frontend && npm run build` — should build clean
3. Manual: start backend+frontend, trigger a DRC error (e.g., rename klayout binary), verify hint appears in amber box below red error text

## Key Architecture Details

### Error Flow (Current)
```
Runner raises DRCError/LVSError
  → Route background task catches it
  → manager.update_status(job_id, status, error=str(e))
  → Frontend polls GET /api/jobs/{job_id}
  → Gets job.error string
  → Shows red text in header
```

### Error Flow (After This Change)
```
Runner raises DRCError/LVSError
  → Route background task catches it
  → hint = get_hint(str(e))  ← NEW
  → manager.update_status(job_id, status, error=str(e), hint=hint)  ← hint kwarg flows through **kwargs
  → Frontend polls GET /api/jobs/{job_id}
  → Gets job.error + job.hint
  → Shows red error text + amber hint box below it
```

### Key Files to Read First
- `backend/core/drc_runner.py` — DRCError class (lines 32-38), all error paths
- `backend/core/lvs_runner.py` — LVSError class (lines 29-35), all error paths
- `backend/jobs/manager.py` — Job dataclass (line 30), update_status (line 109) accepts **kwargs
- `backend/jobs/database.py` — Schema (line 11), JOB_COLUMNS (line 51)
- `backend/api/routes/drc.py` — _run_drc_background catch blocks (lines 32-53)
- `backend/api/routes/lvs.py` — _run_lvs_background catch blocks (lines 90-111)
- `frontend/src/api/client.ts` — JobSummary interface (line 5)
- `frontend/src/App.tsx` — error state (line 29), error display (lines 231-235)
- `tests/unit/test_drc_runner.py` — existing subprocess mock patterns
- `tests/unit/test_api_coverage.py` — existing API error test patterns
