#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

METADATA_RE = re.compile(
    r'<script\s+type=["\']application/json["\']\s+id=["\']exercise-metadata["\']\s*>\s*(?P<body>.*?)\s*</script>',
    re.DOTALL | re.IGNORECASE,
)

CONTENT_RE = re.compile(
    r"<!--\s*EXERCISE_CONTENT_START\s*-->(?P<body>.*?)<!--\s*EXERCISE_CONTENT_END\s*-->",
    re.DOTALL | re.IGNORECASE,
)

EXCLUDED_DIRS = {".git", ".github", "__pycache__", "node_modules", "assets", "old", "theory"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera pagine locali di raccolta e aggiorna esercizi.json.")
    parser.add_argument("--input", default=".", help="Root del sito da scandire. Default: cartella corrente.")
    parser.add_argument("--json", default="esercizi.json", help="Catalogo globale da aggiornare. Default: esercizi.json.")
    parser.add_argument("--strict", action="store_true", help="Interrompe al primo errore.")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def text(value: Any) -> str:
    return str(value or "").strip()


def key(value: Any) -> str:
    return text(value).casefold()


def number(value: Any, default: float = 999999) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def find_collections(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("collection.json"):
        rel = path.relative_to(root).parts
        if any(part in EXCLUDED_DIRS for part in rel[:-1]):
            continue
        out.append(path)
    return sorted(out)


def extract_source(path: Path) -> dict[str, Any]:
    html = path.read_text(encoding="utf-8")

    metadata_match = METADATA_RE.search(html)
    if not metadata_match:
        raise ValueError(f"Manca lo script JSON exercise-metadata in {path}")

    content_match = CONTENT_RE.search(html)
    if not content_match:
        raise ValueError(f"Mancano i marker EXERCISE_CONTENT_START / EXERCISE_CONTENT_END in {path}")

    metadata = json.loads(metadata_match.group("body"))
    if not isinstance(metadata, dict):
        raise ValueError(f"I metadati di {path} devono essere un oggetto JSON.")

    if not text(metadata.get("title")):
        raise ValueError(f"Manca title nei metadati di {path}")

    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    elif isinstance(tags, list):
        tags = [text(tag) for tag in tags if text(tag)]
    else:
        tags = []

    return {
        **metadata,
        "order": number(metadata.get("order")),
        "tags": tags,
        "sourceFile": path.name,
        "content": content_match.group("body").strip(),
    }


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"categories": [], "exercises": []}

    raw = read_json(path)
    if isinstance(raw, list):
        return {"categories": [], "exercises": raw}

    if not isinstance(raw, dict):
        raise ValueError(f"{path} deve contenere un oggetto JSON oppure una lista.")

    raw["categories"] = raw.get("categories", []) if isinstance(raw.get("categories", []), list) else []
    raw["exercises"] = raw.get("exercises", raw.get("simulations", []))
    raw["exercises"] = raw["exercises"] if isinstance(raw["exercises"], list) else []
    raw.pop("simulations", None)
    return raw


def relative_href(from_file: Path, target: Path) -> str:
    return os.path.relpath(target, start=from_file.parent).replace("\\", "/")


def catalog_entry(root: Path, collection_dir: Path, collection: dict[str, Any]) -> dict[str, Any]:
    output = text(collection.get("output")) or "index.html"
    file = (collection_dir / output).relative_to(root).as_posix()
    return {
        "title": text(collection.get("title")) or text(collection.get("topic")) or "Raccolta esercizi",
        "description": text(collection.get("description")),
        "category": text(collection.get("category")) or "Senza categoria",
        "topic": text(collection.get("topic")),
        "subject": text(collection.get("subject")) or "Fisica",
        "icon": text(collection.get("icon")) or "📄",
        "order": int(number(collection.get("order"))),
        "tags": collection.get("tags", []) if isinstance(collection.get("tags", []), list) else [],
        "level": text(collection.get("level")),
        "schoolYear": text(collection.get("schoolYear")),
        "estimatedTime": text(collection.get("estimatedTime")),
        "file": file,
        "isWip": bool(collection.get("isWip", False)),
    }


def render_page(root: Path, collection_dir: Path, collection: dict[str, Any], sources: list[dict[str, Any]], output_path: Path) -> str:
    metadata = dict(collection)
    metadata.pop("output", None)
    metadata.pop("sourcesDir", None)

    title = text(collection.get("title")) or "Raccolta esercizi"
    subject = text(collection.get("subject")) or "Fisica"
    category = text(collection.get("category")) or "Meccanica"
    topic = text(collection.get("topic")) or title
    description = text(collection.get("description"))
    back_href = relative_href(output_path, root / "index.html")

    articles = "\n\n".join(item["content"] for item in sources)
    source_items = "\n".join(
        f"<li>{esc(item.get('sourceFile'))}: {esc(item.get('title'))}</li>"
        for item in sources
    )

    metadata_js = json.dumps(metadata, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(topic)} | Esercizi svolti</title>

  <script>
    window.EXERCISE_METADATA = {metadata_js};
  </script>

  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [["\\\\(", "\\\\)"]],
        displayMath: [["\\\\[", "\\\\]"]]
      }},
      svg: {{ fontCache: "global" }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>

  <style>
    :root {{
      --bg: #f6f4ef;
      --panel-soft: rgba(255, 255, 255, 0.84);
      --text: #1f2933;
      --muted: #667085;
      --muted-soft: #8a94a3;
      --border: #d8d3c7;
      --border-soft: rgba(216, 211, 199, 0.72);
      --accent: #365f85;
      --accent-dark: #24415d;
      --accent-soft: rgba(54, 95, 133, 0.12);
      --shadow: 0 18px 45px rgba(0, 0, 0, 0.075);
      --shadow-soft: 0 12px 28px rgba(0, 0, 0, 0.045);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --serif: Georgia, "Times New Roman", serif;
    }}

    * {{ box-sizing: border-box; }}
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

    .site-shell {{
      width: min(1020px, calc(100% - 2rem));
      margin: 0 auto;
    }}

    header {{ padding: 3.7rem 0 1.7rem; }}

    .back-link {{
      display: inline-flex;
      margin-bottom: 1.3rem;
      color: var(--accent-dark);
      text-decoration: none;
      font-weight: 760;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.72);
      border-radius: 999px;
      padding: 0.58rem 0.86rem;
    }}

    .hero {{
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      background:
        linear-gradient(145deg, rgba(255,255,255,0.92), rgba(255,255,255,0.66)),
        radial-gradient(circle at 0% 0%, rgba(54, 95, 133, 0.13), transparent 24rem);
      box-shadow: var(--shadow);
      padding: clamp(1.5rem, 4vw, 3rem);
    }}

    .kicker {{
      margin: 0 0 0.75rem;
      color: var(--accent-dark);
      font-size: 0.78rem;
      font-weight: 840;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}

    h1 {{
      margin: 0;
      font-family: var(--serif);
      font-weight: 500;
      font-size: clamp(2.6rem, 6vw, 5.1rem);
      line-height: 0.96;
      letter-spacing: -0.055em;
    }}

    .intro {{
      max-width: 760px;
      margin: 1.25rem 0 0;
      color: var(--muted);
      line-height: 1.65;
      font-size: 1.02rem;
    }}

    .formula-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      margin-top: 1.35rem;
    }}

    .formula-pill {{
      border: 1px solid var(--border-soft);
      background: rgba(255,255,255,0.72);
      border-radius: 999px;
      padding: 0.48rem 0.72rem;
      color: var(--accent-dark);
      font-weight: 760;
      font-size: 0.92rem;
    }}

    main {{ padding: 1.3rem 0 4rem; }}

    .exercise-list {{
      display: grid;
      gap: 1rem;
    }}

    .exercise-card {{
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--panel-soft);
      box-shadow: var(--shadow-soft);
      overflow: hidden;
    }}

    .exercise-head {{
      padding: 1.15rem 1.25rem 0.85rem;
      border-bottom: 1px solid var(--border-soft);
      background: rgba(255,255,255,0.48);
    }}

    .exercise-number {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 2.1rem;
      height: 2.1rem;
      margin-right: 0.55rem;
      border-radius: 0.8rem;
      background: var(--accent-soft);
      color: var(--accent-dark);
      font-weight: 820;
      vertical-align: middle;
    }}

    h2 {{
      display: inline;
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.45rem);
      line-height: 1.25;
      letter-spacing: -0.025em;
    }}

    .exercise-body {{
      padding: 1.2rem 1.25rem 1.25rem;
    }}

    .problem {{
      margin: 0 0 1rem;
      line-height: 1.68;
      color: var(--text);
    }}

    .always-visible {{
      display: grid;
      grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
      gap: 0.9rem;
      margin: 1rem 0;
    }}

    .box {{
      border: 1px solid var(--border-soft);
      border-radius: var(--radius-md);
      background: rgba(255,255,255,0.74);
      padding: 0.9rem 1rem;
    }}

    .box-title {{
      margin: 0 0 0.6rem;
      color: var(--accent-dark);
      font-size: 0.78rem;
      font-weight: 850;
      letter-spacing: 0.11em;
      text-transform: uppercase;
    }}

    .box p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.62;
    }}

    details {{
      margin-top: 1rem;
      border: 1px solid var(--border-soft);
      border-radius: var(--radius-md);
      background: #fff;
      overflow: hidden;
    }}

    summary {{
      cursor: pointer;
      padding: 0.88rem 1rem;
      color: var(--accent-dark);
      font-weight: 820;
      background: rgba(54, 95, 133, 0.075);
    }}

    .solution {{
      padding: 1rem;
      color: var(--text);
      line-height: 1.68;
    }}

    .solution p {{ margin: 0.4rem 0; }}

    .result {{
      margin-top: 0.85rem;
      padding: 0.75rem 0.9rem;
      border-left: 4px solid var(--accent);
      border-radius: 0 12px 12px 0;
      background: rgba(54, 95, 133, 0.08);
      font-weight: 760;
    }}

    .note {{ color: var(--muted); }}

    .build-info {{
      margin-top: 1.3rem;
      color: var(--muted-soft);
      font-size: 0.82rem;
    }}

    .build-info details {{
      border: 1px solid var(--border-soft);
      background: rgba(255,255,255,0.55);
    }}

    .build-info summary {{
      font-size: 0.82rem;
      background: transparent;
      color: var(--muted);
    }}

    .build-info ul {{
      margin: 0;
      padding: 0.5rem 1rem 1rem 2rem;
    }}

    footer {{
      width: min(1020px, calc(100% - 2rem));
      margin: 0 auto;
      padding: 0 0 2rem;
      color: rgba(31, 41, 51, 0.58);
      text-align: right;
      font-style: italic;
      font-size: 0.95rem;
    }}

    footer a {{
      color: inherit;
      text-decoration: none;
    }}

    @media (max-width: 780px) {{
      header {{ padding-top: 2rem; }}
      .always-visible {{ grid-template-columns: 1fr; }}
      .hero, .exercise-head, .exercise-body {{
        padding-left: 1rem;
        padding-right: 1rem;
      }}
      footer {{ text-align: left; }}
    }}
  </style>
