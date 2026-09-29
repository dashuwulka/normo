const profileScript = document.getElementById("builtinProfileData");
const builtinProfile = JSON.parse(profileScript.textContent);

let profileData = structuredClone(builtinProfile);
let currentScreen = 0;
let currentFilter = "all";
let latestResult = null;
let currentExtraction = null;
let activeProfileMode = "builtin";

const screens = document.getElementById("screens");
const statusLine = document.getElementById("statusLine");
const rulesTableBody = document.getElementById("rulesTableBody");
const rulesCount = document.getElementById("rulesCount");
const documentFile = document.getElementById("documentFile");
const jsonProfileFile = document.getElementById("jsonProfileFile");
const jsonReviewToggle = document.getElementById("jsonReviewToggle");
const methodFile = document.getElementById("methodFile");
const documentSummary = document.getElementById("documentSummary");
const tooltip = document.getElementById("tooltip");
const extractionSummary = document.getElementById("extractionSummary");
const extractionRuleGroups = document.getElementById("extractionRuleGroups");
const extractionRulesForm = document.getElementById("extractionRulesForm");

const targetLabels = {
    document: "Документ",
    page: "Страница",
    section: "Секция",
    main_text: "Основной текст",
    additional_text: "Дополнительный текст",
    heading: "Заголовки",
    heading_level_1: "Заголовок 1 уровня",
    heading_level_2: "Заголовок 2 уровня",
    heading_level_3: "Заголовок 3 уровня",
    section_heading: "Раздел основной части",
    structural_heading: "Структурный раздел",
    subsection_heading: "Подраздел",
    point_heading: "Пункт",
    appendix_heading: "Приложение",
    caption: "Подписи рисунков и таблиц",
    figure_caption: "Подпись рисунка",
    table_caption: "Название таблицы",
    table: "Таблица",
    table_cell: "Текст таблиц",
    list_item: "Элементы списка",
    footnote: "Сноски",
    note: "Примечания",
    introduction_tasks: "Задачи во введении",
    conclusion: "Заключение"
};

