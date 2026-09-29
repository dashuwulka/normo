import json
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    after_this_request,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)
from werkzeug.utils import secure_filename

from app.extraction.models import ExtractedRuleCandidate
from app.extraction.pipeline import build_profile_from_confirmed, run_extraction
from app.extraction.presentation import grouped_candidate_views
from app.models.violation import Violation
from app.services.check_service import check_docx_document


main_bp = Blueprint("main", __name__)


ALLOWED_DOCUMENT_EXTENSIONS = {".docx"}
ALLOWED_NORMATIVE_EXTENSIONS = {".docx", ".pdf"}
ALLOWED_PROFILE_EXTENSIONS = {".json"}


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_temporary_profile_path(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        resolved = path.resolve()
        profile_dir = current_app.config["PROFILE_PATH"].parent.resolve()
        return profile_dir in resolved.parents and resolved.name.startswith("extracted_")
    except OSError:
        return False


def _send_file_with_cleanup(
    file_path: Path,
    *,
    as_attachment: bool,
    download_name: str | None = None,
    mimetype: str | None = None,
):
    @after_this_request
    def _cleanup(response):
        _safe_unlink(file_path)
        return response

    return send_file(
        file_path,
        as_attachment=as_attachment,
        download_name=download_name,
        mimetype=mimetype,
    )


def _is_allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return Path(filename).suffix.lower() in allowed_extensions


def _safe_output_path(filename: str, expected_suffix: str) -> Path:
    output_dir: Path = current_app.config["OUTPUT_FOLDER"]
    output_dir_resolved = output_dir.resolve()

    safe_name = secure_filename(Path(filename).name)

    if not safe_name:
        abort(400, description="Некорректное имя файла")

    if Path(safe_name).suffix.lower() != expected_suffix:
        abort(404, description="Файл не найден")

    candidate = (output_dir_resolved / safe_name).resolve()

    if candidate != output_dir_resolved and output_dir_resolved not in candidate.parents:
        abort(404, description="Файл не найден")

    return candidate


def _safe_profile_path(filename: str) -> Path:
    profile_dir: Path = current_app.config["PROFILE_PATH"].parent
    profile_dir_resolved = profile_dir.resolve()
    safe_name = secure_filename(Path(filename).name)

    if not safe_name or Path(safe_name).suffix.lower() != ".json":
        abort(404, description="Файл профиля не найден")

    candidate = (profile_dir_resolved / safe_name).resolve()

    if candidate != profile_dir_resolved and profile_dir_resolved not in candidate.parents:
        abort(404, description="Файл профиля не найден")

    return candidate


def _load_builtin_profile() -> dict:
    profile_path: Path = current_app.config["PROFILE_PATH"]
    with profile_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _save_uploaded_document() -> tuple[Path | None, str | None]:
    uploaded_file = request.files.get("document")

    if uploaded_file is None or uploaded_file.filename == "":
        return None, "Файл документа не выбран."

    if not _is_allowed_file(uploaded_file.filename, ALLOWED_DOCUMENT_EXTENSIONS):
        return None, "Пока поддерживаются только файлы формата DOCX."

    upload_dir: Path = current_app.config["UPLOAD_FOLDER"]
    original_name = Path(uploaded_file.filename).name
    safe_original_name = secure_filename(original_name) or "document.docx"

    if not safe_original_name.lower().endswith(".docx"):
        safe_original_name = f"{safe_original_name}.docx"

    saved_docx_path = upload_dir / f"{uuid4().hex[:8]}_{safe_original_name}"
    uploaded_file.save(saved_docx_path)

    return saved_docx_path, None


def _save_uploaded_normative_document() -> tuple[Path | None, str | None]:
    uploaded_file = request.files.get("normative_document")

    if uploaded_file is None or uploaded_file.filename == "":
        return None, "Файл нормативного документа не выбран."

    if not _is_allowed_file(uploaded_file.filename, ALLOWED_NORMATIVE_EXTENSIONS):
        return None, "Поддерживаются только DOCX и PDF."

    upload_dir: Path = current_app.config["UPLOAD_FOLDER"]
    original_name = Path(uploaded_file.filename).name
    safe_original_name = secure_filename(original_name) or "normative.docx"
    saved_path = upload_dir / f"{uuid4().hex[:8]}_{safe_original_name}"
    uploaded_file.save(saved_path)

    return saved_path, None


def _save_profile_from_request() -> tuple[Path | None, str | None]:
    upload_dir: Path = current_app.config["UPLOAD_FOLDER"]
    profile_payload = request.form.get("profile_payload")

    if profile_payload:
        try:
            profile_data = json.loads(profile_payload)
        except json.JSONDecodeError:
            return None, "Передан некорректный JSON-профиль."

        saved_profile_path = upload_dir / f"{uuid4().hex[:8]}_profile.json"
        with saved_profile_path.open("w", encoding="utf-8") as file:
            json.dump(profile_data, file, ensure_ascii=False, indent=2)

        return saved_profile_path, None

    uploaded_profile = request.files.get("profile_json")
    if uploaded_profile and uploaded_profile.filename:
        if not _is_allowed_file(uploaded_profile.filename, ALLOWED_PROFILE_EXTENSIONS):
            return None, "Профиль проверки должен быть JSON-файлом."

        safe_name = secure_filename(Path(uploaded_profile.filename).name) or "profile.json"
        saved_profile_path = upload_dir / f"{uuid4().hex[:8]}_{safe_name}"
        uploaded_profile.save(saved_profile_path)
        return saved_profile_path, None

    return current_app.config["PROFILE_PATH"], None


def _violation_to_json(violation: Violation) -> dict:
    data = violation.model_dump(mode="json")
    data["severity"] = violation.severity
    return data


def _serialize_grouped_violations(section_groups: list[dict]) -> list[dict]:
    serialized_sections = []

    for section in section_groups:
        serialized_section = dict(section)
        serialized_rule_groups = []

        for rule_group in section.get("rule_groups", []):
            serialized_rule_group = dict(rule_group)
            serialized_rule_group["violations"] = [
                _violation_to_json(violation)
                for violation in rule_group.get("violations", [])
            ]
            serialized_rule_groups.append(serialized_rule_group)

        serialized_section["rule_groups"] = serialized_rule_groups
        serialized_sections.append(serialized_section)

    return serialized_sections


def _download_url(kind: str, path: Path | None) -> str | None:
    if path is None:
        return None
    return f"/download/{kind}/{path.name}"


def _save_extraction_candidates(candidates: list[ExtractedRuleCandidate]) -> str:
    upload_dir: Path = current_app.config["UPLOAD_FOLDER"]
    extraction_id = uuid4().hex
    path = upload_dir / f"extraction_{extraction_id}.json"
    payload = [candidate.model_dump(mode="json") for candidate in candidates]

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    return extraction_id


def _load_extraction_candidates(extraction_id: str) -> list[ExtractedRuleCandidate]:
    safe_id = "".join(ch for ch in extraction_id if ch.isalnum())
    path = current_app.config["UPLOAD_FOLDER"] / f"extraction_{safe_id}.json"

    if not path.exists():
        abort(404, description="Результаты извлечения не найдены")

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    return [ExtractedRuleCandidate.model_validate(item) for item in payload]


def _delete_extraction_candidates(extraction_id: str) -> None:
    safe_id = "".join(ch for ch in extraction_id if ch.isalnum())
    path = current_app.config["UPLOAD_FOLDER"] / f"extraction_{safe_id}.json"
    _safe_unlink(path)


def _save_extracted_profile(profile, source_name: str) -> Path:
    profile_dir: Path = current_app.config["PROFILE_PATH"].parent
    profile_dir.mkdir(exist_ok=True)
    safe_source_name = secure_filename(Path(source_name).stem) or "extracted_profile"
    profile_path = profile_dir / f"extracted_{safe_source_name}_{uuid4().hex[:8]}.json"

    with profile_path.open("w", encoding="utf-8") as file:
        json.dump(profile.model_dump(mode="json"), file, ensure_ascii=False, indent=2)

    return profile_path


@main_bp.route("/", methods=["GET"])
def index():
    profile = _load_builtin_profile()
    return render_template("index.html", builtin_profile=profile)


@main_bp.route("/extract", methods=["GET"])
def extract_profile_page():
    return render_template("extract.html")


@main_bp.route("/extract", methods=["POST"])
def extract_profile():
    saved_path, error = _save_uploaded_normative_document()

    if error or saved_path is None:
        return render_template("extract.html", error=error)

    try:
        candidates = run_extraction(
            document_path=str(saved_path),
            source_name=saved_path.name,
        )
    except Exception as exc:
        return render_template("extract.html", error=str(exc))
    finally:
        _safe_unlink(saved_path)

    extraction_id = _save_extraction_candidates(candidates)

    return render_template(
        "extract.html",
        candidates=candidates,
        candidate_groups=grouped_candidate_views(candidates),
        extraction_id=extraction_id,
        source_name=saved_path.name,
        extraction_done=True,
    )


@main_bp.route("/api/extract", methods=["POST"])
def api_extract_profile():
    saved_path, error = _save_uploaded_normative_document()

    if error or saved_path is None:
        return jsonify({"ok": False, "error": error}), 400

    try:
        candidates = run_extraction(
            document_path=str(saved_path),
            source_name=saved_path.name,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        _safe_unlink(saved_path)

    extraction_id = _save_extraction_candidates(candidates)

    candidate_groups = grouped_candidate_views(candidates)
    visible_candidate_count = sum(group["count"] for group in candidate_groups)

    return jsonify(
        {
            "ok": True,
            "extraction_id": extraction_id,
            "source_name": saved_path.name,
            "candidate_count": visible_candidate_count,
            "candidate_groups": candidate_groups,
        }
    )


@main_bp.route("/extract/confirm", methods=["POST"])
def confirm_extracted_profile():
    extraction_id = request.form.get("extraction_id", "")
    source_name = request.form.get("source_name", "extracted_profile")
    accepted_ids = set(request.form.getlist("candidate_ids"))

    candidates = _load_extraction_candidates(extraction_id)
    confirmed_candidates = [
        candidate.model_copy(update={"status": "confirmed"})
        if (
            candidate.id in accepted_ids
            and candidate.status != "unsupported"
            and candidate.target is not None
            and candidate.modality != "unknown"
        )
        else candidate.model_copy(update={"status": "rejected"})
        for candidate in candidates
    ]

    profile = build_profile_from_confirmed(
        confirmed_candidates,
        {
            "id": f"extracted_{uuid4().hex[:8]}",
            "name": f"Профиль из {source_name}",
            "source_name": source_name,
            "description": "Профиль, сформированный из загруженного нормативного документа.",
        },
    )
    profile_path = _save_extracted_profile(profile, source_name)
    _delete_extraction_candidates(extraction_id)

    return render_template(
        "extract.html",
        profile_path=profile_path,
        profile_download_url=f"/download/extracted-profile/{profile_path.name}",
        confirmed_count=len(profile.rules),
    )


@main_bp.route("/api/extract/confirm", methods=["POST"])
def api_confirm_extracted_profile():
    payload = request.get_json(silent=True) or {}
    extraction_id = str(payload.get("extraction_id", ""))
    source_name = str(payload.get("source_name", "extracted_profile"))
    accepted_ids = set(payload.get("candidate_ids") or [])

    if not extraction_id:
        return jsonify({"ok": False, "error": "Результаты извлечения не найдены."}), 400

    candidates = _load_extraction_candidates(extraction_id)
    confirmed_candidates = [
        candidate.model_copy(update={"status": "confirmed"})
        if (
            candidate.id in accepted_ids
            and candidate.status != "unsupported"
            and candidate.target is not None
            and candidate.modality != "unknown"
        )
        else candidate.model_copy(update={"status": "rejected"})
        for candidate in candidates
    ]

    try:
        profile = build_profile_from_confirmed(
            confirmed_candidates,
            {
                "id": f"extracted_{uuid4().hex[:8]}",
                "name": f"Профиль из {source_name}",
                "source_name": source_name,
                "description": "Профиль, сформированный из загруженного нормативного документа.",
            },
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    profile_path = _save_extracted_profile(profile, source_name)
    _delete_extraction_candidates(extraction_id)

    return jsonify(
        {
            "ok": True,
            "confirmed_count": len(profile.rules),
            "profile": profile.model_dump(mode="json"),
            "profile_download_url": f"/download/extracted-profile/{profile_path.name}",
        }
    )


@main_bp.route("/check", methods=["POST"])
def check_document():
    saved_docx_path, error = _save_uploaded_document()

    if error or saved_docx_path is None:
        return render_template(
            "index.html",
            error=error,
            builtin_profile=_load_builtin_profile(),
        )

    profile_path, profile_error = _save_profile_from_request()
    if profile_error or profile_path is None:
        return render_template(
            "index.html",
            error=profile_error,
            builtin_profile=_load_builtin_profile(),
        )

    try:
        result = check_docx_document(
            docx_path=saved_docx_path,
            profile_path=profile_path,
            output_dir=current_app.config["OUTPUT_FOLDER"],
            autocorrect=request.form.get("autocorrect") == "on",
            create_review=request.form.get("create_review") == "on",
        )
    finally:
        _safe_unlink(saved_docx_path)
        if profile_path != current_app.config["PROFILE_PATH"]:
            _safe_unlink(profile_path)

    return render_template(
        "result.html",
        result=result,
        original_name=saved_docx_path.name,
    )


@main_bp.route("/api/check", methods=["POST"])
def api_check_document():
    saved_docx_path, error = _save_uploaded_document()
    if error or saved_docx_path is None:
        return jsonify({"ok": False, "error": error}), 400

    profile_path, profile_error = _save_profile_from_request()
    if profile_error or profile_path is None:
        return jsonify({"ok": False, "error": profile_error}), 400

    try:
        result = check_docx_document(
            docx_path=saved_docx_path,
            profile_path=profile_path,
            output_dir=current_app.config["OUTPUT_FOLDER"],
            autocorrect=request.form.get("autocorrect") == "true",
            create_review=request.form.get("create_review") == "true",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        _safe_unlink(saved_docx_path)
        if profile_path != current_app.config["PROFILE_PATH"]:
            _safe_unlink(profile_path)

    return jsonify(
        {
            "ok": True,
            "document_name": saved_docx_path.name,
            "violations_count": result.violations_count,
            "errors_count": result.errors_count,
            "warnings_count": result.warnings_count,
            "report_url": _download_url("report", result.report_path),
            "report_view_url": f"/view/report/{result.report_path.name}",
            "fixed_url": _download_url("fixed", result.fixed_docx_path),
            "review_url": _download_url("review", result.review_docx_path),
            "profile_url": "/download/profile",
            "groups": _serialize_grouped_violations(result.grouped_violations),
        }
    )


@main_bp.route("/view/report/<path:filename>", methods=["GET"])
def view_report(filename: str):
    file_path = _safe_output_path(filename, expected_suffix=".html")

    if not file_path.exists():
        return "Файл отчёта не найден", 404

    return send_file(file_path, as_attachment=False)


@main_bp.route("/download/profile", methods=["GET"])
def download_profile():
    profile_path: Path = current_app.config["PROFILE_PATH"]
    return send_file(
        profile_path,
        as_attachment=True,
        download_name=profile_path.name,
        mimetype="application/json",
    )


@main_bp.route("/download/extracted-profile/<path:filename>", methods=["GET"])
def download_extracted_profile(filename: str):
    profile_path = _safe_profile_path(filename)

    if not profile_path.exists():
        return "Файл профиля не найден", 404

    if _is_temporary_profile_path(profile_path):
        return _send_file_with_cleanup(
            profile_path,
            as_attachment=True,
            download_name=profile_path.name,
            mimetype="application/json",
        )

    return send_file(
        profile_path,
        as_attachment=True,
        download_name=profile_path.name,
        mimetype="application/json",
    )


@main_bp.route("/download/report/<path:filename>", methods=["GET"])
def download_report(filename: str):
    file_path = _safe_output_path(filename, expected_suffix=".html")

    if not file_path.exists():
        return "Файл отчёта не найден", 404

    return _send_file_with_cleanup(file_path, as_attachment=True)


@main_bp.route("/download/fixed/<path:filename>", methods=["GET"])
def download_fixed_docx(filename: str):
    file_path = _safe_output_path(filename, expected_suffix=".docx")

    if not file_path.exists():
        return "Исправленный файл не найден", 404

    return _send_file_with_cleanup(file_path, as_attachment=True)


@main_bp.route("/download/review/<path:filename>", methods=["GET"])
def download_review_docx(filename: str):
    file_path = _safe_output_path(filename, expected_suffix=".docx")

    if not file_path.exists():
        return "Файл с комментариями не найден", 404

    return _send_file_with_cleanup(file_path, as_attachment=True)
