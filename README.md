# Eserciziario

Sito statico per raccolte di esercizi svolti, pubblicabile con GitHub Pages.

La struttura e' pensata per restare scalabile:

- ogni esercizio rimane un file HTML separato;
- ogni sottocategoria ha un manifest JSON locale;
- ogni sottocategoria ha un `index.html` aggregato;
- la home legge il catalogo globale `esercizi.json`.

## Struttura

Esempio di raccolta con esercizi nella stessa cartella:

```text
matematica/
  limiti/
    index.html
    limiti.json
    limite-01-polinomio.html
    limite-02-zero-su-zero.html
```

Esempio di raccolta con esercizi in una sottocartella:

```text
fisica/
  meccanica/
    energia/
      index.html
      exercises.json
      esercizi/
        01-lavoro-forza-parallela.html
        02-lavoro-attrito.html
```

Il generatore supporta entrambe le forme.

## File principali

- `index.html`: home del sito. Mostra le macro-sezioni Fisica e Matematica e le raccolte disponibili.
- `esercizi.json`: catalogo globale letto dalla home. Viene aggiornato dal generatore.
- `generate_exercises.py`: script di build per una singola sottocategoria.
- `fisica/.../index.html` o `matematica/.../index.html`: pagina aggregata della raccolta.
- `*.json` dentro una raccolta: manifest locale con l'elenco degli esercizi.

## Comando di build

Eseguire sempre dalla root del sito:

```bash
python generate_exercises.py fisica/meccanica/dinamica
python generate_exercises.py fisica/meccanica/energia
python generate_exercises.py matematica/limiti
```

Il percorso passato allo script deve:

- essere relativo alla root;
- iniziare con `fisica/` oppure `matematica/`;
- indicare una singola sottocategoria/raccolta.

Il comando corretto include `.py`:

```bash
python generate_exercises.py fisica/...
```

## Cosa fa il generatore

Per la sottocategoria indicata, `generate_exercises.py`:

1. verifica che la cartella esista;
2. cerca i file HTML degli esercizi;
3. ignora `index.html`, template e file che non sembrano esercizi;
4. ordina gli esercizi in modo naturale;
5. aggiorna o crea il manifest JSON locale;
6. aggiorna o crea l'`index.html` aggregato della raccolta;
7. aggiorna il catalogo globale `esercizi.json`;
8. lascia gli esercizi come file HTML separati.

Il contenuto degli esercizi non viene copiato fisicamente dentro `index.html`: la pagina aggregata carica il manifest JSON e poi i file HTML degli esercizi via `fetch()`.

## Convenzioni per i file esercizio

I file possono chiamarsi, per esempio:

```text
es_1.html
es_2.html
es_10.html
01-lavoro.html
02-potenza.html
limite-01-polinomio.html
```

Sono esclusi:

- `index.html`;
- file con `template` o `modello` nel nome;
- file HTML che non contengono segnali riconoscibili di esercizio.

## Metadati consigliati

Ogni esercizio puo' contenere metadati. Il formato consigliato e':

```html
<script>
window.EXERCISE_METADATA = {
  title: "Titolo esercizio",
  description: "Breve descrizione dell'esercizio.",
  subject: "Fisica",
  category: "Meccanica",
  topic: "Dinamica",
  order: 10,
  tags: ["dinamica", "forze"],
  level: "base",
  schoolYear: "Seconda superiore",
  estimatedTime: "8 min",
  isWip: false
};
</script>
```

Oppure, se si preferisce JSON puro:

```html
<script type="application/json" id="exercise-metadata">
{
  "title": "Titolo esercizio",
  "description": "Breve descrizione dell'esercizio.",
  "order": 10,
  "tags": ["limiti", "polinomi"],
  "level": "base"
}
</script>
```

Se i metadati mancano, il generatore prova a ricavare titolo, descrizione e ordine dal contenuto e dal nome del file.

## Formato del contenuto

Formato consigliato per nuovi esercizi:

```html
<template data-exercise-statement>
  <p>Testo dell'esercizio.</p>
</template>

<template data-exercise-solution>
  <p>Soluzione svolta.</p>
</template>
```

Il generatore supporta anche file gia' strutturati con:

- `<article class="exercise-card">`;
- `.exercise-problem`;
- `.problem-text`;
- `.exercise-solution`;
- `<details><summary>Mostra soluzione</summary>...</details>`.

Nella pagina aggregata il testo resta visibile, mentre la soluzione viene mostrata in un pannello espandibile.

## Aggiungere un esercizio a una raccolta esistente

Esempio: aggiungere un quarto limite.

1. Crea il file:

```text
matematica/limiti/limite-04-nome-esercizio.html
```

2. Inserisci testo, soluzione e metadati.

3. Rigenera la raccolta:

```bash
python generate_exercises.py matematica/limiti
```

4. Verifica in locale:

```bash
python -m http.server
```

poi apri:

```text
http://localhost:8000/matematica/limiti/
```

Il nuovo esercizio comparira' automaticamente nella pagina della raccolta e nella home.

## Aggiungere una nuova raccolta

Esempio:

```text
fisica/
  elettrostatica/
    coulomb/
      es_1.html
      es_2.html
```

Poi esegui:

```bash
python generate_exercises.py fisica/elettrostatica/coulomb
```

Lo script creera':

```text
fisica/elettrostatica/coulomb/index.html
fisica/elettrostatica/coulomb/exercises.json
```

e aggiornera':

```text
esercizi.json
```

Da quel momento la raccolta sara' visibile dalla home.

## Raccolte con sottocartella `esercizi/`

Se vuoi tenere gli esercizi in una sottocartella:

```text
fisica/meccanica/energia/
  index.html
  exercises.json
  esercizi/
    01-esercizio.html
```

il generatore la riconosce automaticamente quando trova HTML dentro `esercizi/`.

## Test locale

Da root:

```bash
python -m http.server
```

Poi apri:

```text
http://localhost:8000/
```

Non aprire direttamente i file con `file://`, perche' il browser puo' bloccare `fetch()` e quindi impedire il caricamento dei JSON o degli esercizi.

## File da modificare a mano

Di solito si modificano a mano solo:

- i file HTML dei singoli esercizi;
- eventualmente `generate_exercises.py`, se cambia la logica di build;
- eventualmente `index.html` root, se cambia la UI della home.

Di solito non conviene modificare a mano:

- `esercizi.json`;
- i manifest locali come `dinamica.json`, `limiti.json`, `exercises.json`;
- gli `index.html` aggregati delle raccolte.

Questi file vengono rigenerati dallo script.

## Checklist rapida

Per aggiungere contenuto:

1. crea o modifica i file HTML degli esercizi;
2. esegui `python generate_exercises.py percorso/della/raccolta`;
3. avvia `python -m http.server`;
4. controlla la home;
5. apri la raccolta e verifica che testo e soluzioni siano corretti.