const parameterLabels = {
    font_family: "гарнитура шрифта",
    font_size: "размер шрифта",
    font_color: "цвет шрифта",
    bold: "полужирное начертание",
    italic: "курсив",
    underline: "подчёркивание",
    line_spacing: "межстрочный интервал",
    first_line_indent: "абзацный отступ",
    left_indent: "левый отступ абзаца",
    right_indent: "правый отступ абзаца",
    alignment: "выравнивание",
    top_margin: "верхнее поле",
    bottom_margin: "нижнее поле",
    left_margin: "левое поле",
    right_margin: "правое поле",
    page_format: "формат страницы",
    page_orientation: "ориентация страницы",
    numbering_terminal_dot: "точка после номера заголовка",
    starts_with_capital: "прописная буква в начале заголовка",
    heading_indent_policy: "отступы заголовка",
    page_break_before: "начинать с новой страницы",
    keep_with_next: "не отрывать от следующего абзаца",
    keep_together: "не разрывать абзац",
    space_before: "интервал перед абзацем",
    space_after: "интервал после абзаца",
    page_number_area: "расположение номера страницы",
    page_number_alignment: "выравнивание номера страницы",
    first_page_no_page_number: "номер на первых листах не показывается",
    continuous_page_numbering: "сквозная нумерация страниц",
    required_document_structure: "состав работы",
    references_min_count: "минимальное количество источников",
    initial_verb_form: "форма задач во введении",
    forbidden_phrases: "нежелательные слова и формулировки",
    completed_action_form: "результаты в заключении",
    heading_english_not_allowed: "заголовки на английском языке",
    list_marker_dash_required: "маркер списка — длинное тире",
    list_marker_allowed: "маркер перечисления",
    hyphen_list_marker_not_recommended: "дефис как маркер списка",
    list_marker_consistency: "единый тип маркера в списке",
    hyphen_instead_of_dash: "дефис вместо тире",
    dash_spacing: "пробелы вокруг тире",
    numeric_range_dash: "тире в числовом диапазоне",
    automatic_list_numbering_required: "автоматическая нумерация списков",
    list_punctuation_policy: "оформление пунктов списка",
    number_sign_symbol: "знак номера",
    russian_quotes: "русские кавычки",
    front_matter_page_numbers_hidden_until_intro: "скрытая нумерация до введения",
    underline: "подчёркивание",
    no_dot_after_udc_keywords_table_title: "точка там, где она не ставится",
    additional_spacing_limit: "слишком большой интервал между частями текста",
    empty_paragraph_between_content: "пустая строка между абзацами",
    empty_paragraph_around_heading: "пустая строка рядом с заголовком",
    table_text_spacing_indent: "интервал и отступы текста в таблице",
    table_grid_style: "границы таблицы",
    table_title_position: "название таблицы над таблицей",
    table_header_required: "строка заголовков таблицы",
    table_repeat_header: "повтор строки заголовков таблицы",
    table_caption_alignment: "выравнивание названия таблицы",
    table_caption_prefix: "слово в начале названия таблицы",
    table_caption_separator: "разделитель после номера таблицы",
    table_caption_terminal_dot: "точка в конце названия таблицы",
    table_text_font_size: "размер шрифта в таблице",
    table_text_line_spacing: "межстрочный интервал в таблице",
    image_after_first_reference: "рисунок после первого упоминания",
    figure_caption_position: "подпись под рисунком",
    figure_caption_alignment: "выравнивание подписи рисунка",
    figure_caption_title_format: "оформление названия рисунка",
    figure_caption_prefix: "слово в начале подписи рисунка",
    figure_caption_separator: "разделитель после номера рисунка",
    figure_caption_terminal_dot: "точка в конце подписи рисунка",
    figure_reference_required: "ссылка на рисунок в тексте",
    figure_after_reference: "рисунок после первого упоминания",
    degree_symbol: "знак градуса",
    centered_text_no_indents: "центрированный текст без отступов",
    heading_font_size_hierarchy: "размеры заголовков по уровням",
    heading_spacing_order: "интервалы вокруг заголовка",
    heading_space_after_min_single: "интервал после заголовка",
    heading_all_caps: "заголовок не полностью прописными буквами",
    toc_headings_match_text: "содержание совпадает с заголовками",
    introduction_required_content: "обязательные элементы введения",
    conclusion_required_content: "обязательные элементы заключения",
    document_language: "язык основного текста",
    table_font_size: "размер шрифта в таблице",
    table_font_size_consistency: "единый размер шрифта в таблицах",
    table_column_alignment_consistency: "единое выравнивание в колонках",
    table_width_within_text_area: "таблица не выходит за поля",
    table_no_empty_rows: "без пустых строк в таблице",
    table_allow_row_break: "разрешить перенос строк таблицы",
    no_continuation_table_titles: "без надписей «Продолжение таблицы»"
};

const operatorLabels = {
    equals: "равно",
    in: "одно из значений",
    min: "не меньше",
    max: "не больше",
    consistent: "единообразно",
    contains: "содержит",
    matches: "соответствует шаблону"
};

const modalityLabels = {
    mandatory: "ошибка",
    recommended: "предупреждение",
    allowed: "допустимое значение"
};

const valueLabels = {
    "000000": "чёрный",
    black: "чёрный",
    true: "да",
    false: "нет",
    justify: "по ширине",
    center: "по центру",
    left: "по левому краю",
    right: "по правому краю",
    dash: "тире после номера",
    hyphen: "дефис",
    dot: "точка после номера",
    no_dot: "без точки в конце",
    below: "под объектом",
    above: "над объектом",
    after_reference: "после первого упоминания",
    infinitive: "глагол в неопределённой форме",
    automatic: "автоматически",
    visible: "видимая",
    hidden: "скрытая",
    russian: "русский язык",
    "русский язык": "русский язык",
    mandatory: "обязательное требование",
    recommended: "рекомендация",
    allowed: "допустимое значение",
    extracted: "готово к сохранению",
    needs_review: "нужно проверить",
    unsupported: "пока проверяется вручную",
    conflict: "есть конфликт с другим правилом",
    confirmed: "подтверждено",
    table_header_required: "строка заголовков таблицы",
    table_text_spacing_indent: "оформление текста в таблице",
    list_marker_dash_required: "маркер списка — длинное тире"
};

