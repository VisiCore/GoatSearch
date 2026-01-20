"""Live E2E test for GoatSearch against Cribl API."""
import json
from pathlib import Path

import pytest

QUERY = """dataset=default_logs channel="output:default_logs"
| limit 10000
| extend row_id = row_number(1)
| project row_id, _time, source"""


@pytest.mark.live
@pytest.mark.timeout(300)
@pytest.mark.xfail(reason="Known pagination bug causes duplicates", strict=False)
def test_e2e_10k_events(goatsearch_cmd):
    """Full workflow: auth -> search -> paginate -> validate uniqueness."""
    goatsearch_cmd.query = QUERY

    # Auth and setup
    goatsearch_cmd.prepare()
    assert goatsearch_cmd.can_run, "Auth failed"
    assert goatsearch_cmd.access_token, "No token"

    # Execute search
    events = list(goatsearch_cmd.generate())
    data = [e for e in events if e.get("sourcetype") != "goatsearch:json"]
    row_ids = [e.get("row_id") for e in data if e.get("row_id") is not None]

    assert len(data) == 10000, f"Expected 10000, got {len(data)}"
    assert row_ids, "No row_id values returned"

    # Check for duplicates (same row_id = pagination bug)
    unique = set(row_ids)
    dupes = len(row_ids) - len(unique)

    # Save artifact
    artifact_dir = Path(__file__).parent / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "analysis.json").write_text(
        json.dumps(
            {
                "total": len(data),
                "unique": len(unique),
                "duplicates": dupes,
                "rate": f"{dupes / len(row_ids) * 100:.1f}%" if row_ids else "N/A",
            },
            indent=2,
        )
    )

    assert dupes == 0, f"Found {dupes} duplicates ({dupes / len(row_ids) * 100:.1f}%)"