</head>

<body>
  <header class="site-shell">
    <a class="back-link" href="{esc(back_href)}">← Torna al catalogo</a>

    <section class="hero">
      <p class="kicker">{esc(subject)} · {esc(category)}</p>
      <h1>{esc(topic)}: esercizi svolti</h1>
      <p class="intro">{esc(description)}</p>

      <div class="formula-strip" aria-label="Formule principali">
        <span class="formula-pill">\\(L = F s \\cos\\theta\\)</span>
        <span class="formula-pill">\\(P = \\dfrac{{L}}{{\\Delta t}}\\)</span>
        <span class="formula-pill">\\(E_c = \\dfrac{{1}}{{2}}mv^2\\)</span>
        <span class="formula-pill">\\(E_p = mgh\\)</span>
        <span class="formula-pill">\\(E_m = E_c + E_p\\)</span>
      </div>

      <div class="build-info">
        <details>
          <summary>File sorgente usati per generare questa pagina</summary>
          <ul>
            {source_items}
          </ul>
        </details>
      </div>
    </section>
  </header>

  <main class="site-shell">
    <section class="exercise-list" aria-label="Esercizi: {esc(topic)}">
{articles}
    </section>
  </main>

  <footer>
    <a href="https://github.com/laboratoriodigitale33-sketch/Eserciziario" target="_blank" rel="noopener noreferrer">
      Roberto Curcio Rubertini
    </a>
  </footer>