const targetIds = Object.fromEntries(Object.entries(targetLabels).map(([id, label]) => [label, id]));
const parameterIds = Object.fromEntries(Object.entries(parameterLabels).map(([id, label]) => [label, id]));
const operatorIds = Object.fromEntries(Object.entries(operatorLabels).map(([id, label]) => [label, id]));
const modalityIds = Object.fromEntries(Object.entries(modalityLabels).map(([id, label]) => [label, id]));
const valueIds = Object.fromEntries(Object.entries(valueLabels).map(([id, label]) => [label, id]));

function readableId(value) {
    if (!value) return "—";
    return String(value).replaceAll("_", " ");
}

const screenStatus = ["", "", "", ""];

function goToScreen(index) {
    currentScreen = index;
    screens.style.transform = `translateX(-${index * 100}%)`;
    if (statusLine) {
        statusLine.textContent = screenStatus[index] || "";
    }
}

function formatFileSize(bytes) {
    if (!bytes) return "0 КБ";
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function updateDocumentSummary(file) {
    if (!file) {
        documentSummary.innerHTML = "";
        documentSummary.classList.remove("visible");
        return;
    }

    documentSummary.classList.add("visible");
    documentSummary.innerHTML = `
        <strong>${file.name}</strong>
        <span>${formatFileSize(file.size)}</span>
        <em>готов к проверке</em>
    `;
}

function parseProfileJsonText(text) {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.rules)) {
        throw new Error("В файле нет списка правил профиля");
    }
    return parsed;
}

function readJsonProfile(file, { openRules = false } = {}) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const buffer = reader.result;
                const decoders = ["utf-8", "utf-8-sig", "windows-1251"];
                let parsedProfile = null;

                for (const encoding of decoders) {
                    try {
                        const text = new TextDecoder(encoding).decode(buffer);
                        parsedProfile = parseProfileJsonText(text);
                        break;
                    } catch {
                        parsedProfile = null;
                    }
                }

                if (!parsedProfile) {
                    throw new Error("Не удалось прочитать JSON-профиль");
                }

                profileData = parsedProfile;
                activeProfileMode = "json";
                renderRules();
                if (statusLine) {
                    statusLine.textContent = "JSON-профиль загружен";
                }
                if (openRules) {
                    goToScreen(1);
                }
                resolve(parsedProfile);
            } catch (error) {
                jsonProfileFile.value = "";
                showToast(error.message || "Не удалось прочитать JSON-профиль");
                reject(error);
            }
        };
        reader.onerror = () => {
            const error = new Error("Не удалось прочитать JSON-профиль");
            jsonProfileFile.value = "";
            showToast(error.message);
            reject(error);
        };
        reader.readAsArrayBuffer(file);
    });
}

function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function getRules() {
    if (!Array.isArray(profileData.rules)) {
        profileData.rules = [];
    }
    return profileData.rules;
}

function valueToText(value) {
    if (Array.isArray(value)) return value.map(valueToText).join(", ");
    if (value && typeof value === "object") return JSON.stringify(value);
    if (value === true) return "да";
    if (value === false) return "нет";
    if (value === null || value === undefined) return "";
    const raw = String(value);
    return valueLabels[raw.toLowerCase()] || valueLabels[raw] || raw;
}

function friendlyRuleDescription(rule) {
    const description = rule.description || "";
    const parameter = parameterLabels[rule.parameter] || readableId(rule.parameter);
    const rawPattern = /^Правило раздела\s+[^:]+:\s+[a-z_]+$/i;
    if (!description || rawPattern.test(description)) {
        return `Проверяется: ${parameter}`;
    }
    return description;
}

function ruleMatchesFilter(rule) {
    if (currentFilter === "all") return true;
    if (currentFilter === "recommended") return rule.modality === "recommended";
    const haystack = `${rule.target || ""} ${rule.parameter || ""} ${rule.category || ""}`.toLowerCase();

    const filterMap = {
        page: ["page", "section", "margin", "orientation", "format", "header", "footer"],
        font: ["font", "bold", "italic", "underline", "caps", "spacing", "color", "кегль"],
        heading: ["heading"],
        main_text: ["main_text"],
        structure: ["structure", "empty", "title_page", "page_number"]
    };

    return (filterMap[currentFilter] || []).some((needle) => haystack.includes(needle));
}

