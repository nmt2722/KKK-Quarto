# How this site works

A plain-English guide to the design and to every function in `generate.py`.

## 1. The one-sentence summary

One Python script reads two CSV files and writes a folder full of Quarto
documents; Quarto then turns those documents into a static HTML website.
There is no database and no server: everything is decided at build time.

```
csv_data/poetsfeed.csv ─┐
                        ├─► generate.py ─► *.qmd files ─► quarto render ─► _site/*.html
csv_data/worksfeed.csv ─┘
```

## 2. The data

Two tables, linked by name:

- `poetsfeed.csv` (100 rows) — one row per **poet**.
- `worksfeed.csv` (227 rows) — one row per **work**.

The link is the `Author` column in works, which holds a poet's name. So one
poet can have many works (a one-to-many relationship).

```
poet (1) ──► (many) works
```

Key columns used by the generator:

| poetsfeed.csv | worksfeed.csv |
|---|---|
| `Poet ID` | `Work ID` |
| `Name of the Poet` | `Name of the Work` |
| `Time period of the Poet` | `Author` |
| `Life of the Poet` | `Genre` |
| `Contribution of the poet to the Sanskrit Literature` | `Summary of the work` |
| | `Contents of the work` |
| | `Uniqueness of the work` |
| | `Contribution to Sanskrit Literature` |
| | `Quotable Quotations` |
| | `Any other notable information` |

The real files also contain an extra `Title` column, which the code ignores.

## 3. What gets produced

```
generate.py                 the generator (the only file you edit)
_quarto.yml                 Quarto website config
styles.css                  theme + component styles
navbar-search.html          JS that adds the navbar search box
index.qmd                   landing page (metrics + genre chart + quotes)
about.qmd                   about page
search.qmd                  global search page
genre.qmd                   browse-by-genre page
poets/index.qmd             list of all poets (table)
poets/<slug>.qmd            one page per poet (tabs)
works/index.qmd             list of all works (table)
works/<slug>.qmd            one page per work (accordion)
data/genre_counts.json      genre counts as JSON
data/genre_chart.png        "works by genre" chart image
home/                       reserved for extra markdown
```

`quarto render` converts all of that into the `_site/` folder.

The golden rule: **never edit the `.qmd` files by hand**. They are output.
Edit the CSV (or `generate.py`) and re-run.

---

## 4. `generate.py`, explained function by function

The script is organised in layers: helpers first, then data loading, then
page writers, then `main()` which calls everything in order.

### 4.1 Setup (top of file)

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POETS_CSV = os.path.join(BASE_DIR, "csv_data", "poetsfeed.csv")
WORKS_CSV = os.path.join(BASE_DIR, "csv_data", "worksfeed.csv")
POETS_DIR = os.path.join(BASE_DIR, "poets")
WORKS_DIR = os.path.join(BASE_DIR, "works")
DATA_DIR  = os.path.join(BASE_DIR, "data")
HOME_DIR  = os.path.join(BASE_DIR, "home")
```

`BASE_DIR` is the folder where the script lives, so paths work no matter
where you run the command from. All input and output paths are built from it.

### 4.2 Text helpers

These are small utilities used everywhere else.

**`slugify(text)`** — turns a name into a safe file name.
It transliterates accented letters to ASCII (`Kāḷidāsa` → `kalidasa`),
lowercases, removes anything that is not a letter/number/space/dash, turns
spaces into dashes and collapses repeats. Returns `"item"` if nothing is left.
Example: `"Rājānaka Ruyyaka"` → `rajanaka-ruyyaka`.

**`clean_cell(value)`** — normalises one CSV cell: NFKC normalisation,
replaces the non-breaking space (`\xa0`, common in this data) with a normal
space, and strips leading/trailing whitespace. Applied to the joining columns
so `"Guṇāḍhya\xa0"` and `"Guṇāḍhya"` become the same string and match.

**`first_line(s)`** — returns the first line of a multi-line value.
Some `Author` cells contain a whole biography on later lines; the author's
name is only on line one, so we match on that.

**`fold_text(s)`** — an accent-insensitive search key. It decomposes
characters (NFD), drops the accent marks, and lowercases. So searching
`kalidasa` finds `Kāḷidāsa`. Used by all the client-side search code.

**`assign_stems(rows, name_col, fallback="Unknown")`** — gives every row a
unique file name "stem". It slugifies the name and, if two rows collide,
appends `-1`, `-2`, etc. Returns a list parallel to the rows. This is why
you may see pages like `abhinanda.qmd` and `abhinanda-2.qmd`.

**`yaml_str(s)`** — safely quotes a value for YAML front matter. Titles that
contain `:`, `#`, `[`, quotes or newlines would otherwise break the YAML.

**`html_escape(s)`** — escapes `& < > "` so raw text can be placed inside HTML.