</body>
</html>
"""


def sort_catalog(catalog: dict[str, Any]) -> None:
    category_order = {}
    for i, category in enumerate(catalog.get("categories", [])):
        if isinstance(category, dict) and text(category.get("name")):
            category_order[key(category.get("name"))] = number(category.get("order"), 100000 + i)

    def sort_key(item: dict[str, Any]):
        return (
            category_order.get(key(item.get("category")), 999999),
            key(item.get("topic")),
            number(item.get("order")),
            key(item.get("title")),
        )

    catalog["exercises"] = sorted([x for x in catalog.get("exercises", []) if isinstance(x, dict)], key=sort_key)


def build(root: Path, json_path: Path, strict: bool) -> int:
    collections = find_collections(root)
    catalog = load_catalog(json_path)

    new_entries = []
    collection_prefixes = []
    warnings = []

    for collection_file in collections:
        collection_dir = collection_file.parent

        try:
            collection = read_json(collection_file)
            if not isinstance(collection, dict):
                raise ValueError(f"{collection_file} deve contenere un oggetto JSON.")

            sources_dir = collection_dir / (text(collection.get("sourcesDir")) or "esercizi")
            source_files = sorted(sources_dir.glob("*.html"))

            if not source_files:
                raise FileNotFoundError(f"Nessun file HTML sorgente trovato in {sources_dir}")

            sources = []
            for source_file in source_files:
                try:
                    sources.append(extract_source(source_file))
                except Exception as exc:
                    if strict:
                        raise
                    warnings.append(str(exc))

            sources.sort(key=lambda item: (number(item.get("order")), key(item.get("title"))))

            output_name = text(collection.get("output")) or "index.html"
            output_path = collection_dir / output_name

            output_path.write_text(
                render_page(root, collection_dir, collection, sources, output_path),
                encoding="utf-8",
                newline="\n"
            )

            entry = catalog_entry(root, collection_dir, collection)
            new_entries.append(entry)
            collection_prefixes.append(collection_dir.relative_to(root).as_posix() + "/")

            print(f"Generata raccolta: {entry['title']} -> {entry['file']} ({len(sources)} esercizi)")

        except Exception as exc:
            if strict:
                raise
            warnings.append(str(exc))

    new_files = {entry["file"] for entry in new_entries}
    new_titles = {key(entry.get("title")) for entry in new_entries}

    cleaned = []
    for item in catalog.get("exercises", []):
        if not isinstance(item, dict):
            continue

        item_file = text(item.get("file") or item.get("path"))
        item_title = key(item.get("title"))

        if item_file in new_files:
            continue
        if item_title in new_titles:
            continue
        if any(item_file.startswith(prefix) for prefix in collection_prefixes):
            continue

        item["file"] = item_file
        cleaned.append(item)

    catalog["exercises"] = cleaned + new_entries
    sort_catalog(catalog)
    write_json(json_path, catalog)

    print(f"Aggiornato catalogo globale: {json_path}")

    if warnings:
        print("\nAvvisi:", file=sys.stderr)
        for warning in warnings:
            print(f" - {warning}", file=sys.stderr)

    return 0


def main() -> int:
    args = parse_args()
    root = Path(args.input).resolve()
    json_path = Path(args.json).resolve()

    if not root.exists() or not root.is_dir():
        print(f"Root non valida: {root}", file=sys.stderr)
        return 1

    try:
        return build(root, json_path, args.strict)
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
