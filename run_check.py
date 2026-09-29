"""Helper script to run check_docx_document on uploaded docx + profile pair."""
import json
import sys
import types
from pathlib import Path

# Stub flask if missing
try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_mod = types.ModuleType("flask")

    class _StubFlask:
        def __init__(self, *a, **k):
            self.config = {}
        def __getattr__(self, name):
            return lambda *a, **k: None
    flask_mod.Flask = _StubFlask
    sys.modules["flask"] = flask_mod

from app.services.check_service import check_docx_document  # noqa: E402

if __name__ == "__main__":
    docx_path = Path(sys.argv[1])
    profile_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("outputs")
    output_dir.mkdir(exist_ok=True)

    result = check_docx_document(
        docx_path=docx_path,
        profile_path=profile_path,
        output_dir=output_dir,
        autocorrect=False,
        create_review=False,
    )
    print(f"Violations: {result.violations_count}")
    rows = []
    for v in result.violations:
        rows.append({
            "rule_id": v.rule_id,
            "section": v.source_section,
            "severity": v.severity,
            "paragraph_index": v.paragraph_index,
            "section_index": v.section_index,
            "parameter": v.parameter,
            "location": v.location,
            "actual": v.actual,
            "expected": v.expected,
            "message": v.message,
        })
    summary_path = output_dir / "violations_summary.json"
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary saved: {summary_path}")