**`_guard_block_start(s)`** — if a line begins in a way Markdown would treat
as a heading (`#`), a block quote (`>`), an ordered list (`1.`), a bullet
(`-`, `+`, `*`) or a horizontal rule, it prefixes an escape character so it
renders as literal text instead.

**`html_content(s)`** — converts a raw CSV cell into HTML content ready to
embed in a page. It:
1. normalises line endings,
2. turns blank lines into `<br><br>` and single newlines into `<br>`,
3. HTML-escapes the text,
4. backslash-escapes Markdown special characters (`* _ \` [ ] ~ ^`) so they
   are not interpreted,
5. guards block starts (via `_guard_block_start`).

Why so careful? The pages place this text inside an HTML block, and Pandoc
still parses Markdown inside HTML, so unescaped characters would turn a
poem or a list into unintended formatting.

### 4.3 Reading the data

**`read_csvs()`** — reads both CSVs with `encoding="utf-8-sig"` (the `-sig`
strips a hidden byte-order mark), strips whitespace from the header names,
and runs `clean_cell` over the columns used for joining and display
(`Poet ID`, `Name of the Poet`, `Time period of the Poet`, `Work ID`,
`Author`, `Name of the Work`, `Genre`). Returns the two DataFrames.

### 4.4 Relationship maps

These build the links between the two tables.

**`build_poet_works_map(works, work_stems)`** — dictionary `author → [works]`.
Used when writing a poet page's "Works" tab (which works belong to this poet).

**`build_poet_stem_map(poets, poet_stems)`** — dictionary `poet name → stem`.
This is the lookup that turns an `Author` string into a link target.

**`build_works_by_poet_stem(works, work_stems, poet_stem_map)`** — dictionary
`poet stem → [works]`. Used by the poets index table to show each poet's works.

### 4.5 Writing a poet page

**`generate_poet_qmd(poet, out_dir, stem, pw_map)`** — writes
`poets/<stem>.qmd`. The page has:

- YAML front matter with the poet's name as `title`.
- A Bootstrap **tab strip** with up to four tabs:
  - **Overview** — the time period.
  - **Life** — the life text.
  - **Contribution** — the contribution text.
  - **Works (N)** — a list of links to `../works/<stem>.html` (only shown if
    the poet has works).

Empty cells become "No information available." via `html_content` handling
and inline fallbacks.

### 4.6 Writing a work page

**`generate_work_qmd(work, out_dir, stem, poet_stem_map)`** — writes
`works/<stem>.qmd`. The page uses a Bootstrap **accordion** with these
sections:

- **Author** — linked to `../poets/<stem>.html` when the author matches a poet.
- **Summary**
- **Contents**
- **Uniqueness**
- **Contribution & Notes** (contribution and "any other notable information"
  merged into one section)
- **Quotable Quotations**
- **Genre** — a coloured badge that links to `../genre.html#<genre-slug>`.

### 4.7 Charts and summary numbers

**`generate_genre_data(works)`** — counts works per genre, writes
`data/genre_counts.json`, and draws a horizontal Plotly bar chart to
`data/genre_chart.png` (`scale=2` for sharp images, transparent background).

### 4.8 The genre browse page

**`genre_slug(genre)`** — `slugify` on a genre so it can be used as an anchor.

**`build_genre_index(works, work_stems, poet_stem_map, poet_stems)`** — groups
`works` by `Genre`. For each genre it collects a list of works (with their
authors and stems) and the set of unique poets in that genre. It then sorts
genres by number of works (descending), then by name. Missing genres are
labelled `Uncategorized`. Returns an ordered list of `(slug, data)` pairs.

**`generate_genre_qmd(works, work_stems, poet_stem_map, poet_stems)`** — writes
`genre.qmd`. It contains:

- A search box (`#genre-search`).
- A row of "pills", one per genre plus an "All" pill, each showing a count.
- One `<section>` per genre containing the poet chips and the list of works.
  Every searchable element carries a `data-search` attribute holding its
  *folded* text, and each section carries `data-genre="<slug>"`.
- A call to `generate_genre_js()` for the interactivity.

