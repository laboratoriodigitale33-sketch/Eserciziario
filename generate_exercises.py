#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_exercises.py

Generatore unico per l'eserciziario.

Supporta due formati di esercizio:
1) pagine HTML autonome con metadati:

   <script>
   window.EXERCISE_METADATA = {
     title: "...",
     description: "...",
     subject: "Fisica",
     category: "Meccanica",
     topic: "Dinamica",
     order: 10,
     tags: ["dinamica"]
   };
   </script>

2) file/template HTML che contengono almeno un elemento con:

   data-exercise-statement

   opzionalmente anche:

   data-exercise-solution
   data-exercise-title="..."
   data-exercise-description="..."
   data-exercise-level="base"
   data-exercise-order="10"

Uso tipico dalla root del progetto:

  python generate_exercises.py
      Aggiorna il catalogo globale esercizi.json.

  python generate_exercises.py fisica/meccanica/dinamica
      Aggiorna la raccolta locale dentro quella cartella:
      dinamica.json + index.html.

  python generate_exercises.py fisica/meccanica/dinamica --mode both
      Aggiorna sia la raccolta locale sia il catalogo globale.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# -----------------------------------------------------------------------------
# Configurazione di base
# -----------------------------------------------------------------------------

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    "assets",
    "old",
    "archive",
    "archivio",
    "backup",
}

DEFAULT_SUBJECTS = [
    {
        "name": "Fisica",
        "order": 1,
        "color": "#5bd4c4",
        "description": "Esercizi di fisica organizzati per ambito.",
    },
    {
        "name": "Matematica",
        "order": 2,
        "color": "#8ab4f0",
        "description": "Esercizi di matematica organizzati per argomento.",
    },
]

DEFAULT_CATEGORIES = [
    {
        "name": "Fondamenti",
        "subject": "Fisica",
        "order": 1,
        "color": "#8ab4f0",
        "description": "Il linguaggio con cui la fisica descrive il mondo.",
    },
    {
        "name": "Meccanica",
        "subject": "Fisica",
        "order": 10,
        "color": "#5bd4c4",
        "description": "Moto, forze, equilibrio, energia e leggi di Newton.",
    },
    {
        "name": "Gravitazione",
        "subject": "Fisica",
        "order": 20,
        "color": "#a78bfa",
        "description": "La forza che domina su grandi scale: dalla caduta dei corpi alle orbite.",
    },
    {
        "name": "Fluidodinamica",
        "subject": "Fisica",
        "order": 30,
        "color": "#5bc8f0",
        "description": "Il comportamento di liquidi, gas e fluidi in movimento.",
    },
    {
        "name": "Termodinamica",
        "subject": "Fisica",
        "order": 40,
        "color": "#f08c5b",
        "description": "Calore, temperatura, energia interna, entropia e macchine termiche.",
    },
    {
        "name": "Onde",
        "subject": "Fisica",
        "order": 50,
        "color": "#f0c060",
        "description": "Propagazione, interferenza, diffrazione e fenomeni ondulatori.",
    },
    {
        "name": "Ottica",
        "subject": "Fisica",
        "order": 60,
        "color": "#f0e060",
        "description": "Riflessione, rifrazione, lenti, specchi e comportamento della luce.",
    },
    {
        "name": "Elettromagnetismo",
        "subject": "Fisica",
        "order": 70,
        "color": "#f07070",
        "description": "Cariche, campi elettrici, magnetismo, circuiti e onde elettromagnetiche.",
    },
    {
        "name": "Relatività",
        "subject": "Fisica",
        "order": 80,
        "color": "#c084fc",
        "description": "Spazio, tempo, simultaneità, gravità relativistica e struttura dello spaziotempo.",
    },
    {
        "name": "Meccanica Quantistica",
        "subject": "Fisica",
        "order": 90,
        "color": "#7dd3fc",
        "description": "Fenomeni microscopici, stati quantistici, probabilità e misura.",
    },
    {
        "name": "Astrofisica",
        "subject": "Fisica",
        "order": 100,
        "color": "#e879f9",
        "description": "Stelle, galassie, cosmologia e fenomeni fisici su scala astronomica.",
    },
    {
        "name": "Fisica Nucleare",
        "subject": "Fisica",
        "order": 110,
        "color": "#fb923c",
        "description": "Nuclei, decadimenti, reazioni nucleari e applicazioni delle radiazioni.",
    },
    {
        "name": "Fisica delle Particelle",
        "subject": "Fisica",
        "order": 120,
        "color": "#fb923c",
        "description": "Particelle elementari, interazioni fondamentali e modello standard.",
    },
    {
        "name": "Algebra",
        "subject": "Matematica",
        "order": 10,
        "color": "#8ab4f0",
        "description": "Equazioni, disequazioni, polinomi e calcolo simbolico.",
    },
    {
        "name": "Geometria Analitica",
        "subject": "Matematica",
        "order": 20,
        "color": "#93c5fd",
        "description": "Rette, circonferenze, coniche e coordinate cartesiane.",
    },
    {
        "name": "Analisi",
        "subject": "Matematica",
        "order": 30,
        "color": "#60a5fa",
        "description": "Funzioni, limiti, derivate, integrali e studio di funzione.",
    },
]

