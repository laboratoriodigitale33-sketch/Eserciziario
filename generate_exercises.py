#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_exercises.py

Generatore unico per un eserciziario a raccolte.

Idea:
- dentro una cartella, per esempio fisica/meccanica/dinamica/, puoi avere tanti file
  HTML sorgente, uno per esercizio;
- il generatore costruisce UNA sola pagina locale index.html con tutti gli esercizi;
- il catalogo globale esercizi.json contiene UNA sola scheda per quella raccolta,
  per esempio "Dinamica", che punta a fisica/meccanica/dinamica/index.html.

Supporta due formati sorgente:
1) file HTML autonomi con:

   <script>
   window.EXERCISE_METADATA = { ... };
   </script>

   e preferibilmente una card:

   <div class="exercise-card"> ... </div>

2) file/template con elementi:

   data-exercise-statement
   data-exercise-solution

Uso dalla root del progetto:

  python generate_exercises.py
      Rigenera tutte le raccolte locali trovate e aggiorna esercizi.json globale.

  python generate_exercises.py fisica/meccanica/dinamica
      Rigenera quella raccolta locale e aggiorna anche esercizi.json globale.

  python generate_exercises.py fisica/meccanica/dinamica --mode local
      Rigenera solo index.html + dinamica.json dentro quella cartella.

  python generate_exercises.py --mode global
      Aggiorna solo esercizi.json globale, rigenerando comunque le pagine locali
      delle raccolte trovate per tenerle coerenti.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = "collection-v2"

EXCLUDED_DIRS = {
    ".git", ".github", "__pycache__", "node_modules", "assets", "old",
    "archive", "archivio", "backup", "dist", "build"
}

DEFAULT_SUBJECTS = [
    {
        "name": "Fisica",
        "order": 1,
        "color": "#5bd4c4",
        "description": "Esercizi di fisica organizzati per ambito."
    },
    {
        "name": "Matematica",
        "order": 2,
        "color": "#8ab4f0",
        "description": "Esercizi di matematica organizzati per argomento."
    }
]

DEFAULT_CATEGORIES = [
    {
        "name": "Fondamenti",
        "subject": "Fisica",
        "order": 1,
        "color": "#8ab4f0",
        "description": "Il linguaggio con cui la fisica descrive il mondo."
    },
    {
        "name": "Meccanica",
        "subject": "Fisica",
        "order": 10,
        "color": "#5bd4c4",
        "description": "Moto, forze, equilibrio, energia e leggi di Newton."
    },
    {
        "name": "Gravitazione",
        "subject": "Fisica",
        "order": 20,
        "color": "#a78bfa",
        "description": "La forza che domina su grandi scale: dalla caduta dei corpi alle orbite."
    },
    {
        "name": "Fluidodinamica",
        "subject": "Fisica",
        "order": 30,
        "color": "#5bc8f0",
        "description": "Il comportamento di liquidi, gas e fluidi in movimento."
    },
    {
        "name": "Termodinamica",
        "subject": "Fisica",
        "order": 40,
        "color": "#f08c5b",
        "description": "Calore, temperatura, energia interna, entropia e macchine termiche."
    },
    {
        "name": "Onde",
        "subject": "Fisica",
        "order": 50,
        "color": "#f0c060",
        "description": "Propagazione, interferenza, diffrazione e fenomeni ondulatori."
    },
    {
        "name": "Ottica",
        "subject": "Fisica",
        "order": 60,
        "color": "#f0e060",
        "description": "Riflessione, rifrazione, lenti, specchi e comportamento della luce."
    },
    {
        "name": "Elettromagnetismo",
        "subject": "Fisica",
        "order": 70,
        "color": "#f07070",
        "description": "Cariche, campi elettrici, magnetismo, circuiti e onde elettromagnetiche."
    },
    {
        "name": "Relatività",
        "subject": "Fisica",
        "order": 80,
        "color": "#c084fc",
        "description": "Spazio, tempo, simultaneità e gravità relativistica."
    },
    {
        "name": "Meccanica Quantistica",
        "subject": "Fisica",
        "order": 90,
        "color": "#7dd3fc",
        "description": "Fenomeni microscopici, stati quantistici, probabilità e misura."
    },
    {
        "name": "Astrofisica",
        "subject": "Fisica",
        "order": 100,
        "color": "#e879f9",
        "description": "Stelle, galassie, cosmologia e fenomeni fisici su scala astronomica."
    },
    {
        "name": "Fisica Nucleare",
        "subject": "Fisica",
        "order": 110,
        "color": "#fb923c",
        "description": "Nuclei, decadimenti, reazioni nucleari e applicazioni delle radiazioni."
    },
    {
        "name": "Fisica delle Particelle",
        "subject": "Fisica",
        "order": 120,
        "color": "#fb923c",
        "description": "Particelle elementari, interazioni fondamentali e modello standard."
    },
    {
        "name": "Algebra",
        "subject": "Matematica",
        "order": 10,
        "color": "#8ab4f0",
        "description": "Equazioni, disequazioni, polinomi e calcolo simbolico."
    },
    {
        "name": "Geometria Analitica",
        "subject": "Matematica",
        "order": 20,
        "color": "#93c5fd",
        "description": "Rette, circonferenze, coniche e coordinate cartesiane."
    },
    {
        "name": "Analisi",
        "subject": "Matematica",
        "order": 30,
        "color": "#60a5fa",
        "description": "Funzioni, limiti, derivate, integrali e studio di funzione."
    }
]

