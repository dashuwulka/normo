from html import escape
from pathlib import Path

from app.models.violation import Violation
from app.services.violation_grouping import (
    count_by_severity,
    group_violations_by_section,
)
from app.services.parameter_registry import get_parameter_label


def _clean_text(value: str | None) -> str:
    if not value:
        return "не указано"
    text = str(value)
    replacements = {
        "line_spacing": "межстрочный интервал",
        "first_line_indent": "абзацный отступ",
        "left_indent": "левый отступ",
        "right_indent": "правый отступ",
        "keep_with_next": "не отрывать от следующего",
        "keep_together": "не разрывать абзац",
        "tblHeader": "повторять строку с названиями столбцов",
        "center": "по центру",
        "justify": "по ширине",
        "left": "по левому краю",
        "right": "по правому краю",
        "000000": "чёрный",
        "True": "да",
        "False": "нет",
        "None": "не задано",
        "not set": "не задано",
    }
    for technical, readable in replacements.items():
        text = text.replace(technical, readable)
    return text


def _render_violation_rows(violations: list[Violation]) -> str:
    rows = []

    for index, violation in enumerate(violations, start=1):
        rows.append(
            f"""
            <tr>
                <td>{index}</td>
                <td>{escape(violation.severity)}</td>
                <td>{escape(violation.location)}</td>
                <td>{escape(get_parameter_label(violation.parameter))}</td>
                <td>{escape(_clean_text(violation.actual))}</td>
                <td>{escape(_clean_text(violation.expected))}</td>
                <td>{escape(_clean_text(violation.message))}</td>
            </tr>
            """
        )

    return "".join(rows)


def _render_grouped_violations(violations: list[Violation]) -> str:
    if not violations:
        return """
        <div class="success">
            Нарушений форматирования основного текста и параметров страницы не найдено.
        </div>
        """

    sections_html = []

    for section in group_violations_by_section(violations):
        rule_groups_html = []

        for rule_group in section["rule_groups"]:
            severity_class = "warning" if rule_group["warnings_count"] and not rule_group["errors_count"] else "error"
            details_rows = _render_violation_rows(rule_group["violations"])
            rule_groups_html.append(
                f"""
                <details class="rule-group {severity_class}">
                    <summary>
                        <strong>{escape(rule_group["summary"])}</strong>
                        <span class="badge error-badge">ошибок: {rule_group["errors_count"]}</span>
                        <span class="badge warning-badge">предупреждений: {rule_group["warnings_count"]}</span>
                    </summary>
                    <div class="rule-meta">
                        <div><strong>Найдено:</strong> {escape(rule_group["actual"] or "не указано")}</div>
                        <div><strong>Требуется:</strong> {escape(rule_group["expected"])}</div>
                        <div><strong>Пояснение:</strong> {escape(rule_group["message"])}</div>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>№</th>
                                <th>Тип</th>
                                <th>Место</th>
                                <th>Параметр</th>
                                <th>Найдено</th>
                                <th>Требуется</th>
                                <th>Описание</th>
                            </tr>
                        </thead>
                        <tbody>{details_rows}</tbody>
                    </table>
                </details>
                """
            )

        sections_html.append(
            f"""
            <section class="section-group">
                <h2>Раздел {escape(section["source_section"])}</h2>
                <div class="section-summary">
                    Всего: <strong>{section["count"]}</strong>,
                    ошибок: <strong>{section["errors_count"]}</strong>,
                    предупреждений: <strong>{section["warnings_count"]}</strong>
                </div>
                {"".join(rule_groups_html)}
            </section>
            """
        )

    return "".join(sections_html)


def generate_html_report(
    violations: list[Violation],
    document_name: str,
    output_path: str | Path = "report.html",
) -> Path:
    """Создаёт сгруппированный HTML-отчёт по найденным нарушениям."""

    output_path = Path(output_path)
    counters = count_by_severity(violations)
    grouped_html = _render_grouped_violations(violations)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Отчёт о проверке документа</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            color: #222;
            background: #fff;
        }}

        h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}

        h2 {{
            font-size: 20px;
            margin: 28px 0 8px;
        }}

        .meta {{
            margin-bottom: 24px;
            color: #555;
        }}

        .summary,
        .section-summary,
        .rule-meta {{
            padding: 12px 14px;
            border: 1px solid #ccc;
            border-radius: 8px;
            background: #f7f7f7;
        }}

        .summary {{
            margin-bottom: 24px;
        }}

        .section-summary {{
            margin-bottom: 12px;
        }}

        .rule-group {{
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            margin: 10px 0;
            padding: 10px 12px;
        }}

        .rule-group summary {{
            cursor: pointer;
        }}

        .rule-meta {{
            margin-top: 12px;
            display: grid;
            gap: 6px;
        }}

        .badge {{
            display: inline-block;
            margin-left: 8px;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
        }}

        .error-badge {{
            background: #ffe8e8;
            color: #7a1111;
        }}

        .warning-badge {{
            background: #fff5d6;
            color: #6c4a00;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}

        th, td {{
            border: 1px solid #ccc;
            padding: 8px 10px;
            text-align: left;
            vertical-align: top;
            font-size: 14px;
        }}

        th {{
            background: #eeeeee;
            font-weight: bold;
        }}

        .success {{
            padding: 14px 18px;
            border: 1px solid #9abf9a;
            border-radius: 8px;
            background: #f0fff0;
        }}
    </style>
</head>
<body>
    <h1>Отчёт о проверке документа</h1>

    <div class="meta">
        Проверяемый файл: <strong>{escape(document_name)}</strong>
    </div>

    <div class="summary">
        Найдено нарушений: <strong>{len(violations)}</strong><br>
        Ошибок: <strong>{counters["error"]}</strong><br>
        Предупреждений: <strong>{counters["warning"]}</strong>
    </div>

    {grouped_html}
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