function renderRules() {
    const rules = getRules();
    const filteredRules = rules
        .map((rule, index) => ({ rule, index }))
        .filter(({ rule }) => ruleMatchesFilter(rule));

    rulesCount.textContent = rules.length;

    if (!filteredRules.length) {
        rulesTableBody.innerHTML = `
            <tr>
                <td colspan="4">Для выбранного фильтра правил не найдено.</td>
            </tr>
        `;
        return;
    }

    rulesTableBody.innerHTML = filteredRules.map(({ rule, index }) => `
        <tr>
            <td>${rule.source_section || "—"}</td>
            <td>${friendlyRuleDescription(rule)}</td>
            <td>${valueToText(rule.value)} ${rule.unit || ""}</td>
            <td><button class="secondary" type="button" data-edit-rule="${index}">Изменить</button></td>
        </tr>
    `).join("");
}

function openModal(id) {
    const modal = document.getElementById(id);
    if (modal && !modal.open) modal.showModal();
}

function closeModal(modal) {
    if (modal && modal.open) modal.close();
}

function openRuleEditor(index) {
    const rules = getRules();
    const rule = rules[index];

    if (!rule) {
        showToast("Правило не найдено");
        return;
    }

    document.getElementById("ruleIndex").value = index;
    document.getElementById("ruleSourceSection").value = rule.source_section || "";
    document.getElementById("ruleTarget").value = targetLabels[rule.target] || rule.target || "";
    document.getElementById("ruleParameter").value = parameterLabels[rule.parameter] || rule.parameter || "";
    document.getElementById("ruleOperator").value = operatorLabels[rule.operator] || rule.operator || "";
    document.getElementById("ruleValue").value = valueToText(rule.value);
    document.getElementById("ruleUnit").value = rule.unit || "";
    document.getElementById("ruleModality").value = modalityLabels[rule.modality] || rule.modality || "";
    document.getElementById("ruleDescription").value = friendlyRuleDescription(rule);
    document.getElementById("ruleSourceText").value = friendlyRuleDescription({ ...rule, description: rule.source_text || rule.description });
    openModal("ruleEditor");
}

function parseRuleValue(raw) {
    const trimmed = raw.trim();
    if (trimmed === "да" || trimmed === "true") return true;
    if (trimmed === "нет" || trimmed === "false") return false;
    if (valueIds[trimmed]) return valueIds[trimmed];
    if (trimmed === "") return "";
    if (!Number.isNaN(Number(trimmed))) return Number(trimmed);
    if (trimmed.includes(",")) return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
    return trimmed;
}

function saveRuleFromEditor() {
    const index = Number(document.getElementById("ruleIndex").value);
    const rules = getRules();
    const current = rules[index] || {};

    rules[index] = {
        ...current,
        source_section: document.getElementById("ruleSourceSection").value.trim(),
        target: targetIds[document.getElementById("ruleTarget").value.trim()] || document.getElementById("ruleTarget").value.trim(),
        parameter: parameterIds[document.getElementById("ruleParameter").value.trim()] || document.getElementById("ruleParameter").value.trim(),
        operator: operatorIds[document.getElementById("ruleOperator").value.trim()] || document.getElementById("ruleOperator").value.trim(),
        value: parseRuleValue(document.getElementById("ruleValue").value),
        unit: document.getElementById("ruleUnit").value.trim() || null,
        modality: modalityIds[document.getElementById("ruleModality").value.trim()] || document.getElementById("ruleModality").value.trim() || "mandatory",
        description: document.getElementById("ruleDescription").value.trim(),
        source_text: document.getElementById("ruleSourceText").value.trim()
    };

    renderRules();
    closeModal(document.getElementById("ruleEditor"));
}

function deleteRuleFromEditor() {
    const index = Number(document.getElementById("ruleIndex").value);
    getRules().splice(index, 1);
    renderRules();
    closeModal(document.getElementById("ruleEditor"));
}