JS_METADATA_RE = re.compile(
    r"window\.(?:EXERCISE_METADATA|ESERCIZIO_METADATA)\s*=\s*\{(?P<body>.*?)\}\s*;",
    re.IGNORECASE | re.DOTALL,
)

SCRIPT_RE = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)

@dataclass
class ExerciseSource:
    path: Path
    relative_to_collection: str
    metadata: dict[str, Any]
    card_html: str
    extra_scripts: list[str]
    source_format: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera pagine locali di raccolta e catalogo globale dell'eserciziario."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Cartella su cui lavorare. Default: cartella corrente/root del progetto."
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "local", "global", "both"],
        default="auto",
        help="auto: senza path fa global, con path fa both."
    )
    parser.add_argument(
        "--catalog",
        default="esercizi.json",
        help="Nome del catalogo globale nella root. Default: esercizi.json."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe l'esecuzione se un sorgente ha errori."
    )
    parser.add_argument(
        "--include-existing-unmanaged",
        action="store_true",
        help="Mantiene nel catalogo globale anche voci non generate dal tool."
    )
    return parser.parse_args()


# -----------------------------------------------------------------------------
# Utility testo/path
# -----------------------------------------------------------------------------

def normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def title_case_from_slug(value: str) -> str:
    text = str(value or "").replace("-", " ").replace("_", " ").strip()
    return " ".join(word[:1].upper() + word[1:] for word in text.split())


def slug_from_title(value: str) -> str:
    value = str(value or "").strip().lower()
    repl = {
        "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
        "ç": "c", "’": "", "'": ""
    }
    for a, b in repl.items():
        value = value.replace(a, b)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "raccolta"


