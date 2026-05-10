#!/usr/bin/env python3
"""
generate_exercises.py

Generatore per Eserciziario.

Uso consigliato dalla directory principale del progetto:

  python generate_exercises.py
      Modalità globale: scansiona le raccolte sotto fisica/ e matematica/,
      genera gli index locali e aggiorna esercizi.json nella directory principale.

  python generate_exercises.py matematica/<cartella-raccolta>
  python generate_exercises.py fisica/<cartella-raccolta>
      Modalità locale: scansiona solo la cartella indicata, genera
      <nome-cartella>.json e index.html dentro quella cartella, senza
      modificare esercizi.json globale.

Esempi:

  python generate_exercises.py matematica/limiti
  python generate_exercises.py matematica/geometria-analitica/circonferenza
  python generate_exercises.py fisica/dinamica/secondo-principio

Ogni file HTML-esercizio deve contenere:

<script>
window.EXERCISE_METADATA = {
  title: "Forma indeterminata 0/0",
  description: "Limite risolto tramite scomposizione.",
  subject: "Matematica",
  category: "Analisi",
  topic: "Limiti",
  collection: "Limiti",
  collectionDescription: "Esercizi svolti sui limiti.",
  icon: "∞",
  order: 10,
  tags: ["limiti", "zero su zero"],
  level: "base",
  schoolYear: "Quinta superiore",
  estimatedTime: "6 min",
  isWip: false
};
</script>

<template data-exercise-statement>
  ... testo dell'esercizio ...
</template>

<template data-exercise-solution>
  ... soluzione dell'esercizio ...
</template>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


METADATA_REGEX = re.compile(
    r"window\.(?:EXERCISE_METADATA|ESERCIZIO_METADATA)\s*=\s*\{(?P<body>.*?)\}\s*;",
    re.DOTALL | re.IGNORECASE,
)

TEMPLATE_REGEX_TEMPLATE = r"<template\b(?=[^>]*\b{attr}\b)[^>]*>(?P<body>.*?)</template>"

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    "assets",
    "old",
    "theory",
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

SUBJECT_ROOTS = {
    "fisica": "Fisica",
    "matematica": "Matematica",
}

DEFAULT_CATEGORY_COLORS = {
    "analisi": "#8f6f3d",
    "algebra": "#6f8f3d",
    "geometria": "#7c6fbd",
    "geometria analitica": "#7c6fbd",
    "trigonometria": "#bd7c6f",
    "probabilita": "#3d8f75",
    "probabilità": "#3d8f75",
    "dinamica": "#5bd4c4",
    "cinematica": "#5bc8f0",
    "elettrostatica": "#f07070",
}


@dataclass
class ExerciseSource:
    path: Path
    relative_to_collection: str
    relative_to_root: str
    metadata: dict[str, Any]
    statement_html: str
    solution_html: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera JSON e pagine index per le raccolte di esercizi.",
        epilog=(
            "Esempi: python generate_exercises.py | "
            "python generate_exercises.py matematica/limiti | "
            "python generate_exercises.py fisica/dinamica/piano-inclinato"
        ),
    )

    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Cartella da processare. Se omessa o uguale a '.', usa la modalità globale. "
            "In modalità locale usa un percorso sotto matematica/ o fisica/, per esempio "
            "matematica/limiti oppure fisica/dinamica/piano-inclinato."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "global", "local"],
        default="auto",
        help="Forza la modalità di esecuzione. Default: auto.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Radice del progetto. Default: cartella corrente.",
    )
    parser.add_argument(
        "--global-json",
        "--json",
        dest="global_json",
        default="esercizi.json",
        help="Nome del JSON principale. Default: esercizi.json.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Alias legacy per indicare la cartella di input.",
    )
    parser.add_argument(
        "--local-json",
        default="",
        help="Nome del JSON locale. Se omesso: <nome-cartella>.json.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="In modalità locale scansiona ricorsivamente anche le sottocartelle.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Genera solo il JSON locale, senza scrivere index.html.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe l'esecuzione al primo errore sui metadati.",
    )
    parser.add_argument(
        "--include-index",
        action="store_true",
        help="Include index.html nella scansione. Sconsigliato: di default gli index generati sono esclusi.",
    )

    # Argomenti mantenuti per compatibilità con la versione precedente.
    parser.add_argument("--categories-source", default="", help=argparse.SUPPRESS)
    parser.add_argument(
        "--category-source",
        choices=["auto", "metadata", "folder"],
        default="auto",
        help=argparse.SUPPRESS,
    )

    return parser.parse_args()


def normalize_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def title_case_from_slug(value: str) -> str:
    text = value.replace("-", " ").replace("_", " ").strip()
    return " ".join(word[:1].upper() + word[1:] for word in text.split())


def path_relative_to_root(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def subject_from_parts(parts: Iterable[str]) -> str:
    parts = list(parts)
    if not parts:
        return ""
    return SUBJECT_ROOTS.get(normalize_key(parts[0]), title_case_from_slug(parts[0]))


def is_subject_collection_target(target_dir: Path, root: Path) -> tuple[bool, str]:
    rel = path_relative_to_root(target_dir, root)
    if rel is None:
        return False, "La cartella indicata deve stare dentro la radice del progetto."

    parts = rel.parts
    if len(parts) < 2:
        return (
            False,
            "La modalità locale richiede una cartella-raccolta dentro 'matematica/' o 'fisica/'. "
            "Esempi: matematica/limiti oppure fisica/dinamica."
        )

    if normalize_key(parts[0]) not in SUBJECT_ROOTS:
        return (
            False,
            "La modalità locale accetta percorsi che iniziano con 'matematica/' oppure 'fisica/'. "
            f"Percorso ricevuto: {rel.as_posix()}"
        )

    return True, ""


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


def extract_metadata(text: str, path: Path) -> dict[str, Any] | None:
    match = METADATA_REGEX.search(text)
    if not match:
        return None

    block = "{" + match.group("body") + "}"
    json_like = js_object_to_json(block)

    try:
        raw = json.loads(json_like)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Metadati non validi in '{path}': {exc}. "
            "Usa chiavi/stringhe tra doppi apici o una sintassi JS semplice."
        ) from exc

    missing = [key for key in ("title", "description", "order") if key not in raw]
    if missing:
        raise ValueError(f"Metadati mancanti in '{path}': {', '.join(missing)}")

    return raw


def extract_template(text: str, attr: str) -> str:
    pattern = TEMPLATE_REGEX_TEMPLATE.format(attr=re.escape(attr))
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return match.group("body").strip()


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


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def normalize_metadata(raw: dict[str, Any], path: Path, collection_dir: Path, root: Path) -> dict[str, Any]:
    relative_to_collection = path.relative_to(collection_dir).as_posix()
    try:
        relative_to_root = path.relative_to(root).as_posix()
    except ValueError:
        relative_to_root = relative_to_collection

    rel = path_relative_to_root(path, root)
    inferred_parts = list(rel.parts) if rel is not None else list(path.parts)
    inferred_subject = subject_from_parts(inferred_parts)
    inferred_topic = title_case_from_slug(collection_dir.name)

    result = dict(raw)
    result["title"] = str(raw["title"]).strip()
    result["description"] = str(raw["description"]).strip()
    result["subject"] = str(raw.get("subject") or inferred_subject or "Matematica").strip()
    result["category"] = str(raw.get("category") or inferred_topic or "Senza categoria").strip()
    result["topic"] = str(raw.get("topic") or inferred_topic or "").strip()
    result["collection"] = str(raw.get("collection") or raw.get("collectionTitle") or inferred_topic).strip()
    result["collectionDescription"] = str(raw.get("collectionDescription") or "").strip()
    result["collectionOrder"] = normalize_order(raw.get("collectionOrder", raw.get("order", 999999)), path)
    result["icon"] = str(raw.get("icon", "📄")).strip()
    result["order"] = normalize_order(raw["order"], path)
    result["tags"] = normalize_tags(raw.get("tags", []))
    result["level"] = str(raw.get("level", "")).strip()
    result["schoolYear"] = str(raw.get("schoolYear", "")).strip()
    result["estimatedTime"] = str(raw.get("estimatedTime", "")).strip()
    result["isWip"] = bool(raw.get("isWip", False))
    result["file"] = relative_to_collection
    result["sourceFile"] = relative_to_root
    return result


def should_skip_path(path: Path, root: Path, include_index: bool) -> bool:
    if path.suffix.lower() not in {".html", ".htm"}:
        return True

    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts

    if any(part in DEFAULT_EXCLUDED_DIRS for part in relative_parts[:-1]):
        return True

    if not include_index and path.name.lower() == "index.html":
        return True

    return False


def find_html_files(directory: Path, recursive: bool, include_index: bool) -> list[Path]:
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    files: list[Path] = []
    for path in iterator:
        if not path.is_file():
            continue
        if should_skip_path(path, directory, include_index=include_index):
            continue
        files.append(path)
    return sorted(files)


def load_exercise_sources(
    collection_dir: Path,
    root: Path,
    recursive: bool,
    include_index: bool,
    strict: bool,
) -> tuple[list[ExerciseSource], list[str]]:
    exercises: list[ExerciseSource] = []
    warnings: list[str] = []

    for path in find_html_files(collection_dir, recursive=recursive, include_index=include_index):
        try:
            text = path.read_text(encoding="utf-8")
            raw = extract_metadata(text, path)
            if raw is None:
                continue

            metadata = normalize_metadata(raw, path, collection_dir, root)
            statement_html = extract_template(text, "data-exercise-statement")
            solution_html = extract_template(text, "data-exercise-solution")

            if not statement_html:
                raise ValueError(f"Template data-exercise-statement mancante in '{path}'.")
            if not solution_html:
                raise ValueError(f"Template data-exercise-solution mancante in '{path}'.")

            exercises.append(
                ExerciseSource(
                    path=path,
                    relative_to_collection=path.relative_to(collection_dir).as_posix(),
                    relative_to_root=path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name,
                    metadata=metadata,
                    statement_html=statement_html,
                    solution_html=solution_html,
                )
            )
        except Exception as exc:
            if strict:
                raise
            warnings.append(str(exc))

    exercises.sort(key=lambda item: (float(item.metadata.get("order", 999999)), item.metadata.get("title", "")))
    return exercises, warnings


def make_collection_metadata(collection_dir: Path, exercises: list[ExerciseSource], root: Path) -> dict[str, Any]:
    if not exercises:
        title = title_case_from_slug(collection_dir.name)
        return {
            "title": title,
            "description": f"Raccolta di esercizi svolti: {title}.",
            "subject": infer_subject_from_path(collection_dir, root),
            "category": title,
            "topic": title,
            "icon": "📄",
            "order": 999999,
            "tags": [],
            "level": "",
            "schoolYear": "",
            "estimatedTime": "",
            "isWip": False,
            "count": 0,
        }

    first = exercises[0].metadata
    collection_title = str(first.get("collection") or first.get("topic") or title_case_from_slug(collection_dir.name)).strip()
    collection_description = str(first.get("collectionDescription") or "").strip()
    if not collection_description:
        collection_description = f"Raccolta di esercizi svolti su {collection_title.lower()}."

    all_tags: list[str] = []
    for exercise in exercises:
        for tag in exercise.metadata.get("tags", []):
            if tag not in all_tags:
                all_tags.append(tag)

    levels = sorted({exercise.metadata.get("level", "") for exercise in exercises if exercise.metadata.get("level", "")})
    school_years = sorted({exercise.metadata.get("schoolYear", "") for exercise in exercises if exercise.metadata.get("schoolYear", "")})

    return {
        "title": collection_title,
        "description": collection_description,
        "subject": str(first.get("subject", "")).strip(),
        "category": str(first.get("category", "")).strip(),
        "topic": str(first.get("topic", collection_title)).strip(),
        "icon": str(first.get("icon", "📄")).strip(),
        "order": min(float(ex.metadata.get("collectionOrder", ex.metadata.get("order", 999999))) for ex in exercises),
        "tags": all_tags,
        "level": levels[0] if len(levels) == 1 else "",
        "schoolYear": school_years[0] if len(school_years) == 1 else "",
        "estimatedTime": estimate_total_time(exercises),
        "isWip": any(bool(ex.metadata.get("isWip", False)) for ex in exercises),
        "count": len(exercises),
    }


def estimate_total_time(exercises: list[ExerciseSource]) -> str:
    total = 0
    found = False
    for exercise in exercises:
        text = str(exercise.metadata.get("estimatedTime", ""))
        match = re.search(r"(\d+(?:[\.,]\d+)?)", text)
        if not match:
            continue
        found = True
        total += int(round(float(match.group(1).replace(",", "."))))
    return f"{total} min" if found and total > 0 else ""


def infer_subject_from_path(path: Path, root: Path) -> str:
    rel = path_relative_to_root(path, root)
    if rel is not None and rel.parts:
        return subject_from_parts(rel.parts)
    return "Matematica"


def build_local_catalog(collection_dir: Path, root: Path, exercises: list[ExerciseSource]) -> dict[str, Any]:
    collection = make_collection_metadata(collection_dir, exercises, root)
    return {
        "collection": collection,
        "exercises": [
            {
                **exercise.metadata,
                "statementHtml": exercise.statement_html,
                "solutionHtml": exercise.solution_html,
            }
            for exercise in exercises
        ],
    }


def json_filename_for_directory(directory: Path, explicit_name: str = "") -> str:
    if explicit_name:
        return explicit_name
    return f"{directory.name}.json"


def write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def generate_collection_index(collection_dir: Path, json_filename: str, root: Path) -> None:
    back_href = Path(__import__("os").path.relpath(root / "index.html", collection_dir)).as_posix()
    html = f"""<!DOCTYPE html>