JS_METADATA_REGEX = re.compile(
    r"window\.(?:EXERCISE_METADATA|ESERCIZIO_METADATA)\s*=\s*\{(?P<body>.*?)\}\s*;",
    re.DOTALL | re.IGNORECASE,
)

TAG_WITH_ATTR_REGEX_TEMPLATE = r"<(?P<tag>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*)\b{attr}\b(?P<attrs2>[^>]*)>(?P<body>.*?)</(?P=tag)>"

SELF_CLOSING_ATTR_REGEX_TEMPLATE = r"<(?P<tag>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*)\b{attr}\b(?P<attrs2>[^>]*)/?>"

ATTR_REGEX = re.compile(
    r"(?P<name>[a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)


@dataclass
class ExtractedExercise:
    metadata: dict[str, Any]
    statement_html: str = ""
    solution_html: str = ""
    source_format: str = "metadata"


# -----------------------------------------------------------------------------
# Argomenti CLI
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera cataloghi globali e raccolte locali per l'eserciziario."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help=(
            "Cartella da usare. Senza argomenti aggiorna il catalogo globale. "
            "Con una cartella specifica aggiorna la raccolta locale della cartella."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "global", "local", "both"],
        default="auto",
        help=(
            "auto: senza path specifico = globale, con path specifico = locale. "
            "global: solo catalogo globale. local: solo raccolta locale. both: entrambi."
        ),
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root del progetto per calcolare i percorsi globali. Default: cartella corrente.",
    )
    parser.add_argument(
        "--global-json",
        default="esercizi.json",
        help="Nome/percorso del catalogo globale. Default: esercizi.json.",
    )
    parser.add_argument(
        "--local-json",
        default="",
        help="Nome del JSON locale. Default: <nome-cartella>.json, per esempio dinamica.json.",
    )
    parser.add_argument(
        "--local-index",
        default="index.html",
        help="Nome della pagina locale da generare. Default: index.html.",
    )
    parser.add_argument(
        "--categories-source",
        default="",
        help="JSON da cui copiare subjects/categories, per esempio un vecchio esercizi.json.",
    )
    parser.add_argument(
        "--taxonomy-source",
        choices=["auto", "metadata", "path"],
        default="auto",
        help=(
            "Da dove prendere subject/category/topic. "
            "auto: se il file è in subject/category/topic usa il percorso, altrimenti usa i metadati. "
            "metadata: preferisce i metadati. path: preferisce sempre il percorso."
        ),
    )
    parser.add_argument(
        "--include-index",
        action="store_true",
        help="Include anche file chiamati index.html nella scansione. Di default sono esclusi.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe al primo errore di parsing invece di stampare un avviso.",
    )
    return parser.parse_args()


# -----------------------------------------------------------------------------
# Utility testo/percorso
# -----------------------------------------------------------------------------


def norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def title_case_from_slug(value: str) -> str:
    text = str(value or "").replace("-", " ").replace("_", " ").strip()
    return " ".join(word[:1].upper() + word[1:] for word in text.split())


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i").replace("ò", "o").replace("ù", "u")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "raccolta"