def path_has_excluded_part(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def is_html_source(path: Path) -> bool:
    if path.suffix.lower() not in {".html", ".htm"}:
        return False
    if path.name.lower() == "index.html":
        return False
    if path_has_excluded_part(path):
        return False
    return True


def infer_taxonomy_from_collection(collection_dir: Path, root: Path) -> dict[str, str]:
    try:
        parts = list(collection_dir.relative_to(root).parts)
    except ValueError:
        parts = list(collection_dir.parts)

    subject = title_case_from_slug(parts[0]) if len(parts) >= 1 else ""
    category = title_case_from_slug(parts[1]) if len(parts) >= 2 else ""
    topic = title_case_from_slug(parts[2]) if len(parts) >= 3 else title_case_from_slug(collection_dir.name)

    if not subject:
        subject = "Fisica"
    if not category:
        category = topic or "Senza categoria"
    if not topic:
        topic = title_case_from_slug(collection_dir.name)

    return {"subject": subject, "category": category, "topic": topic}


def infer_taxonomy_from_file(path: Path, root: Path) -> dict[str, str]:
    return infer_taxonomy_from_collection(path.parent, root)


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# -----------------------------------------------------------------------------
# Parsing JS object minimale
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
    delim = ""
    escape = False

    while i < n:
        ch = js_text[i]
        if not in_string:
            if ch == "'":
                in_string = True
                delim = "'"
                out.append('"')
            elif ch == '"':
                in_string = True
                delim = '"'
                out.append(ch)
            else:
                out.append(ch)
            i += 1
            continue

        if escape:
            if delim == "'" and ch == '"':
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

        if ch == delim:
            out.append('"' if delim == "'" else ch)
            in_string = False
            i += 1
            continue

        if delim == "'" and ch == '"':
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
    delim = ""
    escape = False

    while i < n:
        ch = js_text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == delim:
                in_string = False
            i += 1
            continue

        if ch in {'"', "'"}:
            in_string = True
            delim = ch
            out.append(ch)
            i += 1
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (js_text[j].isalnum() or js_text[j] in "_-')"):
                # il carattere ')' non dovrebbe esserci, ma non rompe il parsing di chiavi normali
                break
            j = i + 1
            while j < n and (js_text[j].isalnum() or js_text[j] in "_-"):
                j += 1
            k = j
            while k < n and js_text[k].isspace():
                k += 1
            prev_i = len(out) - 1
            while prev_i >= 0 and out[prev_i].isspace():
                prev_i -= 1
            prev = out[prev_i] if prev_i >= 0 else ""
            token = js_text[i:j]
            if k < n and js_text[k] == ":" and prev in {"", "{", ","}:
                out.append(f'"{token}"')
                i = j
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_js_metadata(text: str, path: Path) -> dict[str, Any] | None:
    match = JS_METADATA_RE.search(text)
    if not match:
        return None

    js_obj = "{" + match.group("body") + "}"
    js_obj = strip_js_comments(js_obj)
    js_obj = normalize_single_quoted_strings(js_obj)
    js_obj = quote_unquoted_keys(js_obj)
    js_obj = re.sub(r",(\s*[}\]])", r"\1", js_obj)

    try:
        data = json.loads(js_obj)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Metadati JS non validi in '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Metadati JS non validi in '{path}': devono essere un oggetto.")
    return data


# -----------------------------------------------------------------------------
# Parsing HTML sorgenti
# -----------------------------------------------------------------------------

def parse_attrs(attr_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in ATTR_RE.finditer(attr_text or ""):
        attrs[match.group("name").lower()] = html.unescape(match.group("value"))
    return attrs


def find_tag_start_with_attr(text: str, attr_name: str) -> re.Match[str] | None:
    # Trova il primo tag che contiene l'attributo richiesto, anche booleano.
    pattern = re.compile(
        rf"<(?P<tag>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*)\b{re.escape(attr_name)}\b(?P<attrs2>[^>]*)>",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.search(text)


def extract_balanced_element_from_match(text: str, match: re.Match[str]) -> str:
    tag = match.group("tag")
    start = match.start()
    open_end = match.end()

    if text[open_end - 2:open_end] == "/>":
        return text[start:open_end]

    token_re = re.compile(rf"</?{re.escape(tag)}\b[^>]*>", re.IGNORECASE | re.DOTALL)
    depth = 0
    for token in token_re.finditer(text, start):
        token_text = token.group(0)
        is_close = token_text.startswith("</")
        is_self_close = token_text.endswith("/>")
        if not is_close:
            depth += 1
            if is_self_close:
                depth -= 1
        else:
            depth -= 1
        if depth == 0:
            return text[start:token.end()]

    return text[start:]


def inner_html_from_element(element_html: str) -> str:
    open_match = re.match(r"<[^>]+>", element_html, flags=re.DOTALL)
    close_match = re.search(r"</[a-zA-Z][a-zA-Z0-9:-]*>\s*$", element_html, flags=re.DOTALL)
    if not open_match:
        return element_html
    start = open_match.end()
    end = close_match.start() if close_match else len(element_html)
    return element_html[start:end]


def extract_element_by_attr(text: str, attr_name: str) -> tuple[str, dict[str, str]] | None:
    match = find_tag_start_with_attr(text, attr_name)
    if not match:
        return None
    element = extract_balanced_element_from_match(text, match)
    attrs = parse_attrs((match.group("attrs") or "") + " " + (match.group("attrs2") or ""))
    return element, attrs


def extract_first_element_by_class(text: str, class_name: str) -> str | None:
    pattern = re.compile(
        rf"<(?P<tag>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*class\s*=\s*(['\"])[^'\"]*\b{re.escape(class_name)}\b[^'\"]*\3[^>]*)>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return extract_balanced_element_from_match(text, match)


def extract_inline_scripts(text: str) -> list[str]:
    scripts: list[str] = []
    seen: set[str] = set()
    for match in SCRIPT_RE.finditer(text):
        attrs = match.group("attrs") or ""
        body = match.group("body") or ""
        if re.search(r"\bsrc\s*=", attrs, flags=re.IGNORECASE):
            continue
        if "EXERCISE_METADATA" in body or "ESERCIZIO_METADATA" in body:
            continue
        if "renderMathInElement" in body:
            continue
        cleaned = body.strip()
        if not cleaned:
            continue
        # Evita di importare mille volte solo la funzione toggle: la pagina locale la possiede già.
        if "graph-canvas" not in cleaned and "canvas" not in cleaned and "DOMContentLoaded" not in cleaned:
            continue
        if cleaned not in seen:
            scripts.append(cleaned)
            seen.add(cleaned)
    return scripts


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def number_or_default(value: Any, default: int | float) -> int | float:
    try:
        if isinstance(value, bool):
            raise ValueError
        n = float(value)
        return int(n) if n.is_integer() else n
    except Exception:
        return default


def normalize_exercise_metadata(raw: dict[str, Any], path: Path, root: Path, index: int) -> dict[str, Any]:
    tax = infer_taxonomy_from_file(path, root)
    title = str(raw.get("title") or raw.get("titolo") or title_case_from_slug(path.stem)).strip()
    description = str(raw.get("description") or raw.get("descrizione") or f"Esercizio svolto: {title}.").strip()

    # La struttura delle cartelle prevale: fisica/meccanica/dinamica è più affidabile
    # della categoria eventualmente rimasta vecchia nei metadati.
    subject = tax["subject"]
    category = tax["category"]
    topic = tax["topic"]

    return {
        "title": title,
        "description": description,
        "subject": subject,
        "category": category,
        "topic": topic,
        "icon": str(raw.get("icon") or raw.get("icona") or "📄").strip(),
        "order": number_or_default(raw.get("order", raw.get("ordine", index * 10)), index * 10),
        "tags": normalize_tags(raw.get("tags", [])),
        "level": str(raw.get("level") or raw.get("livello") or "").strip(),
        "schoolYear": str(raw.get("schoolYear") or raw.get("anno") or "").strip(),
        "estimatedTime": str(raw.get("estimatedTime") or raw.get("tempo") or "").strip(),
        "isWip": bool(raw.get("isWip", raw.get("wip", False))),
        "source": path.name,
    }


def level_badge_class(level: str) -> str:
    n = normalize_key(level)
    if n in {"intermedio", "medio"}:
        return " medium"
    if n in {"avanzato", "difficile", "hard"}:
        return " hard"
    return ""


def level_label(level: str) -> str:
    n = normalize_key(level)
    if n == "base":
        return "Base"
    if n in {"intermedio", "medio"}:
        return "Medio"
    if n in {"avanzato", "difficile", "hard"}:
        return "Avanzato"
    return level or "Esercizio"


def build_card_from_template(metadata: dict[str, Any], statement_html: str, solution_html: str) -> str:
    badge = level_label(str(metadata.get("level", "")))
    badge_cls = level_badge_class(str(metadata.get("level", "")))
    title = html.escape(str(metadata.get("title", "Esercizio")))

    sol = solution_html.strip() or "<p>Soluzione non ancora inserita.</p>"
    return f"""
<div class="exercise-card">
  <div class="exercise-header">
    <span class="exercise-badge{badge_cls}">{html.escape(badge)}</span>
    <span class="exercise-title">{title}</span>
  </div>
  <div class="exercise-problem">
    <div class="problem-text">{statement_html}</div>
  </div>
  <div class="solution-toggle" onclick="toggleSol(this)">
    <span class="sol-icon">▼</span>&nbsp;Mostra soluzione
  </div>
  <div class="exercise-solution">
    <div class="solution-divider"><span>Soluzione</span></div>
    {sol}
  </div>
</div>
""".strip()


def extract_exercise_source(path: Path, collection_dir: Path, root: Path, index: int) -> ExerciseSource | None:
    text = read_text(path)
    raw_meta = parse_js_metadata(text, path) or {}
    source_format = "metadata" if raw_meta else "template"

    card_html = extract_first_element_by_class(text, "exercise-card")
    extra_scripts = extract_inline_scripts(text)

    if card_html is None:
        statement = extract_element_by_attr(text, "data-exercise-statement")
        if statement is None:
            return None
        statement_element, statement_attrs = statement
        solution = (
            extract_element_by_attr(text, "data-exercise-solution")
            or extract_element_by_attr(text, "data-exercise-answer")
            or extract_element_by_attr(text, "data-exercise-soluzione")
        )
        solution_html = inner_html_from_element(solution[0]) if solution else ""

        attr_meta = {
            "title": statement_attrs.get("data-exercise-title") or statement_attrs.get("data-title"),
            "description": statement_attrs.get("data-exercise-description") or statement_attrs.get("data-description"),
            "level": statement_attrs.get("data-exercise-level") or statement_attrs.get("data-level"),
            "order": statement_attrs.get("data-exercise-order") or statement_attrs.get("data-order"),
            "estimatedTime": statement_attrs.get("data-exercise-time") or statement_attrs.get("data-estimated-time"),
            "icon": statement_attrs.get("data-exercise-icon") or statement_attrs.get("data-icon"),
            "tags": statement_attrs.get("data-exercise-tags") or statement_attrs.get("data-tags"),
        }
        raw_meta = {**{k: v for k, v in attr_meta.items() if v not in {None, ""}}, **raw_meta}
        meta = normalize_exercise_metadata(raw_meta, path, root, index)
        card_html = build_card_from_template(meta, inner_html_from_element(statement_element), solution_html)
        source_format = "template"
    else:
        meta = normalize_exercise_metadata(raw_meta, path, root, index)

    return ExerciseSource(
        path=path,
        relative_to_collection=path.relative_to(collection_dir).as_posix(),
        metadata=meta,
        card_html=card_html,
        extra_scripts=extra_scripts,
        source_format=source_format,
    )


def find_direct_sources(collection_dir: Path) -> list[Path]:
    if not collection_dir.exists() or not collection_dir.is_dir():
        return []
    return sorted(path for path in collection_dir.iterdir() if path.is_file() and is_html_source(path))


def load_sources_from_collection(collection_dir: Path, root: Path, strict: bool = False) -> tuple[list[ExerciseSource], list[str]]:
    sources: list[ExerciseSource] = []
    warnings: list[str] = []
    for i, path in enumerate(find_direct_sources(collection_dir), start=1):
        try:
            item = extract_exercise_source(path, collection_dir, root, i)
            if item is None:
                warnings.append(f"Nessun esercizio riconosciuto in '{path}'. Cerca window.EXERCISE_METADATA + .exercise-card oppure data-exercise-statement.")
                continue
            sources.append(item)
        except Exception as exc:
            if strict:
                raise
            warnings.append(str(exc))

    sources.sort(key=lambda x: (float(x.metadata.get("order", 999999)), str(x.metadata.get("title", "")).lower()))
    return sources, warnings


def find_collection_dirs(root: Path) -> list[Path]:
    collection_dirs: list[Path] = []
    for dirpath in sorted([root, *[p for p in root.rglob("*") if p.is_dir()]]):
        if dirpath == root:
            continue
        try:
            rel_parts = dirpath.relative_to(root).parts
        except ValueError:
            continue
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        if find_direct_sources(dirpath):
            collection_dirs.append(dirpath)
    return collection_dirs


# -----------------------------------------------------------------------------
# Generazione pagine locali
# -----------------------------------------------------------------------------

def collection_title(collection_dir: Path, taxonomy: dict[str, str]) -> str:
    # Per fisica/meccanica/dinamica il titolo deve essere Dinamica.
    return taxonomy.get("topic") or title_case_from_slug(collection_dir.name)


def collection_json_name(collection_dir: Path) -> str:
    return f"{slug_from_title(collection_dir.name)}.json"


def description_for_collection(title: str, sources: list[ExerciseSource], taxonomy: dict[str, str]) -> str:
    count = len(sources)
    if count == 1:
        return f"Raccolta di esercizi svolti di {title.lower()}: 1 esercizio con soluzione commentata."
    return f"Raccolta di esercizi svolti di {title.lower()}: {count} esercizi con testo, schema e soluzione commentata."


def icon_for_collection(taxonomy: dict[str, str]) -> str:
    topic = normalize_key(taxonomy.get("topic"))
    category = normalize_key(taxonomy.get("category"))
    if "dinamica" in topic:
        return "⚙️"
    if "limiti" in topic:
        return "∞"
    if "cinematica" in topic:
        return "📈"
    if "circonfer" in topic:
        return "○"
    if "meccanica" in category:
        return "⚙️"
    if normalize_key(taxonomy.get("subject")) == "matematica":
        return "∑"
    return "📚"


def unique_tags(sources: list[ExerciseSource], taxonomy: dict[str, str]) -> list[str]:
    tags: list[str] = []
    for value in [taxonomy.get("subject"), taxonomy.get("category"), taxonomy.get("topic")]:
        if value:
            tags.append(str(value).lower())
    for source in sources:
        tags.extend(source.metadata.get("tags", []))
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        t = str(tag).strip()
        key = t.lower()
        if t and key not in seen:
            out.append(t)
            seen.add(key)
    return out[:12]


def build_local_json(collection_dir: Path, root: Path, sources: list[ExerciseSource]) -> dict[str, Any]:
    tax = infer_taxonomy_from_collection(collection_dir, root)
    title = collection_title(collection_dir, tax)
    return {
        "generator": VERSION,
        "title": title,
        "subject": tax["subject"],
        "category": tax["category"],
        "topic": tax["topic"],
        "description": description_for_collection(title, sources, tax),
        "count": len(sources),
        "exercises": [
            {
                **src.metadata,
                "source": src.relative_to_collection,
                "sourceFormat": src.source_format,
            }
            for src in sources
        ],
    }


def build_local_index_html(collection_dir: Path, root: Path, sources: list[ExerciseSource]) -> str:
    tax = infer_taxonomy_from_collection(collection_dir, root)
    title = collection_title(collection_dir, tax)
    subtitle = f"{tax['subject']} · {tax['category']} · {tax['topic']}"
    description = description_for_collection(title, sources, tax)
    cards = "\n\n".join(src.card_html for src in sources)

    scripts: list[str] = []
    seen: set[str] = set()
    for src in sources:
        for script in src.extra_scripts:
            if script not in seen:
                scripts.append(script)
                seen.add(script)
    extra_script_html = "\n".join(f"<script>\n{script}\n</script>" for script in scripts)

    toc = "\n".join(
        f"<span>{i}. {html.escape(str(src.metadata.get('title', 'Esercizio')))}</span>"
        for i, src in enumerate(sources, start=1)
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} | Esercizi svolti</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}})"></script>
<style>
  :root {{
    --cream: #f5f0e8;
    --cream-dark: #ede5d5;
    --ink: #1a1612;
    --ink-light: #3d3530;
    --ink-faint: #7a6f65;
    --accent: #8b3a2a;
    --accent-warm: #b5622a;
    --gold: #c9a84c;
    --border: #c8b89a;
    --border-light: #ddd0bc;
    --blue-muted: #3a5a7a;
    --green-muted: #3a6a4a;
    --shadow: rgba(26,22,18,0.12);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--cream); color: var(--ink); font-family: 'IBM Plex Sans', sans-serif; font-size: 16px; line-height: 1.7; }}
  .site-header {{ background: var(--ink); color: var(--cream); padding: 3rem 2rem 2.5rem; text-align: center; position: relative; overflow: hidden; }}
  .site-header::before {{ content: ''; position: absolute; inset: 0; background: repeating-linear-gradient(-45deg,transparent,transparent 40px,rgba(255,255,255,0.015) 40px,rgba(255,255,255,0.015) 41px); }}
  .site-header h1 {{ font-family: 'EB Garamond', serif; font-size: clamp(2.2rem, 5vw, 3.4rem); font-weight: 500; letter-spacing: 0.02em; position: relative; }}
  .site-header .subtitle {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: var(--gold); margin-top: 0.5rem; letter-spacing: 0.12em; text-transform: uppercase; position: relative; }}
  .site-header .meta-row {{ display: flex; justify-content: center; gap: 0.8rem; flex-wrap: wrap; margin-top: 1.2rem; font-size: 0.82rem; color: rgba(245,240,232,0.6); position: relative; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 0 1.5rem 4rem; }}
  .intro-box {{ background: var(--cream-dark); border-left: 4px solid var(--gold); padding: 1.4rem 1.6rem; margin: 2.5rem 0; font-family: 'EB Garamond', serif; font-size: 1.08rem; font-style: italic; color: var(--ink-light); border-radius: 0 4px 4px 0; }}
  .toc {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin: -1rem 0 2rem; }}
  .toc span {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; color: var(--ink-faint); border: 1px solid var(--border-light); background: rgba(255,255,255,0.55); border-radius: 999px; padding: 0.24rem 0.55rem; }}
  .section-header {{ margin-top: 3.5rem; padding-bottom: 0.6rem; border-bottom: 2px solid var(--ink); display: flex; align-items: baseline; gap: 1rem; }}
  .section-number {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--accent); letter-spacing: 0.1em; text-transform: uppercase; }}
  .section-title {{ font-family: 'EB Garamond', serif; font-size: 1.7rem; font-weight: 500; color: var(--ink); }}
  .section-desc {{ margin-top: 0.8rem; color: var(--ink-faint); font-size: 0.93rem; font-style: italic; }}
  .law-card {{ background: var(--ink); color: var(--cream); border-radius: 6px; padding: 1.2rem 1.6rem; margin: 1.8rem 0 0; display: flex; gap: 1.2rem; align-items: flex-start; }}
  .law-card .law-num {{ font-family: 'EB Garamond', serif; font-size: 2.8rem; font-weight: 600; color: var(--gold); line-height: 1; flex-shrink: 0; }}
  .law-card .law-content h3 {{ font-family: 'EB Garamond', serif; font-size: 1.1rem; font-weight: 500; margin-bottom: 0.3rem; }}
  .law-card .law-content p {{ font-size: 0.88rem; color: rgba(245,240,232,0.7); line-height: 1.55; }}
  .law-card .law-formula {{ margin-top: 0.5rem; font-size: 0.95rem; }}
  .exercise-card {{ background: white; border: 1px solid var(--border); border-radius: 6px; margin-top: 2rem; overflow: hidden; box-shadow: 0 2px 8px var(--shadow); }}
  .exercise-header {{ display: flex; align-items: center; gap: 1rem; padding: 1rem 1.4rem; background: var(--ink); color: var(--cream); }}
  .exercise-badge {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; background: var(--accent); color: white; padding: 0.2rem 0.6rem; border-radius: 3px; white-space: nowrap; letter-spacing: 0.05em; }}
  .exercise-badge.medium {{ background: var(--accent-warm); }}
  .exercise-badge.hard {{ background: var(--blue-muted); }}
  .exercise-title {{ font-family: 'EB Garamond', serif; font-size: 1.12rem; font-weight: 500; flex: 1; }}
  .exercise-problem {{ padding: 1.4rem 1.6rem 0; }}
  .problem-text {{ font-family: 'EB Garamond', serif; font-size: 1.05rem; color: var(--ink); line-height: 1.75; }}
  .schema-wrap {{ margin: 1.2rem 0 0; background: var(--cream-dark); border: 1px solid var(--border); border-radius: 4px; padding: 1rem; text-align: center; }}
  .schema-wrap .schema-caption {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--ink-faint); margin-top: 0.5rem; text-transform: uppercase; letter-spacing: 0.08em; }}
  svg {{ max-width: 100%; overflow: visible; }}
  canvas {{ max-width: 100%; }}
  .solution-toggle {{ display: flex; align-items: center; gap: 0.7rem; padding: 0.85rem 1.6rem; cursor: pointer; user-select: none; border-top: 1px solid var(--border-light); margin-top: 1.2rem; color: var(--accent); font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; transition: background 0.15s; }}
  .solution-toggle:hover {{ background: var(--cream); }}
  .solution-toggle .sol-icon {{ display: inline-block; transition: transform 0.3s; font-size: 0.9rem; }}
  .exercise-card.open .solution-toggle .sol-icon {{ transform: rotate(180deg); }}
  .exercise-solution {{ display: none; padding: 0 1.6rem 1.4rem; border-top: 1px dashed var(--border-light); }}
  .exercise-card.open .exercise-solution {{ display: block; }}
  .solution-divider {{ display: flex; align-items: center; gap: 0.8rem; margin: 1.2rem 0 1rem; }}
  .solution-divider span {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; white-space: nowrap; }}
  .solution-divider::before, .solution-divider::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}
  .step {{ margin: 1rem 0; padding-left: 1rem; border-left: 3px solid var(--border-light); }}
  .step-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.3rem; }}
  .step p {{ font-size: 0.95rem; color: var(--ink-light); line-height: 1.65; }}
  .step .math-block {{ margin: 0.6rem 0; }}
  .result-box {{ background: linear-gradient(135deg, var(--ink) 0%, #2d2420 100%); color: var(--cream); border-radius: 5px; padding: 1rem 1.4rem; margin-top: 1.4rem; display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }}
  .result-box .res-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--gold); text-transform: uppercase; letter-spacing: 0.12em; white-space: nowrap; }}
  .result-box .res-value {{ font-family: 'EB Garamond', serif; font-size: 1.1rem; }}
  .concept-note {{ background: #f0f5f0; border-left: 3px solid var(--green-muted); padding: 0.8rem 1.1rem; margin-top: 1.2rem; border-radius: 0 4px 4px 0; font-size: 0.9rem; color: var(--ink-light); }}
  .concept-note .cn-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--green-muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.3rem; }}
  .warning-band {{ background: var(--blue-muted); color: white; padding: 0.28rem 1rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; letter-spacing: 0.08em; text-transform: uppercase; }}
  #graph-canvas {{ cursor: crosshair; display: block; margin: 0 auto; }}
  .graph-info {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--ink-faint); text-align: center; margin-top: 0.4rem; }}
  .graph-legend {{ display: flex; flex-wrap: wrap; gap: 1rem; justify-content: center; margin-top: 0.7rem; }}
  .graph-legend span {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; display: flex; align-items: center; gap: 0.4rem; }}
  .leg-dot {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
  footer {{ text-align: center; padding: 2rem; font-family: 'EB Garamond', serif; font-size: 1rem; font-style: italic; color: var(--ink-faint); border-top: 1px solid var(--border-light); margin-top: 4rem; }}
  .katex-display {{ margin: 0.7rem 0 !important; }}
  @media (max-width: 600px) {{
    .site-header h1 {{ font-size: 2rem; }}
    .law-card {{ flex-direction: column; gap: 0.5rem; }}
    .law-card .law-num {{ font-size: 2rem; }}
  }}
</style>
</head>
<body>
<header class="site-header">
  <h1>{html.escape(title)}</h1>
  <p class="subtitle">{html.escape(subtitle)}</p>
  <div class="meta-row"><span>{len(sources)} esercizi svolti</span><span>·</span><span>testo sempre visibile</span><span>·</span><span>soluzione espandibile</span></div>
</header>

<div class="container">
  <div class="intro-box">{html.escape(description)} Clicca su <em>Mostra soluzione</em> per espandere solo la soluzione.</div>
  <div class="toc">{toc}</div>

{cards}
</div>

<footer>{html.escape(title)} · Esercizi svolti</footer>

<script>
function toggleSol(btn) {{
  const card = btn.closest('.exercise-card');
  if (!card) return;
  card.classList.toggle('open');
  const icon = btn.querySelector('.sol-icon');
  if (icon) icon.textContent = card.classList.contains('open') ? '▲' : '▼';
  btn.innerHTML = `<span class="sol-icon">${{card.classList.contains('open') ? '▲' : '▼'}}</span>&nbsp;${{card.classList.contains('open') ? 'Nascondi soluzione' : 'Mostra soluzione'}}`;
}}
</script>
{extra_script_html}
</body>
</html>
"""


def build_collection(collection_dir: Path, root: Path, strict: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
    sources, warnings = load_sources_from_collection(collection_dir, root, strict=strict)
    if not sources:
        return None, warnings

    local_json = build_local_json(collection_dir, root, sources)
    json_name = collection_json_name(collection_dir)
    write_json(collection_dir / json_name, local_json)
    write_text(collection_dir / "index.html", build_local_index_html(collection_dir, root, sources))

    tax = infer_taxonomy_from_collection(collection_dir, root)
    title = collection_title(collection_dir, tax)
    orders = [number_or_default(src.metadata.get("order"), 999999) for src in sources]
    order = min(orders) if orders else 999999

    entry = {
        "title": title,
        "description": description_for_collection(title, sources, tax),
        "subject": tax["subject"],
        "category": tax["category"],
        "topic": tax["topic"],
        "icon": icon_for_collection(tax),
        "order": order,
        "tags": unique_tags(sources, tax),
        "level": "raccolta",
        "schoolYear": first_nonempty([src.metadata.get("schoolYear") for src in sources]),
        "estimatedTime": f"{len(sources)} esercizi",
        "file": rel_posix(collection_dir / "index.html", root),
        "isWip": any(bool(src.metadata.get("isWip")) for src in sources),
        "isCollection": True,
        "exerciseCount": len(sources),
        "localJson": rel_posix(collection_dir / json_name, root),
        "generatedBy": VERSION,
    }
    return entry, warnings


def first_nonempty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


# -----------------------------------------------------------------------------
# Catalogo globale
# -----------------------------------------------------------------------------

def load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": []}
    try:
        raw = json.loads(read_text(path))
    except Exception:
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": []}
    if isinstance(raw, list):
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": raw}
    if not isinstance(raw, dict):
        return {"subjects": DEFAULT_SUBJECTS, "categories": DEFAULT_CATEGORIES, "exercises": []}
    return {
        **raw,
        "subjects": raw.get("subjects") if isinstance(raw.get("subjects"), list) else DEFAULT_SUBJECTS,
        "categories": raw.get("categories") if isinstance(raw.get("categories"), list) else DEFAULT_CATEGORIES,
        "exercises": raw.get("exercises") if isinstance(raw.get("exercises"), list) else [],
    }


def ensure_subjects_and_categories(catalog: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    subjects = list(catalog.get("subjects") or DEFAULT_SUBJECTS)
    categories = list(catalog.get("categories") or DEFAULT_CATEGORIES)

    subj_keys = {normalize_key(s.get("name")) for s in subjects if isinstance(s, dict)}
    cat_keys = {(normalize_key(c.get("subject")), normalize_key(c.get("name"))) for c in categories if isinstance(c, dict)}

    for entry in entries:
        subject = str(entry.get("subject") or "").strip() or "Fisica"
        category = str(entry.get("category") or "").strip() or "Senza categoria"
        if normalize_key(subject) not in subj_keys:
            subjects.append({"name": subject, "order": 999999, "color": "#365f85", "description": ""})
            subj_keys.add(normalize_key(subject))
        key = (normalize_key(subject), normalize_key(category))
        if key not in cat_keys:
            subjects_color = next((s.get("color") for s in subjects if isinstance(s, dict) and normalize_key(s.get("name")) == normalize_key(subject)), "#365f85")
            categories.append({"name": category, "subject": subject, "order": 999999, "color": subjects_color or "#365f85", "description": ""})
            cat_keys.add(key)

    catalog["subjects"] = sorted(subjects, key=lambda x: (number_or_default(x.get("order"), 999999), str(x.get("name", ""))))
    catalog["categories"] = sorted(categories, key=lambda x: (number_or_default(x.get("order"), 999999), str(x.get("name", ""))))


def category_order_lookup(categories: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for i, cat in enumerate(categories):
        if not isinstance(cat, dict):
            continue
        key = (normalize_key(cat.get("subject")), normalize_key(cat.get("name")))
        out[key] = float(number_or_default(cat.get("order"), 100000 + i))
    return out


def subject_order_lookup(subjects: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for i, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        out[normalize_key(subject.get("name"))] = float(number_or_default(subject.get("order"), 100000 + i))
    return out


def sort_catalog_entries(entries: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    subj_order = subject_order_lookup(catalog.get("subjects", []))
    cat_order = category_order_lookup(catalog.get("categories", []))

    def key(entry: dict[str, Any]) -> tuple[float, float, str, float, str]:
        subject = normalize_key(entry.get("subject"))
        category = normalize_key(entry.get("category"))
        topic = str(entry.get("topic", "")).lower()
        order = float(number_or_default(entry.get("order"), 999999))
        title = str(entry.get("title", "")).lower()
        return (subj_order.get(subject, 999999), cat_order.get((subject, category), 999999), topic, order, title)

    return sorted(entries, key=key)


def update_global_catalog(root: Path, catalog_name: str, target_dirs: list[Path] | None, strict: bool, keep_unmanaged: bool) -> tuple[list[dict[str, Any]], list[str]]:
    if target_dirs is None:
        collection_dirs = find_collection_dirs(root)
    else:
        collection_dirs = target_dirs

    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    source_files_to_remove: set[str] = set()
    collection_index_files: set[str] = set()

    for collection_dir in collection_dirs:
        for src in find_direct_sources(collection_dir):
            source_files_to_remove.add(rel_posix(src, root))
        collection_index_files.add(rel_posix(collection_dir / "index.html", root))
        entry, local_warnings = build_collection(collection_dir, root, strict=strict)
        warnings.extend(local_warnings)
        if entry:
            entries.append(entry)

    catalog_path = root / catalog_name
    catalog = load_catalog(catalog_path)
    ensure_subjects_and_categories(catalog, entries)

    final_entries = entries
    if keep_unmanaged:
        generated_files = {str(e.get("file", "")) for e in entries}
        keep: list[dict[str, Any]] = []
        for item in catalog.get("exercises", []):
            if not isinstance(item, dict):
                continue
            file_key = str(item.get("file", item.get("path", ""))).strip()
            if not file_key:
                continue
            if file_key in generated_files:
                continue
            if file_key in source_files_to_remove:
                continue
            if file_key in collection_index_files:
                continue
            keep.append(item)
        final_entries = keep + entries

    catalog["exercises"] = sort_catalog_entries(final_entries, catalog)
    catalog["generator"] = VERSION
    write_json(catalog_path, catalog)
    return entries, warnings


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def discover_root(start: Path, catalog_name: str) -> Path:
    # Se si lancia dalla root, resta lì. Se si lancia da una sottocartella,
    # risale fino a trovare esercizi.json oppure generate_exercises.py.
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / catalog_name).exists() or (candidate / "generate_exercises.py").exists():
            return candidate
    return Path.cwd().resolve()


def print_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print("Avvisi durante la scansione:", file=sys.stderr)
    for warning in warnings:
        print(f" - {warning}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    cwd = Path.cwd().resolve()
    path_arg = Path(args.path)
    target_path = (cwd / path_arg).resolve() if not path_arg.is_absolute() else path_arg.resolve()

    root = discover_root(cwd, args.catalog)

    if not target_path.exists() or not target_path.is_dir():
        print(f"Errore: la cartella indicata non esiste: {target_path}", file=sys.stderr)
        return 1

    mode = args.mode
    if mode == "auto":
        mode = "global" if target_path == root else "both"

    try:
        if mode == "local":
            entry, warnings = build_collection(target_path, root, strict=args.strict)
            print_warnings(warnings)
            if not entry:
                print(f"Nessun esercizio trovato in: {target_path}")
                return 0
            print(f"Raccolta locale aggiornata: {target_path}")
            print(f" - Pagina locale: index.html")
            print(f" - JSON locale: {Path(str(entry.get('localJson'))).name}")
            print(f" - Esercizi nella pagina: {entry.get('exerciseCount')}")
            print(f" - Titolo raccolta: {entry.get('title')}")
            return 0

        if mode == "both":
            entry, warnings = build_collection(target_path, root, strict=args.strict)
            print_warnings(warnings)
            if not entry:
                print(f"Nessun esercizio trovato in: {target_path}")
                return 0
            entries, global_warnings = update_global_catalog(root, args.catalog, None, args.strict, args.include_existing_unmanaged)
            print_warnings(global_warnings)
            print(f"Raccolta locale aggiornata: {target_path}")
            print(f" - Pagina locale: index.html")
            print(f" - JSON locale: {Path(str(entry.get('localJson'))).name}")
            print(f" - Esercizi nella pagina: {entry.get('exerciseCount')}")
            print(f"Catalogo globale aggiornato: {root / args.catalog}")
            print(f" - Raccolte totali nel catalogo: {len(entries)}")
            for e in entries:
                print(f" - {e.get('title')} [{e.get('file')}] ({e.get('exerciseCount')} esercizi)")
            return 0

        # mode == global
        entries, warnings = update_global_catalog(root, args.catalog, None, args.strict, args.include_existing_unmanaged)
        print_warnings(warnings)
        print(f"Catalogo globale aggiornato: {root / args.catalog}")
        print(f" - Raccolte trovate: {len(entries)}")
        for e in entries:
            print(f" - {e.get('title')} [{e.get('file')}] ({e.get('exerciseCount')} esercizi)")
        return 0

    except Exception as exc:
        if args.strict:
            raise
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
