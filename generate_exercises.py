#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generatore per categorie di esercizi.

Uso consigliato:
    python generate_exercises.py matematica/analisi/limiti

Uso alternativo:
    python generate_exercises.py --input matematica/analisi/limiti

Opzioni:
    --json nomefile.json     forza il nome del JSON
    --strict                 blocca la build se un esercizio non ha metadati validi
    --write-index            genera/sovrascrive un index.html minimale
"""

import argparse
import json
import re
import sys
from pathlib import Path
from html import unescape


def slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def extract_metadata(html: str, filename: str, strict: bool = False) -> dict:
    pattern = re.compile(
        r'<script\s+type=["\']application/json["\']\s+class=["\']exercise-metadata["\']\s*>\s*(.*?)\s*</script>',
        re.DOTALL | re.IGNORECASE
    )

    match = pattern.search(html)

    if match:
        raw_json = match.group(1).strip()

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            message = f"Metadati JSON non validi in {filename}: {exc}"
            if strict:
                raise ValueError(message)
            print(f"[AVVISO] {message}")
            data = {}
    else:
        message = f"Nessun blocco exercise-metadata trovato in {filename}"
        if strict:
            raise ValueError(message)
        print(f"[AVVISO] {message}")
        data = {}

    title = data.get("title") or extract_title(html) or Path(filename).stem.replace("_", " ").title()

    data.setdefault("id", Path(filename).stem)
    data.setdefault("title", title)
    data.setdefault("topic", "")
    data.setdefault("subtopic", "")
    data.setdefault("difficulty", "")
    data.setdefault("order", None)
    data.setdefault("tags", [])
    data["file"] = filename

    return data


def extract_title(html: str) -> str | None:
    for tag in ["h1", "h2", "title"]:
        pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.DOTALL | re.IGNORECASE)
        match = pattern.search(html)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1))
            text = unescape(text).strip()
            if text:
                return text
    return None


def sort_key(exercise: dict):
    order = exercise.get("order")
    if isinstance(order, int):
        return (0, order)

    if isinstance(order, str) and order.isdigit():
        return (0, int(order))

    return (1, exercise.get("file", ""))


def build_json(target_dir: Path, json_name: str | None, strict: bool = False) -> Path:
    if not target_dir.exists():
        raise FileNotFoundError(f"La cartella non esiste: {target_dir}")

    if not target_dir.is_dir():
        raise NotADirectoryError(f"Il percorso indicato non è una cartella: {target_dir}")

    slug = target_dir.name
    category = slug_to_title(slug)

    if json_name is None:
        json_name = f"{slug}.json"

    exercise_files = sorted(
        file for file in target_dir.glob("*.html")
        if file.name.lower() != "index.html"
    )

    if not exercise_files:
        print(f"[AVVISO] Nessun file HTML di esercizio trovato in: {target_dir}")

    exercises = []

    for file in exercise_files:
        html = file.read_text(encoding="utf-8")
        metadata = extract_metadata(html, file.name, strict=strict)
        exercises.append(metadata)

    exercises.sort(key=sort_key)

    data = {
        "category": category,
        "slug": slug,
        "path": target_dir.as_posix(),
        "count": len(exercises),
        "exercises": exercises
    }

    json_path = target_dir / json_name

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[OK] JSON aggiornato: {json_path}")
    print(f"[OK] Esercizi trovati: {len(exercises)}")

    for exercise in exercises:
        order = exercise.get("order")
        title = exercise.get("title")
        file = exercise.get("file")
        print(f"  - {order if order is not None else '?'} | {title} | {file}")

    return json_path


def write_minimal_index(target_dir: Path, json_name: str):
    slug = target_dir.name
    title = slug_to_title(slug)
    index_path = target_dir / "index.html"

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | Esercizi svolti</title>

  <script>
    window.EXERCISES_JSON = "{json_name}";
  </script>
</head>
<body>
  <h1>{title}</h1>

  <p>
    Pagina della categoria <strong>{title}</strong>.
    Il file JSON associato è <code>{json_name}</code>.
  </p>

  <div id="exercises-root"></div>

  <script>
    fetch(window.EXERCISES_JSON)
      .then(response => {{
        if (!response.ok) {{
          throw new Error("JSON non trovato: " + window.EXERCISES_JSON);
        }}
        return response.json();
      }})
      .then(data => {{
        const root = document.getElementById("exercises-root");
        root.innerHTML = "";

        const info = document.createElement("p");
        info.textContent = "Esercizi trovati: " + data.exercises.length;
        root.appendChild(info);

        const list = document.createElement("ol");

        data.exercises.forEach(ex => {{
          const item = document.createElement("li");
          const link = document.createElement("a");
          link.href = ex.file;
          link.textContent = ex.title || ex.file;
          item.appendChild(link);
          list.appendChild(item);
        }});

        root.appendChild(list);
      }})
      .catch(error => {{
        document.getElementById("exercises-root").innerHTML =
          "<p><strong>Errore:</strong> " + error.message + "</p>";
      }});
  </script>
</body>
</html>
"""

    index_path.write_text(html, encoding="utf-8")
    print(f"[OK] index.html scritto: {index_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Genera il JSON di una categoria di esercizi."
    )

    parser.add_argument(
        "path",
        nargs="?",
        help="Percorso della cartella, per esempio matematica/analisi/limiti"
    )

    parser.add_argument(
        "--input",
        dest="input_dir",
        help="Percorso della cartella, equivalente all'argomento diretto"
    )

    parser.add_argument(
        "--json",
        dest="json_name",
        default=None,
        help="Nome opzionale del file JSON da generare"
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe la build se trova metadati mancanti o non validi"
    )

    parser.add_argument(
        "--write-index",
        action="store_true",
        help="Genera o sovrascrive un index.html minimale"
    )

    args = parser.parse_args()

    target = args.input_dir or args.path

    if not target:
        parser.error(
            "Devi indicare una cartella. Esempio: "
            "python generate_exercises.py matematica/analisi/limiti"
        )

    target_dir = Path(target).resolve()

    try:
        json_path = build_json(
            target_dir=target_dir,
            json_name=args.json_name,
            strict=args.strict
        )

        if args.write_index:
            write_minimal_index(target_dir, json_path.name)
        else:
            index_path = target_dir / "index.html"
            if index_path.exists():
                print(f"[INFO] index.html esiste già e non è stato sovrascritto: {index_path}")
            else:
                print("[INFO] index.html non esiste. Per crearne uno minimale usa --write-index")

    except Exception as exc:
        print(f"[ERRORE] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()