def safe_relative_to(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.resolve()


def path_as_posix(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def first_match(pattern: str, text: str, flags: int = re.DOTALL | re.IGNORECASE) -> str:
    match = re.search(pattern, text, flags)
    return html.unescape(match.group(1).strip()) if match else ""


def short_description_from_html(value: str, max_len: int = 180) -> str:
    text = strip_tags(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def normalize_order(value: Any, default: int = 999999) -> int | float:
    try:
        if isinstance(value, bool) or value is None or value == "":
            return default
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return default


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def infer_from_path(relative_path: Path) -> dict[str, str]:
    parts = [p for p in relative_path.parts if p and p != "."]
    parts = [p for p in parts if not p.lower().endswith((".html", ".htm"))]

    subject = title_case_from_slug(parts[0]) if len(parts) >= 1 else "Fisica"
    category = title_case_from_slug(parts[1]) if len(parts) >= 2 else "Senza categoria"
    topic = title_case_from_slug(parts[2]) if len(parts) >= 3 else ""

    return {
        "subject": subject or "Fisica",
        "category": category or "Senza categoria",
        "topic": topic,
    }


# -----------------------------------------------------------------------------
# Parsing oggetti JS-like
# -----------------------------------------------------------------------------


def strip_js_comments(js_text: str) -> str:
    js_text = re.sub(r"/\*.*?\*/", "", js_text, flags=re.DOTALL)
    js_text = re.sub(r"//.*?$", "", js_text, flags=re.MULTILINE)
    return js_text


def normalize_single_quoted_strings(js_text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(js_text)
    in_string = False
    string_delim = ""
    escape = False

    while i < n:
        ch = js_text[i]

        if not in_string:
            if ch == '"':
                in_string = True
                string_delim = '"'
                out.append(ch)
            elif ch == "'":
                in_string = True
                string_delim = "'"
                out.append('"')
            else:
                out.append(ch)
            i += 1
            continue

        if escape:
            if string_delim == "'" and ch == '"':
                out.append('\\"')
            else:
                out.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            escape = True
            out.append(ch)
            i += 1
            continue

        if ch == string_delim:
            out.append('"' if string_delim == "'" else ch)
            in_string = False
            i += 1
            continue

        if string_delim == "'" and ch == '"':
            out.append('\\"')
        else:
            out.append(ch)
        i += 1

    return "".join(out)


def quote_unquoted_keys(js_text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(js_text)
    in_string = False
    string_delim = ""
    escape = False

    while i < n:
        ch = js_text[i]

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_delim:
                in_string = False
            i += 1
            continue

        if ch in ('"', "'"):
            in_string = True
            string_delim = ch
            out.append(ch)
            i += 1
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (js_text[j].isalnum() or js_text[j] in "_-."):
                j += 1
            k = j
            while k < n and js_text[k].isspace():
                k += 1

            prev_nonspace_idx = len(out) - 1
            while prev_nonspace_idx >= 0 and out[prev_nonspace_idx].isspace():
                prev_nonspace_idx -= 1
            prev_nonspace = out[prev_nonspace_idx] if prev_nonspace_idx >= 0 else ""
            token = js_text[i:j]

            if k < n and js_text[k] == ":" and prev_nonspace in {"", "{", ",", "\n"}:
                out.append(f'"{token}"')
                i = j
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def js_object_to_dict(body: str) -> dict[str, Any]:
    candidate = "{" + body + "}"
    candidate = strip_js_comments(candidate)
    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate).strip()

    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    candidate = normalize_single_quoted_strings(candidate)
    candidate = quote_unquoted_keys(candidate)
    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate).strip()
    data = json.loads(candidate)
    return data if isinstance(data, dict) else {}


def extract_js_metadata(text: str) -> dict[str, Any] | None:
    match = JS_METADATA_REGEX.search(text)
    if not match:
        return None
    return js_object_to_dict(match.group("body"))


# -----------------------------------------------------------------------------
# Parsing data-exercise-statement
# -----------------------------------------------------------------------------


def parse_attrs(attrs_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in ATTR_REGEX.finditer(attrs_text or ""):
        attrs[match.group("name").strip().lower()] = html.unescape(match.group("value"))
    return attrs


def find_elements_with_attr(text: str, attr: str) -> list[tuple[dict[str, str], str]]:
    pattern = re.compile(
        TAG_WITH_ATTR_REGEX_TEMPLATE.format(attr=re.escape(attr)),
        re.DOTALL | re.IGNORECASE,
    )
    items: list[tuple[dict[str, str], str]] = []
    for match in pattern.finditer(text):
        attrs = parse_attrs((match.group("attrs") or "") + " " + (match.group("attrs2") or ""))
        items.append((attrs, match.group("body").strip()))
    return items


def find_first_element_with_attr(text: str, attr: str) -> tuple[dict[str, str], str] | None:
    items = find_elements_with_attr(text, attr)
    return items[0] if items else None


def extract_data_template(text: str, path: Path) -> tuple[dict[str, Any], str, str] | None:
    statement = find_first_element_with_attr(text, "data-exercise-statement")
    if statement is None:
        return None

    attrs, statement_html = statement

    solution = find_first_element_with_attr(text, "data-exercise-solution")
    solution_attrs, solution_html = solution if solution else ({}, "")

    title = (
        attrs.get("data-exercise-title")
        or solution_attrs.get("data-exercise-title")
        or first_match(r"<h1[^>]*>(.*?)</h1>", text)
        or first_match(r"<title[^>]*>(.*?)</title>", text)
        or title_case_from_slug(path.stem)
    )

    description = (
        attrs.get("data-exercise-description")
        or solution_attrs.get("data-exercise-description")
        or short_description_from_html(statement_html)
    )

    metadata = {
        "title": strip_tags(title),
        "description": description,
        "icon": attrs.get("data-exercise-icon", "📄"),
        "order": normalize_order(attrs.get("data-exercise-order"), 999999),
        "tags": normalize_tags(attrs.get("data-exercise-tags", "")),
        "level": attrs.get("data-exercise-level", ""),
        "schoolYear": attrs.get("data-exercise-school-year", ""),
        "estimatedTime": attrs.get("data-exercise-estimated-time", ""),
        "isWip": attrs.get("data-exercise-wip", "").strip().lower() in {"1", "true", "sì", "si", "yes"},
    }

    return metadata, statement_html, solution_html


# -----------------------------------------------------------------------------
# Estrazione esercizio da HTML
# -----------------------------------------------------------------------------


def normalize_metadata(raw: dict[str, Any], path: Path, relative_path: Path, taxonomy_source: str = "auto") -> dict[str, Any]:
    inferred = infer_from_path(relative_path)
    dir_depth = max(0, len(relative_path.parts) - 1)

    title = str(raw.get("title") or raw.get("titolo") or "").strip()
    if not title:
        title = title_case_from_slug(path.stem)

    description = str(raw.get("description") or raw.get("descrizione") or "").strip()
    if not description:
        description = f"Esercizio svolto: {title}."

    raw_subject = str(raw.get("subject") or raw.get("materia") or "").strip()
    raw_category = str(raw.get("category") or raw.get("categoria") or "").strip()
    raw_topic = str(raw.get("topic") or raw.get("argomento") or "").strip()

    # In modalità auto, una struttura a tre livelli come
    # fisica/meccanica/dinamica/file.html è considerata autorevole.
    # Questo evita che vecchi metadati interni, per esempio category: "Dinamica",
    # prevalgano su una cartella più ordinata: subject/category/topic.
    prefer_path = taxonomy_source == "path" or (taxonomy_source == "auto" and dir_depth >= 3)

    if prefer_path:
        subject = inferred["subject"] or raw_subject or "Fisica"
        category = inferred["category"] or raw_category or "Senza categoria"
        topic = inferred["topic"] or raw_topic or ""
    else:
        subject = raw_subject or inferred["subject"] or "Fisica"
        category = raw_category or inferred["category"] or "Senza categoria"
        topic = raw_topic or inferred["topic"] or ""

    result = dict(raw)
    result.update(
        {
            "title": title,
            "description": description,
            "subject": subject,
            "category": category,
            "topic": topic,
            "icon": str(raw.get("icon", raw.get("icona", "📄"))).strip() or "📄",
            "order": normalize_order(raw.get("order", raw.get("ordine", 999999))),
            "tags": normalize_tags(raw.get("tags", [])),
            "level": str(raw.get("level", raw.get("livello", ""))).strip(),
            "schoolYear": str(raw.get("schoolYear", raw.get("anno", ""))).strip(),
            "estimatedTime": str(raw.get("estimatedTime", raw.get("tempo", ""))).strip(),
            "isWip": bool(raw.get("isWip", raw.get("wip", False))),
        }
    )
    return result


def load_exercise_from_html(path: Path, global_root: Path, taxonomy_source: str = "auto") -> ExtractedExercise | None:
    text = path.read_text(encoding="utf-8")
    relative_path = safe_relative_to(path, global_root)

    raw_metadata = extract_js_metadata(text)
    if raw_metadata is not None:
        metadata = normalize_metadata(raw_metadata, path, relative_path, taxonomy_source)
        metadata["file"] = path_as_posix(relative_path)
        return ExtractedExercise(metadata=metadata, source_format="metadata")

    template_data = extract_data_template(text, path)
    if template_data is not None:
        raw, statement_html, solution_html = template_data
        metadata = normalize_metadata(raw, path, relative_path, taxonomy_source)
        metadata["file"] = path_as_posix(relative_path)
        return ExtractedExercise(
            metadata=metadata,
            statement_html=statement_html,
            solution_html=solution_html,
            source_format="data-template",
        )

    return None


def find_html_files(root: Path, include_index: bool = False) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        parts = path.relative_to(root).parts
        if any(part in DEFAULT_EXCLUDED_DIRS for part in parts[:-1]):
            continue
        if not include_index and path.name.lower() == "index.html":
            continue
        files.append(path)
    return sorted(files)


def extract_exercises(scan_dir: Path, global_root: Path, include_index: bool, strict: bool, taxonomy_source: str = "auto") -> tuple[list[ExtractedExercise], list[str]]:
    exercises: list[ExtractedExercise] = []
    warnings: list[str] = []

    for path in find_html_files(scan_dir, include_index=include_index):
        try:
            item = load_exercise_from_html(path, global_root, taxonomy_source)
            if item is None:
                rel = path_as_posix(safe_relative_to(path, global_root))
                warnings.append(
                    f"Template/metadati mancanti in '{rel}'. "
                    "Serve window.EXERCISE_METADATA oppure data-exercise-statement."
                )
                continue
            exercises.append(item)
        except Exception as exc:
            message = f"Errore in '{path}': {exc}"
            if strict:
                raise RuntimeError(message) from exc
            warnings.append(message)

    return exercises, warnings


# -----------------------------------------------------------------------------
# JSON globale
# -----------------------------------------------------------------------------


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": []}

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": data}

    if isinstance(data, dict):
        subjects = data.get("subjects", DEFAULT_SUBJECTS)
        categories = data.get("categories", DEFAULT_CATEGORIES)
        exercises = data.get("exercises", data.get("simulations", []))
        return {
            **data,
            "subjects": subjects if isinstance(subjects, list) else DEFAULT_SUBJECTS,
            "categories": categories if isinstance(categories, list) else DEFAULT_CATEGORIES,
            "exercises": exercises if isinstance(exercises, list) else [],
        }

    raise ValueError(f"Il file JSON '{path}' deve contenere un oggetto oppure una lista.")


def merge_by_name(existing: list[dict[str, Any]], defaults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for item in defaults + existing:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        key = norm(name)
        current = dict(by_name.get(key, {}))
        current.update(item)
        current["name"] = name
        by_name[key] = current
    return list(by_name.values())


def ensure_subjects_and_categories(data: dict[str, Any], exercises: Iterable[dict[str, Any]]) -> None:
    subjects = merge_by_name(data.get("subjects", []), DEFAULT_SUBJECTS)
    categories = merge_by_name(data.get("categories", []), DEFAULT_CATEGORIES)

    subject_keys = {norm(item.get("name")): item for item in subjects}
    category_keys = {norm(item.get("name")): item for item in categories}

    for exercise in exercises:
        subject_name = str(exercise.get("subject", "")).strip() or "Fisica"
        category_name = str(exercise.get("category", "")).strip() or "Senza categoria"

        if norm(subject_name) not in subject_keys:
            item = {
                "name": subject_name,
                "order": 999999,
                "color": "#365f85",
                "description": "",
            }
            subjects.append(item)
            subject_keys[norm(subject_name)] = item

        if norm(category_name) not in category_keys:
            subject = subject_keys.get(norm(subject_name), {})
            item = {
                "name": category_name,
                "subject": subject_name,
                "order": 999999,
                "color": subject.get("color", "#365f85"),
                "description": "",
            }
            categories.append(item)
            category_keys[norm(category_name)] = item

    subjects.sort(key=lambda x: (normalize_order(x.get("order"), 999999), str(x.get("name", ""))))
    categories.sort(key=lambda x: (normalize_order(x.get("order"), 999999), str(x.get("name", ""))))

    data["subjects"] = subjects
    data["categories"] = categories


def merge_exercises(existing: list[dict[str, Any]], extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_file: dict[str, dict[str, Any]] = {}

    for item in existing:
        if not isinstance(item, dict):
            continue
        file_key = str(item.get("file", item.get("path", ""))).strip()
        if not file_key:
            continue
        current = dict(item)
        current["file"] = file_key
        by_file[file_key] = current

    for item in extracted:
        file_key = str(item.get("file", "")).strip()
        if not file_key:
            continue
        current = dict(by_file.get(file_key, {}))
        current.update(item)
        current["file"] = file_key
        by_file[file_key] = current

    # deduplica anche eventuali vecchie voci con stesso titolo ma file diverso non più valido
    # senza cancellare esercizi di altre cartelle.
    return list(by_file.values())


def category_order_map(categories: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            continue
        name = str(category.get("name", "")).strip()
        if not name:
            continue
        result[norm(name)] = float(normalize_order(category.get("order"), 100000 + index))
    return result


def subject_order_map(subjects: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for index, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        name = str(subject.get("name", "")).strip()
        if not name:
            continue
        result[norm(name)] = float(normalize_order(subject.get("order"), 100000 + index))
    return result


def sort_exercises(exercises: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    subject_order = subject_order_map(data.get("subjects", []))
    category_order = category_order_map(data.get("categories", []))

    def key(item: dict[str, Any]) -> tuple[float, float, str, float, str]:
        return (
            subject_order.get(norm(item.get("subject")), 999999),
            category_order.get(norm(item.get("category")), 999999),
            norm(item.get("topic")),
            float(normalize_order(item.get("order"), 999999)),
            norm(item.get("title")),
        )

    return sorted(exercises, key=key)


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def update_global_catalog(scan_root: Path, args: argparse.Namespace) -> int:
    global_json = Path(args.global_json)
    if not global_json.is_absolute():
        global_json = scan_root / global_json

    data = load_json_object(global_json)

    if args.categories_source:
        source = Path(args.categories_source)
        if not source.is_absolute():
            source = scan_root / source
        source_data = load_json_object(source)
        data["subjects"] = source_data.get("subjects", data.get("subjects", DEFAULT_SUBJECTS))
        data["categories"] = source_data.get("categories", data.get("categories", DEFAULT_CATEGORIES))

    extracted, warnings = extract_exercises(scan_root, scan_root, args.include_index, args.strict, args.taxonomy_source)
    extracted_metadata = [item.metadata for item in extracted]

    ensure_subjects_and_categories(data, extracted_metadata)
    existing = data.get("exercises", [])
    if not isinstance(existing, list):
        existing = []

    data["exercises"] = sort_exercises(merge_exercises(existing, extracted_metadata), data)
    data.pop("simulations", None)

    write_json(data, global_json)

    print(f"Catalogo globale aggiornato: {path_as_posix(global_json.relative_to(scan_root) if global_json.is_relative_to(scan_root) else global_json)}")
    print(f" - Esercizi trovati nella scansione: {len(extracted_metadata)}")
    print(f" - Esercizi totali nel catalogo: {len(data['exercises'])}")
    for item in extracted_metadata:
        print(f"   - {item.get('title', '<senza titolo>')} [{item.get('file', '')}]")

    if warnings:
        print("Avvisi durante la scansione:", file=sys.stderr)
        for warning in warnings:
            print(f" - {warning}", file=sys.stderr)

    return len(extracted_metadata)


# -----------------------------------------------------------------------------
# Raccolta locale
# -----------------------------------------------------------------------------


def local_collection_title(local_dir: Path) -> str:
    return title_case_from_slug(local_dir.name)


def make_local_json_name(local_dir: Path, explicit_name: str = "") -> str:
    if explicit_name:
        return explicit_name
    return f"{slugify(local_dir.name)}.json"


def make_local_exercise_item(item: ExtractedExercise, local_dir: Path, global_root: Path) -> dict[str, Any]:
    metadata = dict(item.metadata)
    absolute_file = global_root / metadata.get("file", "")
    if not absolute_file.exists():
        # fallback: se metadata['file'] era già relativo a local_dir o assoluto
        candidate = Path(str(metadata.get("file", "")))
        absolute_file = candidate if candidate.is_absolute() else local_dir / candidate

    local_file = safe_relative_to(absolute_file, local_dir)
    metadata["file"] = path_as_posix(local_file)
    metadata["sourceFormat"] = item.source_format

    if item.statement_html:
        metadata["statement"] = item.statement_html
    if item.solution_html:
        metadata["solution"] = item.solution_html

    return metadata


def make_local_catalog(local_dir: Path, global_root: Path, extracted: list[ExtractedExercise]) -> dict[str, Any]:
    title = local_collection_title(local_dir)
    rel = safe_relative_to(local_dir, global_root)
    inferred = infer_from_path(rel)

    exercises = [make_local_exercise_item(item, local_dir, global_root) for item in extracted]
    exercises = sorted(
        exercises,
        key=lambda item: (
            float(normalize_order(item.get("order"), 999999)),
            norm(item.get("title")),
        ),
    )

    return {
        "collection": {
            "title": title,
            "subject": inferred.get("subject", ""),
            "category": inferred.get("category", ""),
            "topic": inferred.get("topic", title),
            "path": path_as_posix(rel),
            "count": len(exercises),
        },
        "exercises": exercises,
    }


def local_index_html(catalog_file: str) -> str:
    safe_catalog = html.escape(catalog_file, quote=True)
    return f"""<!DOCTYPE html>
<html lang=\"it\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Raccolta esercizi</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css\">
  <script defer src=\"https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js\"></script>
  <script defer src=\"https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js\"></script>
  <style>
    :root {{
      --bg: #f6f4ef;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --border: #d8d3c7;
      --accent: #365f85;
      --accent-soft: rgba(54,95,133,.12);
      --shadow: 0 14px 34px rgba(0,0,0,.065);
      --radius: 22px;
      --sans: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: var(--sans);
      color: var(--text);
      background: radial-gradient(circle at 8% 4%, rgba(54,95,133,.13), transparent 22rem), var(--bg);
    }}
    .shell {{ width: min(980px, calc(100% - 2rem)); margin: 0 auto; }}
    header {{ padding: 3.2rem 0 1.7rem; }}
    h1 {{ margin: 0; font-size: clamp(2.2rem, 6vw, 4.5rem); line-height: .95; letter-spacing: -.055em; }}
    .subtitle {{ margin-top: .9rem; color: var(--muted); line-height: 1.55; }}
    .toolbar {{ display: flex; gap: .7rem; margin: 1.5rem 0; flex-wrap: wrap; }}
    input, select {{ border: 1px solid var(--border); border-radius: 999px; padding: .75rem .95rem; background: #fff; color: var(--text); font-size: .95rem; }}
    input {{ flex: 1 1 260px; }}
    .list {{ display: grid; gap: 1rem; padding-bottom: 4rem; }}
    .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }}
    .card-head {{ padding: 1.1rem 1.25rem; display: flex; gap: .8rem; align-items: flex-start; justify-content: space-between; }}
    .card-title {{ margin: 0; font-size: 1.15rem; line-height: 1.25; }}
    .desc {{ margin: .45rem 0 0; color: var(--muted); line-height: 1.55; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .75rem; }}
    .pill {{ font-size: .75rem; padding: .24rem .52rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 700; }}
    .statement {{ padding: 0 1.25rem 1.1rem; color: var(--text); line-height: 1.65; }}
    .actions {{ padding: .85rem 1.25rem; border-top: 1px solid var(--border); display: flex; gap: .65rem; flex-wrap: wrap; }}
    button, .open-link {{ border: 1px solid var(--border); background: #fff; color: var(--accent); border-radius: 999px; padding: .58rem .78rem; font-weight: 750; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; }}
    button:hover, .open-link:hover {{ border-color: var(--accent); }}
    .solution {{ display: none; padding: 1.1rem 1.25rem 1.25rem; border-top: 1px dashed var(--border); line-height: 1.65; }}
    .card.open .solution {{ display: block; }}
    .empty, .error {{ background: #fff; border: 1px dashed var(--border); border-radius: var(--radius); padding: 2rem; color: var(--muted); line-height: 1.6; }}
    svg, canvas, img {{ max-width: 100%; }}
    @media (max-width: 680px) {{ .card-head {{ flex-direction: column; }} }}
  </style>
</head>
<body>
  <header class=\"shell\">
    <h1 id=\"title\">Raccolta esercizi</h1>
    <p id=\"subtitle\" class=\"subtitle\">Caricamento...</p>
    <div class=\"toolbar\">
      <input id=\"search\" type=\"search\" placeholder=\"Cerca esercizio...\" />
      <select id=\"level\"><option value=\"\">Tutti i livelli</option></select>
    </div>
  </header>
  <main class=\"shell\">
    <section id=\"list\" class=\"list\"><div class=\"empty\">Caricamento raccolta...</div></section>
  </main>

  <script>
    const CATALOG_FILE = \"{safe_catalog}\";
    const state = {{ exercises: [], filtered: [] }};
    const titleEl = document.getElementById('title');
    const subtitleEl = document.getElementById('subtitle');
    const listEl = document.getElementById('list');
    const searchEl = document.getElementById('search');
    const levelEl = document.getElementById('level');

    function esc(value) {{
      return String(value ?? '')
        .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
        .replaceAll('\\"','&quot;').replaceAll("'",'&#039;');
    }}
    function norm(value) {{
      return String(value ?? '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').trim();
    }}
    function levelLabel(value) {{
      const n = norm(value);
      if (n === 'base') return 'Base';
      if (n === 'intermedio') return 'Intermedio';
      if (n === 'avanzato') return 'Avanzato';
      return value || '';
    }}
    function renderMath() {{
      if (window.renderMathInElement) {{
        renderMathInElement(document.body, {{
          delimiters: [
            {{left: '$$', right: '$$', display: true}},
            {{left: '$', right: '$', display: false}}
          ],
          throwOnError: false
        }});
      }}
    }}
    function fillFilters() {{
      const levels = [...new Set(state.exercises.map(e => e.level).filter(Boolean))].sort();
      for (const level of levels) {{
        const opt = document.createElement('option');
        opt.value = level;
        opt.textContent = levelLabel(level);
        levelEl.appendChild(opt);
      }}
    }}
    function applyFilters() {{
      const q = norm(searchEl.value);
      const level = levelEl.value;
      state.filtered = state.exercises.filter(e => {{
        const haystack = norm([e.title, e.description, e.category, e.topic, e.level, ...(e.tags || [])].join(' '));
        return (!q || haystack.includes(q)) && (!level || e.level === level);
      }});
      renderList();
    }}
    function renderList() {{
      if (!state.filtered.length) {{
        listEl.innerHTML = '<div class=\"empty\">Nessun esercizio trovato.</div>';
        return;
      }}
      listEl.innerHTML = state.filtered.map((e, i) => {{
        const tags = (e.tags || []).slice(0, 8).map(t => `<span class=\"pill\">#${{esc(t)}}</span>`).join('');
        const statement = e.statement ? `<div class=\"statement\">${{e.statement}}</div>` : '';
        const solutionButton = e.solution ? `<button type=\"button\" data-toggle=\"${{i}}\">Mostra soluzione</button>` : '';
        const solution = e.solution ? `<div class=\"solution\"><strong>Soluzione</strong><br>${{e.solution}}</div>` : '';
        const openLink = e.file ? `<a class=\"open-link\" href=\"${{esc(e.file)}}\">Apri pagina esercizio →</a>` : '';
        return `
          <article class=\"card\" data-index=\"${{i}}\">
            <div class=\"card-head\">
              <div>
                <h2 class=\"card-title\">${{esc(e.icon || '')}} ${{esc(e.title || 'Esercizio senza titolo')}}</h2>
                <p class=\"desc\">${{esc(e.description || '')}}</p>
                <div class=\"meta\">
                  ${{e.level ? `<span class=\"pill\">${{esc(levelLabel(e.level))}}</span>` : ''}}
                  ${{e.estimatedTime ? `<span class=\"pill\">${{esc(e.estimatedTime)}}</span>` : ''}}
                  ${{tags}}
                </div>
              </div>
            </div>
            ${{statement}}
            <div class=\"actions\">${{solutionButton}}${{openLink}}</div>
            ${{solution}}
          </article>`;
      }}).join('');
      renderMath();
    }}

    listEl.addEventListener('click', event => {{
      const btn = event.target.closest('button[data-toggle]');
      if (!btn) return;
      const card = btn.closest('.card');
      card.classList.toggle('open');
      btn.textContent = card.classList.contains('open') ? 'Nascondi soluzione' : 'Mostra soluzione';
    }});
    searchEl.addEventListener('input', applyFilters);
    levelEl.addEventListener('change', applyFilters);

    fetch(CATALOG_FILE, {{ cache: 'no-store' }})
      .then(r => {{ if (!r.ok) throw new Error('Errore nel caricamento'); return r.json(); }})
      .then(data => {{
        const collection = data.collection || {{}};
        state.exercises = Array.isArray(data.exercises) ? data.exercises : [];
        titleEl.textContent = collection.title ? `Esercizi di ${{collection.title}}` : 'Raccolta esercizi';
        subtitleEl.textContent = `${{collection.subject || ''}}${{collection.category ? ' · ' + collection.category : ''}}${{collection.topic ? ' · ' + collection.topic : ''}} — ${{state.exercises.length}} esercizi`;
        fillFilters();
        applyFilters();
      }})
      .catch(error => {{
        listEl.innerHTML = `<div class=\"error\"><strong>Non è stato possibile caricare ${{esc(CATALOG_FILE)}}.</strong><br>Controlla che il JSON sia nella stessa cartella di questa pagina e che sia valido. Per testare in locale usa <code>python -m http.server</code>.</div>`;
        console.error(error);
      }});
  </script>
</body>
</html>
"""


def update_local_collection(local_dir: Path, global_root: Path, args: argparse.Namespace) -> int:
    local_dir = local_dir.resolve()
    if not local_dir.exists() or not local_dir.is_dir():
        raise FileNotFoundError(f"La cartella locale non esiste: {local_dir}")

    extracted, warnings = extract_exercises(local_dir, global_root, args.include_index, args.strict, args.taxonomy_source)
    catalog = make_local_catalog(local_dir, global_root, extracted)

    local_json_name = make_local_json_name(local_dir, args.local_json)
    local_json_path = local_dir / local_json_name
    local_index_path = local_dir / args.local_index

    write_json(catalog, local_json_path)
    local_index_path.write_text(local_index_html(local_json_name), encoding="utf-8", newline="\n")

    print(f"Raccolta locale aggiornata: {path_as_posix(safe_relative_to(local_dir, global_root))}")
    print(f" - JSON locale: {local_json_name}")
    print(f" - Pagina locale: {args.local_index}")
    print(f" - index.html carica: {local_json_name}")
    print(f" - Esercizi trovati: {len(extracted)}")
    for item in catalog["exercises"]:
        print(f"   - {item.get('title', '<senza titolo>')} [{item.get('file', '')}]")

    if warnings:
        print("Avvisi durante la scansione:", file=sys.stderr)
        for warning in warnings:
            print(f" - {warning}", file=sys.stderr)

    return len(extracted)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def resolve_mode(args: argparse.Namespace, root: Path, target: Path) -> str:
    if args.mode != "auto":
        return args.mode
    try:
        same = target.resolve() == root.resolve()
    except FileNotFoundError:
        same = False
    return "global" if same else "local"


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    target = Path(args.path)
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()

    if not root.exists() or not root.is_dir():
        print(f"Errore: root del progetto non valida: {root}", file=sys.stderr)
        return 1
    if not target.exists() or not target.is_dir():
        print(f"Errore: cartella non valida: {target}", file=sys.stderr)
        return 1

    mode = resolve_mode(args, root, target)

    try:
        if mode == "global":
            update_global_catalog(root, args)
        elif mode == "local":
            update_local_collection(target, root, args)
        elif mode == "both":
            update_local_collection(target, root, args)
            print("")
            update_global_catalog(root, args)
        else:
            raise ValueError(f"Modalità non riconosciuta: {mode}")
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