function downloadProfile() {
    const blob = new Blob([JSON.stringify(profileData, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${profileData.id || "normcontrol_profile"}.json`;
    link.click();
    URL.revokeObjectURL(url);
}

function renderExtractionGroups(data) {
    currentExtraction = data;
    const groups = data.candidate_groups || [];
    const count = data.candidate_count || groups.reduce((sum, group) => sum + (group.count || 0), 0);

    extractionSummary.textContent = `Найдено правил: ${count}. Проверьте список и оставьте только те правила, которые действительно нужны для проверки документа.`;

    if (!groups.length) {
        extractionRuleGroups.innerHTML = `
            <div class="extraction-empty">
                Система пока не нашла формализуемых правил. Можно загрузить другой файл или использовать готовый профиль проверки.
            </div>
        `;
        return;
    }

    extractionRuleGroups.innerHTML = groups.map((group) => `
        <section class="extraction-group">
            <h3>${escapeHtml(group.label)} <span>${group.count}</span></h3>
            <div class="extraction-cards">
                ${(group.rules || []).map((rule) => `
                    <label class="extraction-card ${rule.can_accept ? "" : "disabled"}">
                        <input
                            type="checkbox"
                            name="candidate_ids"
                            value="${escapeHtml(rule.id)}"
                            ${rule.checked ? "checked" : ""}
                            ${rule.can_accept ? "" : "disabled"}
                        >
                        <span class="extraction-card-body">
                            <strong>${escapeHtml(rule.rule_text)}</strong>
                            <span class="extraction-meta">
                                <em>${escapeHtml(rule.modality)}</em>
                                <em>${escapeHtml(rule.status)}</em>
                                <em>раздел ${escapeHtml(rule.source_section)}</em>
                            </span>
                        </span>
                    </label>
                `).join("")}
            </div>
        </section>
    `).join("");
}

async function confirmExtractedRules(event) {
    event.preventDefault();

    if (!currentExtraction) {
        showToast("Сначала загрузите методичку или ГОСТ");
        return;
    }

    const acceptedIds = [...extractionRulesForm.querySelectorAll('input[name="candidate_ids"]:checked')]
        .map((input) => input.value);

    if (!acceptedIds.length) {
        showToast("Выберите хотя бы одно правило для профиля");
        return;
    }

    try {
        const response = await fetch("/api/extract/confirm", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                extraction_id: currentExtraction.extraction_id,
                source_name: currentExtraction.source_name,
                candidate_ids: acceptedIds
            })
        });
        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Не удалось сохранить профиль");
        }

        profileData = data.profile;
        activeProfileMode = "method";
        renderRules();
        closeModal(document.getElementById("extractionModal"));
        showToast(`Профиль создан: ${data.confirmed_count} правил`);
        goToScreen(1);
    } catch (error) {
        showToast(error.message || "Не удалось сохранить профиль");
    }
}

function resetProcess() {
    document.querySelectorAll("#processList li").forEach((item) => {
        item.dataset.stepStatus = "wait";
    });
}

function markProcessStep(index, status) {
    const steps = [...document.querySelectorAll("#processList li")];
    if (steps[index]) steps[index].dataset.stepStatus = status;
}

async function runCheck() {
    const file = documentFile.files[0];
    if (!file) {
        showToast("Сначала загрузите DOCX-документ");
        return;
    }

    if (!file.name.toLowerCase().endsWith(".docx")) {
        showToast("Проверяемый документ должен быть в формате DOCX");
        return;
    }

    resetProcess();
    goToScreen(2);

    const formData = new FormData();
    formData.append("document", file);
    if (activeProfileMode === "json" && jsonProfileFile.files[0] && !jsonReviewToggle?.checked) {
        formData.append("profile_json", jsonProfileFile.files[0]);
    } else {
        formData.append("profile_payload", JSON.stringify(profileData));
    }
    formData.append("autocorrect", document.getElementById("autocorrect").checked ? "true" : "false");
    formData.append("create_review", document.getElementById("createReview").checked ? "true" : "false");

    const timers = [];
    const processSteps = document.querySelectorAll("#processList li");
    for (let index = 0; index < processSteps.length; index += 1) {
        timers.push(setTimeout(() => {
            document.querySelectorAll("#processList li").forEach((item, itemIndex) => {
                if (itemIndex < index) item.dataset.stepStatus = "done";
                if (itemIndex === index) item.dataset.stepStatus = "active";
            });
        }, index * 420));
    }

    try {
        const response = await fetch("/api/check", {
            method: "POST",
            body: formData
        });
        const data = await response.json();

        timers.forEach(clearTimeout);

        if (!response.ok || !data.ok) {
            document.querySelectorAll("#processList li").forEach((item) => {
                item.dataset.stepStatus = "error";
            });
            showToast(data.error || "Проверка завершилась с ошибкой");
            if (statusLine) {
                statusLine.textContent = "Проверка завершилась с ошибкой";
            }
            return;
        }

        document.querySelectorAll("#processList li").forEach((item) => {
            item.dataset.stepStatus = "done";
        });

        latestResult = data;
        fillResults(data);
        setTimeout(() => goToScreen(3), 420);
    } catch (error) {
        timers.forEach(clearTimeout);
        document.querySelectorAll("#processList li").forEach((item) => {
            item.dataset.stepStatus = "error";
        });
        showToast(error.message || "Не удалось выполнить проверку");
    }
}

function setDownloadLink(id, url) {
    const element = document.getElementById(id);
    if (!element) {
        return;
    }
    if (!url) {
        element.href = "#";
        element.setAttribute("aria-disabled", "true");
        return;
    }
    element.href = url;
    element.removeAttribute("aria-disabled");
}

function fillResults(data) {
    document.getElementById("totalCount").textContent = data.violations_count;
    document.getElementById("errorCount").textContent = data.errors_count;
    document.getElementById("warningCount").textContent = data.warnings_count;

    setDownloadLink("downloadFixed", data.fixed_url);
    setDownloadLink("downloadReview", data.review_url);

    document.getElementById("reportFrame").src = data.report_view_url;

    const groups = data.groups || [];
    const summary = document.getElementById("groupSummary");

    if (!groups.length) {
        summary.innerHTML = "<p>Нарушений не найдено</p>";
        return;
    }

    const ruleGroups = groups.flatMap((section) => section.rule_groups || []);

    summary.innerHTML = ruleGroups.slice(0, 12).map((group) => {
        const count = group.count || group.violations?.length || 0;
        const section = group.source_section ? `§${group.source_section}` : "Без раздела";
        const locations = group.affected || (group.violations || [])
            .slice(0, 8)
            .map((violation) => violation.location)
            .filter(Boolean)
            .join(", ");
        return `
            <details>
                <summary>${count} × ${section}</summary>
                <p>${group.message || group.description || "Нарушение правила профиля"}</p>
                <p>${locations}</p>
            </details>
        `;
    }).join("");
}

function clearForm() {
    documentFile.value = "";
    jsonProfileFile.value = "";
    methodFile.value = "";
    profileData = structuredClone(builtinProfile);
    activeProfileMode = "builtin";
    document.querySelectorAll("[data-profile-mode]").forEach((item) => {
        item.classList.toggle("active", item.dataset.profileMode === "builtin");
    });
    document.querySelectorAll(".profile-mode").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.mode === "builtin");
    });
    if (jsonReviewToggle) {
        jsonReviewToggle.checked = false;
    }
    currentExtraction = null;
    updateDocumentSummary(null);
    renderRules();
    showToast("Форма очищена");
}

document.querySelectorAll("[data-profile-mode]").forEach((button) => {
    button.addEventListener("click", () => {
        const mode = button.dataset.profileMode;
        activeProfileMode = mode;
        document.querySelectorAll("[data-profile-mode]").forEach((item) => item.classList.toggle("active", item === button));
        document.querySelectorAll(".profile-mode").forEach((panel) => panel.classList.toggle("active", panel.dataset.mode === mode));
        if (mode === "builtin") {
            profileData = structuredClone(builtinProfile);
            renderRules();
            if (statusLine) {
                statusLine.textContent = "Используется встроенный профиль ГОСТ";
            }
        } else if (mode === "json" && jsonReviewToggle?.checked && jsonProfileFile.files[0]) {
            readJsonProfile(jsonProfileFile.files[0]).catch(() => {});
        }
    });
});

document.querySelectorAll("[data-drop]").forEach((zone) => {
    const input = document.getElementById(zone.dataset.drop);
    zone.addEventListener("dragover", (event) => {
        event.preventDefault();
        zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
        event.preventDefault();
        zone.classList.remove("drag-over");
        if (!event.dataTransfer.files.length) return;
        input.files = event.dataTransfer.files;
        input.dispatchEvent(new Event("change"));
    });
});

documentFile.addEventListener("change", () => updateDocumentSummary(documentFile.files[0]));

jsonProfileFile.addEventListener("change", async () => {
    const file = jsonProfileFile.files[0];
    if (!file) return;

    if (statusLine) {
        statusLine.textContent = "JSON-профиль выбран";
    }

    if (jsonReviewToggle?.checked) {
        await readJsonProfile(file, { openRules: true }).catch(() => {});
        return;
    }

    showToast("JSON-профиль будет использован при запуске проверки");
});

jsonReviewToggle?.addEventListener("change", async () => {
    const file = jsonProfileFile.files[0];
    if (!file || !jsonReviewToggle.checked) {
        return;
    }
    await readJsonProfile(file, { openRules: true }).catch(() => {});
});

methodFile.addEventListener("change", async () => {
    const file = methodFile.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("normative_document", file);

    showToast("Извлекаю правила из методички");

    try {
        const response = await fetch("/api/extract", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Не удалось извлечь правила");
        }

        renderExtractionGroups(data);
        openModal("extractionModal");
    } catch (error) {
        showToast(error.message || "Не удалось извлечь правила");
        methodFile.value = "";
    }
});

document.querySelectorAll("[data-modal]").forEach((button) => {
    button.addEventListener("click", () => openModal(button.dataset.modal));
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.closest("dialog")));
});

document.querySelectorAll("[data-back]").forEach((button) => {
    button.addEventListener("click", () => goToScreen(Math.max(0, currentScreen - 1)));
});

document.querySelectorAll("[data-to-screen]").forEach((button) => {
    button.addEventListener("click", () => goToScreen(Number(button.dataset.toScreen)));
});

document.getElementById("processingBack").addEventListener("click", () => {
    if (confirm("Проверка будет остановлена. Вернуться?")) {
        goToScreen(0);
    }
});

document.getElementById("clearForm").addEventListener("click", clearForm);
document.getElementById("startCheck").addEventListener("click", runCheck);
document.getElementById("saveProfileContinue").addEventListener("click", runCheck);

document.getElementById("downloadProfileJson").addEventListener("click", downloadProfile);
document.getElementById("downloadResultProfile").addEventListener("click", downloadProfile);
extractionRulesForm.addEventListener("submit", confirmExtractedRules);
document.getElementById("openReport").addEventListener("click", () => {
    if (!latestResult?.report_view_url) {
        showToast("Сначала выполните проверку документа");
        return;
    }
    openModal("reportModal");
});
document.getElementById("saveRule").addEventListener("click", saveRuleFromEditor);
document.getElementById("deleteRule").addEventListener("click", deleteRuleFromEditor);

document.getElementById("ruleFilters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    currentFilter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
    renderRules();
});

rulesTableBody.addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-rule]");
    if (!button) return;
    openRuleEditor(Number(button.dataset.editRule));
});

document.querySelectorAll("[data-tooltip]").forEach((button) => {
    button.addEventListener("mouseenter", () => {
        tooltip.textContent = button.dataset.tooltip;
        const rect = button.getBoundingClientRect();
        tooltip.style.display = "block";
        tooltip.style.left = `${Math.min(rect.left, window.innerWidth - 340)}px`;
        tooltip.style.top = `${rect.bottom + 8}px`;
    });
    button.addEventListener("mouseleave", () => {
        tooltip.style.display = "none";
    });
});

renderRules();
goToScreen(0);
