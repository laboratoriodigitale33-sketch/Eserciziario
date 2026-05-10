#!/usr/bin/env python3
"""
generate_exercises.py

Genera o aggiorna esercizi.json leggendo i metadati dai file HTML degli esercizi.

Formato metadati atteso dentro ogni file HTML:

<script>
window.EXERCISE_METADATA = {
  title: "Secondo principio della dinamica su piano orizzontale",
  description: "Esercizio svolto sull'applicazione di F = m a.",
  category: "Meccanica",
  topic: "Dinamica",
  subject: "Fisica",
  icon: "➡️",
  order: 10,
  tags: ["dinamica", "forza", "accelerazione"],
  level: "base",
  schoolYear: "Seconda superiore",
  estimatedTime: "10 min"
};
</script>

Il file HTML verrà inserito automaticamente nel campo "file".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


METADATA_REGEX = re.compile(
    r"window\.(?:EXERCISE_METADATA|ESERCIZIO_METADATA)\s*=\s*\{(?P<body>.*?)\}\s*;",
    re.DOTALL | re.IGNORECASE,
)

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    "assets",
    "old",
    "theory",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggiorna esercizi.json leggendo i metadati dai file HTML."
    )
    parser.add_argument(
        "--input",
        default=".",
        help="Cartella da scandire ricorsivamente. Default: cartella corrente.",
    )
    parser.add_argument(
        "--json",
        default="esercizi.json",
        help="File JSON da creare o aggiornare. Default: esercizi.json.",
    )
    parser.add_argument(
        "--categories-source",
        default="",
        help=(
            "File JSON da cui copiare la lista 'categories'. "
            "Esempio: simulations.json. Se omesso, conserva le categorie già presenti in esercizi.json."
        ),
    )
    parser.add_argument(
        "--category-source",
        choices=["auto", "metadata", "folder"],
        default="auto",
        help=(
            "Come determinare la categoria dell'esercizio: "
            "'metadata' usa category dai metadati, "
            "'folder' usa la prima cartella del percorso, "
            "'auto' usa category se presente, altrimenti deduce dalla cartella."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe l'esecuzione al primo file con metadati invalidi.",
    )
    parser.add_argument(
        "--include-index",
        action="store_true",
        help="Include index.html nella scansione. Di default viene escluso.",
    )
    return parser.parse_args()


def find_html_files(root: Path, include_index: bool) -> list[Path]:
    html_files: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {".html", ".htm"}:
            continue

        relative_parts = path.relative_to(root).parts
        if any(part in DEFAULT_EXCLUDED_DIRS for part in relative_parts[:-1]):
            continue

        if not include_index and path.name.lower() == "index.html":
            continue

        html_files.append(path)

    return sorted(html_files)


def extract_metadata_block(text: str) -> str | None:
    match = METADATA_REGEX.search(text)
    if not match:
        return None
    return "{" + match.group("body") + "}"


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
            while j < n and (js_text[j].isalnum() or js_text[j] in "_-"):
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


def js_object_to_json(js_text: str) -> str:
    js_text = strip_js_comments(js_text)

    candidate = re.sub(r",(\s*[}\]])", r"\1", js_text).strip()
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    js_text = normalize_single_quoted_strings(js_text)
    js_text = quote_unquoted_keys(js_text)
    js_text = re.sub(r",(\s*[}\]])", r"\1", js_text)
    return js_text.strip()


def normalize_order(value: Any, path: Path) -> int | float:
    try:
        if isinstance(value, bool):
            raise TypeError
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else value
        if isinstance(value, str):
            n = float(value)
            return int(n) if n.is_integer() else n
        raise TypeError
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Il campo 'order' deve essere numerico in '{path}'.") from exc


def title_case_from_slug(value: str) -> str:
    text = value.replace("-", " ").replace("_", " ").strip()
    return " ".join(word[:1].upper() + word[1:] for word in text.split())


def infer_category_from_path(relative_path: Path) -> str:
    parts = list(relative_path.parts)
    if len(parts) <= 1:
        return "Senza categoria"
    return title_case_from_slug(parts[0])


def choose_category(raw: dict[str, Any], relative_path: Path, mode: str) -> str:
    from_folder = infer_category_from_path(relative_path)
    from_metadata = str(raw.get("category", "")).strip()

    if mode == "folder":
        return from_folder
    if mode == "metadata":
        return from_metadata or from_folder
    return from_metadata or from_folder


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def load_metadata_from_html(path: Path, root: Path, category_source: str) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    block = extract_metadata_block(text)
    if block is None:
        return None

    json_like = js_object_to_json(block)

    try:
        raw = json.loads(json_like)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Metadati non validi in '{path}': {exc}. "
            "Consiglio: usa chiavi e stringhe tra doppi apici e separa ogni riga con una virgola."
        ) from exc

    required = ["title", "description", "order"]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Metadati mancanti in '{path}': {', '.join(missing)}")

    relative_path = path.relative_to(root)

    result = dict(raw)
    result["file"] = relative_path.as_posix()
    result["title"] = str(raw["title"]).strip()
    result["description"] = str(raw["description"]).strip()
    result["category"] = choose_category(raw, relative_path, category_source)
    result["topic"] = str(raw.get("topic", "")).strip()
    result["subject"] = str(raw.get("subject", "")).strip()
    result["icon"] = str(raw.get("icon", "📄")).strip()
    result["order"] = normalize_order(raw["order"], path)
    result["tags"] = normalize_tags(raw.get("tags", []))
    result["level"] = str(raw.get("level", "")).strip()
    result["schoolYear"] = str(raw.get("schoolYear", "")).strip()
    result["estimatedTime"] = str(raw.get("estimatedTime", "")).strip()
    result["isWip"] = bool(raw.get("isWip", False))

    return result


def load_json_object(json_path: Path) -> dict[str, Any]:
    if not json_path.exists():
        return {"categories": [], "exercises": []}

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Il file JSON '{json_path}' non è valido: {exc}") from exc

    if isinstance(data, list):
        return {"categories": [], "exercises": data}

    if isinstance(data, dict):
        categories = data.get("categories", [])
        exercises = data.get("exercises", data.get("simulations", []))
        return {
            **data,
            "categories": categories if isinstance(categories, list) else [],
            "exercises": exercises if isinstance(exercises, list) else [],
        }

    raise ValueError(f"Il file JSON '{json_path}' deve contenere un oggetto oppure una lista.")


def load_categories_from_source(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File categorie non trovato: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
        raise ValueError(f"Il file '{path}' non contiene una lista 'categories' valida.")

    return data["categories"]


def _norm_title(value: Any) -> str:
    return str(value).strip().casefold()


def merge_exercises(existing: list[dict[str, Any]], extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extracted_by_file: dict[str, dict[str, Any]] = {
        str(item["file"]): dict(item)
        for item in extracted
        if isinstance(item, dict) and "file" in item
    }

    extracted_titles: set[str] = {
        _norm_title(item.get("title", ""))
        for item in extracted_by_file.values()
    }

    merged: dict[str, dict[str, Any]] = {}

    for item in existing:
        if not isinstance(item, dict):
            continue

        file_key = str(item.get("file", item.get("path", ""))).strip()
        title_key = _norm_title(item.get("title", ""))

        if not file_key:
            continue

        if file_key in extracted_by_file:
            current = dict(item)
            current.update(extracted_by_file[file_key])
            merged[file_key] = current
            continue

        if title_key and title_key in extracted_titles:
            continue

        item = dict(item)
        item["file"] = file_key
        merged[file_key] = item

    for file_key, item in extracted_by_file.items():
        current = dict(merged.get(file_key, {}))
        current.update(item)
        merged[file_key] = current

    dedup_by_title: dict[str, dict[str, Any]] = {}
    for item in merged.values():
        title_key = _norm_title(item.get("title", ""))
        key = title_key if title_key else f"__file__:{item.get('file', '')}"
        dedup_by_title[key] = item

    return list(dedup_by_title.values())


def category_order_map(categories: list[dict[str, Any]]) -> dict[str, float]:
    mapping: dict[str, float] = {}

    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            continue

        name = str(category.get("name", "")).strip()
        if not name:
            continue

        try:
            order = float(category.get("order", 100000 + index))
        except (TypeError, ValueError):
            order = float(100000 + index)

        mapping[name.casefold()] = order

    return mapping


def sort_exercises(exercises: list[dict[str, Any]], categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cat_order = category_order_map(categories)

    def sort_key(item: dict[str, Any]) -> tuple[float, str, float, str]:
        category = str(item.get("category", "")).strip()
        topic = str(item.get("topic", "")).casefold()

        try:
            order = float(item.get("order", 999999))
        except (TypeError, ValueError):
            order = float(999999)

        title = str(item.get("title", "")).casefold()
        return (cat_order.get(category.casefold(), 999999), topic, order, title)

    return sorted(exercises, key=sort_key)


def write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    args = parse_args()

    input_dir = Path(args.input).resolve()
    json_path = Path(args.json).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Errore: la cartella di input non esiste o non è una directory: {input_dir}", file=sys.stderr)
        return 1

    try:
        data = load_json_object(json_path)
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    if args.categories_source:
        try:
            data["categories"] = load_categories_from_source(Path(args.categories_source).resolve())
        except Exception as exc:
            print(f"Errore nel caricamento delle categorie: {exc}", file=sys.stderr)
            return 1

    html_files = find_html_files(input_dir, include_index=args.include_index)
    extracted: list[dict[str, Any]] = []
    warnings: list[str] = []

    for path in html_files:
        try:
            metadata = load_metadata_from_html(path, input_dir, args.category_source)
            if metadata is not None:
                extracted.append(metadata)
        except Exception as exc:
            if args.strict:
                print(f"Errore: {exc}", file=sys.stderr)
                return 1
            warnings.append(str(exc))

    if warnings:
        print("Avvisi durante la scansione:", file=sys.stderr)
        for warning in warnings:
            print(f" - {warning}", file=sys.stderr)

    if extracted:
        print(f"Esercizi trovati: {len(extracted)}")
        for item in extracted:
            print(f" - {item.get('title', '<senza titolo>')}  [{item.get('file', '<percorso sconosciuto>')}]")
    else:
        print("Esercizi trovati: nessuno")

    existing_exercises = data.get("exercises", [])
    if not isinstance(existing_exercises, list):
        print("Errore: la chiave 'exercises' del JSON deve contenere una lista.", file=sys.stderr)
        return 1

    data["exercises"] = sort_exercises(
        merge_exercises(existing_exercises, extracted),
        data.get("categories", []),
    )

    data.pop("simulations", None)

    try:
        write_json(data, json_path)
    except Exception as exc:
        print(f"Errore durante la scrittura del JSON: {exc}", file=sys.stderr)
        return 1

    print(f"Aggiornato il file '{json_path.name}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