**`generate_genre_js()`** — returns the JavaScript that makes the page
interactive. It:
- filters by the active pill (show only that genre's section), and
- filters by the typed text (hide individual poets/works that do not match),
- updates a small status line,
- stores the chosen genre in the URL hash (`#epic`) so that genre badges on
  work pages, which link to `genre.html#epic`, jump straight to that genre.

### 4.9 The landing page and about page

**`split_quotation(cell)`** — one `Quotable Quotations` cell may hold several
numbered quotations, each a Sanskrit verse (Devanagari + IAST transliteration)
followed by an English translation. The English translation is taken to start
right after the verse's `[reference]` bracket, so each quotation becomes a
`(verse, meaning)` pair. If there is no reference bracket the whole cell is
treated as one verse, so the English is never lost or cut in the wrong place.

**`build_quotes_marquee(works)`** — collects every quotation (as verse +
English meaning), truncates long ones, and builds an auto-scrolling,
**bottom-to-top** marquee. The track is a vertical flex column, duplicated
so the `translateY(0) -> translateY(-50%)` CSS animation (`marquee-scroll`)
loops seamlessly; the duration is set inline from the item count (very slow,
`len(items) * 16` seconds, minimum 160). Returns the lines (including a
```` ```{=html} ```` fence) to append to the home page.

**`generate_index_qmd(poets, works, genre_counts)`** — writes `index.qmd`:
- three **value boxes**: Poets, Works, Genres (each number sits in its own box),
- the genre chart image,
- a short "Explore" link list,
- the quotes marquee.

**`generate_about_qmd()`** — writes a static `about.qmd`.

### 4.10 Interactivity: tables, global search, navbar box

**`generate_table_js(table_id, search_id, info_id, pag_id, size_id, default_size)`**
— returns a reusable JavaScript "table controller" used by both list pages.
It reads the table rows that are already in the HTML (each row carries a
`data-search` attribute), then provides:
- live text filtering,
- click-a-column-header **sorting**,
- **pagination** with numbered page links,
- a "rows per page" dropdown,
- a "showing X–Y of N" label.

**`clean_text(s, limit=1500)`** — trims a value for the search index, treating
`nan`/empty as blank and truncating very long text (with `limit=0` meaning
"no limit", used for quotations).

**`build_search_records(poets, works, poet_stems, work_stems, poet_stem_map)`**
— builds the search index as a list of dictionaries. Each record has a `type`
(`poet`/`work`), a `name`, a `link`, the concatenated searchable `text`, and
`fhay` (the folded "haystack" string used for matching).

**`generate_search_js()`** — the global search engine. It reads the JSON
index, filters records by the folded query, splits results into Poets and
Works, highlights matches with `<mark>`, shows a short snippet around the
first hit, and reads a `?q=` URL parameter so searches can be linked to.

**`generate_search_qmd(...)`** — writes `search.qmd`: the search input, a
results container, the JSON index inside a
`<script type="application/json">` block, and the search JavaScript.

**`generate_navbar_search_html()`** — writes `navbar-search.html`, which
Quarto injects into every page's `<head>`. Its JavaScript adds a search box
to the navbar and redirects to `search.html?q=...` on submit. It figures out
the correct relative path by inspecting the navbar brand link, so it works
from pages in sub-folders too.

### 4.11 The two list pages

**`generate_poets_index_qmd(poets, poet_stems, works_by_stem)`** — writes
`poets/index.qmd`: a table with columns Poet ID, Name, Works. Each row has a
folded `data-search` value, the name links to `<stem>.html`, and the works
link to `../works/<stem>.html`. Ends with the table controller JS.

**`generate_works_index_qmd(works, work_stems, poet_stem_map)`** — writes
`works/index.qmd`: a table with columns Work ID, Work, Author, Genre. The
author links to `../poets/<stem>.html` and the genre badge links to
`../genre.html#<slug>`. Ends with the table controller JS.

### 4.12 Site scaffolding

**`generate_quarto_yml()`** — writes `_quarto.yml`, the Quarto site config:
- `project.type: website`,
- a `render` whitelist (`*.qmd`, `poets/*.qmd`, `works/*.qmd`) so files like
  `PROMPT.md` are **not** turned into pages,
- a `post-render` step that deletes Quarto's built-in `_site/search.json`
  (we ship our own search),
- the navbar (Home, About, Poets, Works, Genres) and footer. There is no
  "Search" nav item: the single navbar search box (injected by
  `navbar-search.html`) is the only search entry point in the navbar,
- the HTML format: `cosmo` theme, our `styles.css`, and the
  `navbar-search.html` header include.

**`generate_styles_css()`** — writes `styles.css`: a warm "manuscript" palette
(cream background, maroon headings, gold accents, serif headings) plus styles
for value boxes, tables, tabs, accordions, the marquee, and the genre page.

### 4.13 `main()` — the build order

At the bottom, `if __name__ == "__main__":` runs the whole pipeline:

1. `read_csvs()` — load both tables.
2. Create the output folders if missing.
3. **Delete old** `poets/*.qmd` and `works/*.qmd` so removed rows disappear.
4. `assign_stems(...)` for poets and works.
5. Build the relationship maps.
6. Write every poet page, then every work page.
7. Build the charts.
8. Write `_quarto.yml`, `styles.css`, `index`, `about`, the two list pages,
   `genre`, `search`, and `navbar-search.html`.
9. Print "Done" — then you run `quarto render`.

---

## 5. How the interactivity works (no server needed)

All the "dynamic" behaviour is plain JavaScript running in the browser on top
of fully static HTML:

- **Search / sort / pagination** — the data is already in the table rows.
  JavaScript just hides/shows, sorts and slices them.
- **Global search** — the entire index is embedded in the page as JSON;
  JavaScript filters it and renders results.
- **Genre filter** — each element carries a folded `data-search` string and
  each section a `data-genre`; JavaScript toggles visibility.
- **Navbar search** — a small script injects the box and redirects to the
  search page with a `?q=` parameter.

Because it is all static, the site can be hosted anywhere (GitHub Pages, S3,
a shared folder) with no backend.

## 6. How missing data and future edits are handled

- **Missing cells** render as friendly placeholders ("No information
  available.", "No summary available.") instead of breaking the layout.
- **Genre** is read straight from the CSV. Change any `Genre` value (or add a
  new one) and re-run; the genre page, the pills, the chart, the metric and
  the links on work pages all update automatically.
- **New or removed rows** are picked up because stems are reassigned and old
  `.qmd` files are deleted first. Removing a poet removes their pages.
- **Name matching** is tolerant: `\xa0` spaces are cleaned and multi-line
  `Author` cells are matched on their first line, so all 227 works link to a
  poet page.

## 7. Building and updating

```
pip install pandas plotly kaleido     # one-time dependencies
python generate.py                    # read CSVs and write all .qmd/.css/.yml
quarto render                         # build _site/
quarto preview                        # optional: live local preview
```

The only dependencies are `pandas` (data), `plotly` + `kaleido` (charts), and
Quarto (rendering).

## 8. Glossary of generated page types

| Page | Quarto feature | Why |
|---|---|---|
| Landing | value boxes + image | at-a-glance metrics and chart |
| Poet detail | Bootstrap tabs | several short sections in one place |
| Work detail | Bootstrap accordion | long, collapsible sections |
| Poets / Works lists | HTML table + JS | search, sort, paginate |
| Genre | sections + JS | filter works/poets per category |
| Search | embedded JSON + JS | search the whole corpus client-side |
| About | static markdown | project information |

## 9. Developer notes (how it was done)

These notes are the "why" behind the design. They are kept here in the
documentation on purpose, and **not** shown on the website itself.

- **Genre page purpose.** The genre page lets a reader browse the corpus by
  genre. The reader can use the search box to narrow the list, or pick a
  genre pill to focus on a single category. Genres are taken directly from
  the source data: update the `Genre` column in the CSV and re-run
  `generate.py` to refresh the page. (This paragraph previously lived on the
  genre page itself and was moved here so the public page stays clean.)

- **Genre is data-driven.** No genre is hard-coded anywhere. The pills, the
  counts, the chart, the metric card and the genre badges on work pages all
  come from the `Genre` column, so renaming or adding a genre in the CSV is
  enough to change the whole site.

- **Missing data.** Empty cells become placeholders ("No information
  available.") rather than breaking layout. Filling them in the CSV and
  re-running is all that is needed.

- **Name matching.** `\xa0` (non-breaking space) is normalised and multi-line
  `Author` cells are matched on their first line, so every work links to a
  poet page.

- **Stale pages.** `main()` deletes old `poets/*.qmd` and `works/*.qmd` before
  regenerating, so deleted rows disappear from the site.

- **Search.** There is a single search entry point in the navbar (the injected
  search box). The dedicated `search.html` page is the results target. The
  navbar has no separate "Search" link to avoid duplication.

- **Removed features.** The "Most prolific poets" chart and the "Quotable
  Passages" metric card were removed by request; their code
  (`generate_poets_chart`, `count_quotes`) is gone from `generate.py`.

- **Quotes marquee.** The landing-page marquee scrolls **bottom to top**
  (vertical). Each item shows the verse and, when present, the English
  meaning below it in a lighter colour. The scroll is deliberately very slow;
  change the duration by editing the `len(items) * 16` factor in
  `build_quotes_marquee`.

- **Value boxes.** The three headline numbers (Poets, Works, Genres) render
  as bordered boxes inside a `.kpi-row` container. `.kpi-row` is a CSS grid
  using `repeat(auto-fit, minmax(200px, 1fr))`, so it shows three cards across
  when there is room, and automatically drops to two or one card per row when
  space is tight &mdash; the cards are never squeezed. The number uses
  `white-space: nowrap` so digits never stack vertically. Do **not** use
  Quarto/Bootstrap `.grid` + `.col-md-*` here: `.col-md-*` is not a grid-span
  class, so each card would fall into a single 1/12 slot and look broken.

- **Regeneration rule.** Never edit generated `.qmd` files by hand. Edit the
  CSV or `generate.py`, then run `python generate.py` and `quarto render`.