<html lang=\"it\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Raccolta esercizi</title>

  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['\\\\(', '\\\\)']],
        displayMath: [['\\\\[', '\\\\]']]
      }},
      svg: {{ fontCache: 'global' }}
    }};
  </script>
  <script defer src=\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js\"></script>

  <style>
    :root {{
      --bg: #f6f4ef;
      --panel: rgba(255,255,255,0.88);
      --text: #1f2933;
      --muted: #667085;
      --border: #d8d3c7;
      --accent: #365f85;
      --accent-soft: rgba(54,95,133,0.12);
      --shadow: 0 18px 45px rgba(0,0,0,0.075);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 15px;
      --sans: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
    }}

    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at 8% 4%, rgba(54, 95, 133, 0.14), transparent 24rem),
        radial-gradient(circle at 92% 10%, rgba(181, 141, 72, 0.09), transparent 22rem),
        linear-gradient(180deg, #f8f6f0 0%, var(--bg) 100%);
    }}

    .shell {{ width: min(1040px, calc(100% - 2rem)); margin: 0 auto; }}
    header {{ padding: 3.6rem 0 1.5rem; }}
    .back {{
      display: inline-flex;
      margin-bottom: 1.1rem;
      color: var(--accent);
      text-decoration: none;
      font-weight: 760;
    }}
    .hero {{
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: clamp(1.35rem, 3vw, 2.4rem);
    }}
    .eyebrow {{
      margin-bottom: 0.75rem;
      color: var(--accent);
      font-size: 0.8rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-family: Georgia, \"Times New Roman\", serif;
      font-size: clamp(2.7rem, 6vw, 5.3rem);
      line-height: 0.96;
      letter-spacing: -0.055em;
      font-weight: 500;
    }}
    .description {{ max-width: 72ch; margin: 1rem 0 0; color: var(--muted); line-height: 1.65; }}
    .meta-row {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 1.15rem; }}
    .pill {{
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 0.34rem 0.62rem;
      font-size: 0.78rem;
      font-weight: 780;
    }}

    .toolbar {{
      display: flex;
      justify-content: flex-end;
      gap: 0.7rem;
      margin: 1.1rem 0;
    }}
    button {{
      border: 1px solid var(--border);
      background: white;
      color: var(--accent);
      border-radius: 999px;
      padding: 0.62rem 0.88rem;
      font-weight: 760;
      cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}

    .exercise-list {{ display: grid; gap: 0.9rem; padding-bottom: 3.5rem; }}
    .exercise-card {{
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--panel);
      box-shadow: 0 12px 30px rgba(0,0,0,0.052);
      overflow: hidden;
    }}
    details summary {{ list-style: none; cursor: pointer; }}
    details summary::-webkit-details-marker {{ display: none; }}
    .summary-inner {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 1rem;
      align-items: center;
      padding: 1.15rem 1.25rem;
    }}
    .number {{
      display: grid;
      place-items: center;
      width: 2.3rem;
      height: 2.3rem;
      border-radius: 0.8rem;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 850;
    }}
    .exercise-title h2 {{ margin: 0; font-size: 1.12rem; letter-spacing: -0.025em; }}
    .exercise-title p {{ margin: 0.25rem 0 0; color: var(--muted); font-size: 0.92rem; }}
    .chevron {{ color: var(--accent); font-size: 1.35rem; transition: transform 160ms ease; }}
    details[open] .chevron {{ transform: rotate(90deg); }}
    .exercise-body {{ border-top: 1px solid var(--border); padding: 1.15rem; }}
    .grid {{ display: grid; grid-template-columns: 0.95fr 1.05fr; gap: 1rem; align-items: start; }}
    .box {{ background: white; border: 1px solid rgba(216,211,199,0.82); border-radius: var(--radius-md); padding: 1rem; }}
    .box h3 {{ margin: 0 0 0.8rem; color: var(--accent); font-size: 0.84rem; text-transform: uppercase; letter-spacing: 0.09em; }}
    .result-label {{ margin-top: 0.85rem; color: var(--muted); font-size: 0.86rem; }}
    .empty, .error {{
      margin: 1rem 0 3rem;
      background: white;
      border: 1px dashed var(--border);
      border-radius: var(--radius-lg);
      padding: 2rem;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 620px) {{ .summary-inner {{ grid-template-columns: auto 1fr; }} .chevron {{ grid-column: 1 / -1; justify-self: end; }} }}
  </style>
</head>
<body>
  <header class=\"shell\">
    <a class=\"back\" href=\"{back_href}\">← Torna all'indice</a>
    <section class=\"hero\">
      <div id=\"eyebrow\" class=\"eyebrow\">Esercizi svolti</div>
      <h1 id=\"title\">Raccolta esercizi</h1>
      <p id=\"description\" class=\"description\"></p>
      <div id=\"metaRow\" class=\"meta-row\"></div>
    </section>
  </header>

  <main class=\"shell\">
    <div class=\"toolbar\">
      <button id=\"openAll\" type=\"button\">Mostra tutte le soluzioni</button>
      <button id=\"closeAll\" type=\"button\">Nascondi tutte le soluzioni</button>
    </div>
    <section id=\"exerciseList\" class=\"exercise-list\" aria-label=\"Esercizi\">
      <div class=\"empty\">Caricamento esercizi...</div>
    </section>
  </main>

  <script>
    const LOCAL_CATALOG_FILE = \"{json_filename}\";

    const escapeHtml = (value) => String(value ?? \"\")
      .replaceAll(\"&\", \"&amp;\")
      .replaceAll(\"<\", \"&lt;\")
      .replaceAll(\">\", \"&gt;\")
      .replaceAll('\\\"', \"&quot;\")
      .replaceAll(\"'\", \"&#039;\");

    async function loadCollection() {{
      const list = document.getElementById(\"exerciseList\");
      try {{
        const response = await fetch(LOCAL_CATALOG_FILE, {{ cache: \"no-store\" }});
        if (!response.ok) throw new Error(`Impossibile caricare ${{LOCAL_CATALOG_FILE}}`);
        const data = await response.json();
        renderCollection(data);
      }} catch (error) {{
        list.innerHTML = `
          <div class=\"error\">
            <strong>Non è stato possibile caricare il JSON locale.</strong><br>
            Controlla che <code>${{LOCAL_CATALOG_FILE}}</code> sia nella stessa cartella di <code>index.html</code>.<br><br>
            Nota: in locale usa <code>python -m http.server</code>, non l'apertura diretta con <code>file://</code>.
          </div>
        `;
        console.error(error);
      }}
    }}

    function renderCollection(data) {{
      const collection = data.collection || {{}};
      const exercises = Array.isArray(data.exercises) ? data.exercises : [];

      document.title = `${{collection.title || \"Raccolta esercizi\"}} | Esercizi svolti`;
      document.getElementById(\"eyebrow\").textContent = [collection.subject, collection.category, collection.topic].filter(Boolean).join(\" · \") || \"Esercizi svolti\";
      document.getElementById(\"title\").textContent = collection.title || \"Raccolta esercizi\";
      document.getElementById(\"description\").textContent = collection.description || \"\";
      document.getElementById(\"metaRow\").innerHTML = [
        collection.count ? `${{collection.count}} esercizi` : \"\",
        collection.level || \"\",
        collection.schoolYear || \"\",
        collection.estimatedTime || \"\"
      ].filter(Boolean).map(item => `<span class=\"pill\">${{escapeHtml(item)}}</span>`).join(\"\");

      const list = document.getElementById(\"exerciseList\");
      if (exercises.length === 0) {{
        list.innerHTML = `<div class=\"empty\">Questa raccolta non contiene ancora esercizi.</div>`;
        return;
      }}

      list.innerHTML = exercises
        .sort((a, b) => Number(a.order || 999999) - Number(b.order || 999999))
        .map((exercise, index) => renderExercise(exercise, index + 1))
        .join(\"\");

      if (window.MathJax?.typesetPromise) window.MathJax.typesetPromise();
    }}

    function renderExercise(exercise, number) {{
      return `
        <article class=\"exercise-card\">
          <details class=\"exercise\">
            <summary>
              <div class=\"summary-inner\">
                <div class=\"number\">${{number}}</div>
                <div class=\"exercise-title\">
                  <h2>${{escapeHtml(exercise.title || \"Esercizio senza titolo\")}}</h2>
                  <p>${{escapeHtml(exercise.description || \"\")}}</p>
                </div>
                <div class=\"chevron\" aria-hidden=\"true\">›</div>
              </div>
            </summary>
            <div class=\"exercise-body\">
              <div class=\"grid\">
                <section class=\"box\">
                  <h3>Testo</h3>
                  ${{exercise.statementHtml || \"<p>Testo non disponibile.</p>\"}}
                </section>
                <section class=\"box\">
                  <h3>Soluzione</h3>
                  ${{exercise.solutionHtml || \"<p>Soluzione non disponibile.</p>\"}}
                  ${{exercise.file ? `<p class=\"result-label\">File sorgente: <code>${{escapeHtml(exercise.file)}}</code></p>` : \"\"}}
                </section>
              </div>
            </div>
          </details>
        </article>
      `;
    }}

    document.getElementById(\"openAll\").addEventListener(\"click\", () => {{
      document.querySelectorAll(\"details.exercise\").forEach(item => item.open = true);
      if (window.MathJax?.typesetPromise) window.MathJax.typesetPromise();
    }});

    document.getElementById(\"closeAll\").addEventListener(\"click\", () => {{
      document.querySelectorAll(\"details.exercise\").forEach(item => item.open = false);
    }});

    loadCollection();
  </script>
</body>
</html>
"""
    (collection_dir / "index.html").write_text(html, encoding="utf-8", newline="\n")


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"subjects": DEFAULT_SUBJECTS, "categories": [], "exercises": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Il file JSON '{path}' non è valido: {exc}") from exc

    if isinstance(data, list):
        return {"subjects": DEFAULT_SUBJECTS, "categories": [], "exercises": data}
    if not isinstance(data, dict):
        raise ValueError(f"Il file JSON '{path}' deve contenere un oggetto o una lista.")

    return {
        **data,
        "subjects": data.get("subjects") if isinstance(data.get("subjects"), list) else DEFAULT_SUBJECTS,
        "categories": data.get("categories") if isinstance(data.get("categories"), list) else [],
        "exercises": data.get("exercises") if isinstance(data.get("exercises"), list) else [],
    }


def subject_color(subject: str) -> str:
    key = normalize_key(subject)
    for item in DEFAULT_SUBJECTS:
        if normalize_key(item["name"]) == key:
            return item["color"]
    return "#365f85"


def ensure_category(categories: list[dict[str, Any]], subject: str, category: str, order_hint: int | float = 999999) -> None:
    if not category:
        return
    for existing in categories:
        if normalize_key(existing.get("subject", subject)) == normalize_key(subject) and normalize_key(existing.get("name")) == normalize_key(category):
            if not existing.get("subject"):
                existing["subject"] = subject
            return

    key = normalize_key(category)
    categories.append(
        {
            "name": category,
            "subject": subject,
            "order": order_hint,
            "color": DEFAULT_CATEGORY_COLORS.get(key, subject_color(subject)),
            "description": f"Esercizi di {category.lower()}.",
        }
    )


def sort_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        categories,
        key=lambda item: (
            normalize_key(item.get("subject", "")),
            float(item.get("order", 999999)) if str(item.get("order", "")).replace(".", "", 1).isdigit() else 999999,
            str(item.get("name", "")).casefold(),
        ),
    )


def collection_catalog_entry(collection_dir: Path, root: Path, local_catalog: dict[str, Any]) -> dict[str, Any]:
    collection = dict(local_catalog.get("collection", {}))
    try:
        rel_index = (collection_dir / "index.html").relative_to(root).as_posix()
    except ValueError:
        rel_index = "index.html"

    return {
        "title": collection.get("title", title_case_from_slug(collection_dir.name)),
        "description": collection.get("description", ""),
        "subject": collection.get("subject", infer_subject_from_path(collection_dir, root)),
        "category": collection.get("category", title_case_from_slug(collection_dir.name)),
        "topic": collection.get("topic", title_case_from_slug(collection_dir.name)),
        "icon": collection.get("icon", "📄"),
        "order": collection.get("order", 999999),
        "tags": collection.get("tags", []),
        "level": collection.get("level", ""),
        "schoolYear": collection.get("schoolYear", ""),
        "estimatedTime": collection.get("estimatedTime", ""),
        "file": rel_index,
        "isWip": collection.get("isWip", False),
        "type": "collection",
        "count": collection.get("count", 0),
    }


def write_local_collection(
    collection_dir: Path,
    root: Path,
    local_json_name: str,
    recursive: bool,
    include_index: bool,
    no_index: bool,
    strict: bool,
) -> tuple[dict[str, Any], list[str]]:
    exercises, warnings = load_exercise_sources(
        collection_dir=collection_dir,
        root=root,
        recursive=recursive,
        include_index=include_index,
        strict=strict,
    )
    catalog = build_local_catalog(collection_dir, root, exercises)
    json_path = collection_dir / json_filename_for_directory(collection_dir, local_json_name)
    write_json(catalog, json_path)
    if not no_index:
        generate_collection_index(collection_dir, json_path.name, root)
    return catalog, warnings


def existing_subject_roots(root: Path) -> list[Path]:
    roots = []
    for dirname in SUBJECT_ROOTS:
        candidate = root / dirname
        if candidate.exists() and candidate.is_dir():
            roots.append(candidate)
    return roots


def find_collection_dirs(root: Path, include_index: bool) -> list[Path]:
    dirs: set[Path] = set()
    scan_roots = existing_subject_roots(root) or [root]
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if should_skip_path(path, root, include_index=include_index):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if METADATA_REGEX.search(text):
                dirs.add(path.parent)
    return sorted(dirs, key=lambda item: item.relative_to(root).as_posix())


def run_local(args: argparse.Namespace, root: Path, target_dir: Path) -> int:
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Errore: la cartella non esiste: {target_dir}", file=sys.stderr)
        return 1

    ok, message = is_subject_collection_target(target_dir, root)
    if not ok:
        print(f"Errore: {message}", file=sys.stderr)
        return 1

    try:
        catalog, warnings = write_local_collection(
            collection_dir=target_dir,
            root=root,
            local_json_name=args.local_json,
            recursive=args.recursive,
            include_index=args.include_index,
            no_index=args.no_index,
            strict=args.strict,
        )
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"Avviso: {warning}", file=sys.stderr)

    json_name = json_filename_for_directory(target_dir, args.local_json)
    count = catalog.get("collection", {}).get("count", 0)
    print(f"Raccolta aggiornata: {target_dir}")
    print(f" - JSON locale: {json_name}")
    if not args.no_index:
        print(" - Pagina locale: index.html")
    print(f" - Esercizi trovati: {count}")
    return 0


def run_global(args: argparse.Namespace, root: Path) -> int:
    global_json_path = root / args.global_json

    try:
        global_catalog = load_json_object(global_json_path)
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    collection_dirs = find_collection_dirs(root, include_index=args.include_index)
    collection_entries: list[dict[str, Any]] = []
    all_warnings: list[str] = []

    for collection_dir in collection_dirs:
        try:
            local_catalog, warnings = write_local_collection(
                collection_dir=collection_dir,
                root=root,
                local_json_name="",
                recursive=False,
                include_index=args.include_index,
                no_index=args.no_index,
                strict=args.strict,
            )
            all_warnings.extend(warnings)
            if local_catalog.get("collection", {}).get("count", 0) > 0:
                collection_entries.append(collection_catalog_entry(collection_dir, root, local_catalog))
        except Exception as exc:
            if args.strict:
                print(f"Errore: {exc}", file=sys.stderr)
                return 1
            all_warnings.append(str(exc))

    # Mantiene eventuali voci non generate automaticamente, ma sostituisce le raccolte generate.
    old_entries = [item for item in global_catalog.get("exercises", []) if not (isinstance(item, dict) and item.get("type") == "collection")]
    by_file: dict[str, dict[str, Any]] = {}
    for item in old_entries + collection_entries:
        if not isinstance(item, dict):
            continue
        file_key = str(item.get("file", "")).strip()
        if not file_key:
            continue
        by_file[file_key] = item

    categories = global_catalog.get("categories", [])
    if not isinstance(categories, list):
        categories = []

    for entry in collection_entries:
        ensure_category(
            categories,
            subject=str(entry.get("subject", "")),
            category=str(entry.get("category", "")),
            order_hint=entry.get("order", 999999),
        )

    global_catalog["subjects"] = global_catalog.get("subjects") or DEFAULT_SUBJECTS
    global_catalog["categories"] = sort_categories(categories)
    global_catalog["exercises"] = sorted(
        by_file.values(),
        key=lambda item: (
            normalize_key(item.get("subject", "")),
            normalize_key(item.get("category", "")),
            float(item.get("order", 999999)) if str(item.get("order", "")).replace(".", "", 1).isdigit() else 999999,
            normalize_key(item.get("title", "")),
        ),
    )

    write_json(global_catalog, global_json_path)

    for warning in all_warnings:
        print(f"Avviso: {warning}", file=sys.stderr)

    print(f"Catalogo globale aggiornato: {global_json_path.name}")
    print(f" - Raccolte trovate: {len(collection_entries)}")
    for entry in collection_entries:
        print(f" - {entry.get('title', '<senza titolo>')} [{entry.get('file', '')}] ({entry.get('count', 0)} esercizi)")
    return 0


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    target_arg = args.target if args.target is not None else args.input
    if target_arg is None:
        target_arg = "."
    target_dir = (root / target_arg).resolve() if not Path(target_arg).is_absolute() else Path(target_arg).resolve()

    if args.mode == "global":
        return run_global(args, root)
    if args.mode == "local":
        return run_local(args, root, target_dir)

    # Modalità auto: nessun target, '.', o root => globale; ogni altra cartella => locale.
    if target_dir == root:
        return run_global(args, root)
    return run_local(args, root, target_dir)


if __name__ == "__main__":
    raise SystemExit(main())
