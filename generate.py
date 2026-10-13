import os
import json
import re
import unicodedata
import pandas as pd
import plotly.express as px

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POETS_CSV = os.path.join(BASE_DIR, "csv_data", "poetsfeed.csv")
WORKS_CSV = os.path.join(BASE_DIR, "csv_data", "worksfeed.csv")

POETS_DIR = os.path.join(BASE_DIR, "poets")
WORKS_DIR = os.path.join(BASE_DIR, "works")
DATA_DIR = os.path.join(BASE_DIR, "data")
HOME_DIR = os.path.join(BASE_DIR, "home")


def slugify(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "item"


def clean_cell(value):
    return unicodedata.normalize("NFKC", str(value).replace("\xa0", " ")).strip()


def first_line(s):
    return str(s).split("\n", 1)[0].strip()


def fold_text(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def assign_stems(rows, name_col, fallback="Unknown"):
    used = set()
    stems = []
    for _, r in rows.iterrows():
        base = slugify(str(r.get(name_col, fallback)))
        stem = base
        counter = 1
        while stem + ".qmd" in used:
            stem = f"{base}-{counter}"
            counter += 1
        used.add(stem + ".qmd")
        stems.append(stem)
    return stems


def yaml_str(s):
    s = str(s)
    if '"' in s or '\n' in s:
        return "'''" + s.replace("'''", "\\'\\'\\'") + "'''"
    if any(c in s for c in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _guard_block_start(s):
    if not s:
        return s
    if s[0] in "#>":
        return "\\" + s
    m = re.match(r"^(\d{1,9}[.)])\s", s)
    if m:
        pos = m.start(1) + len(m.group(1)) - 1
        return s[:pos] + "\\" + s[pos] + s[pos + 1 :]
    if s[0] in "-+*" and (len(s) == 1 or s[1] in " \t"):
        return "\\" + s
    if re.match(r"^(---|\*\*\*|___|===)", s):
        return "\\" + s
    return s


def html_content(s):
    s = str(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n[ \t]*\n+", "\x00BRS\x00BRBRS\x00", s)
    s = s.replace("\n", "\x00BRS\x00BR\x00")
    s = html_escape(s)
    for ch in "\\*_`[]~^":
        s = s.replace(ch, "\\" + ch)
    s = s.replace("\x00BRS\x00BRBRS\x00", "<br><br>").replace("\x00BRS\x00BR\x00", "<br>")
    return _guard_block_start(s)


def read_csvs():
    poets = pd.read_csv(POETS_CSV, encoding="utf-8-sig")
    works = pd.read_csv(WORKS_CSV, encoding="utf-8-sig")
    poets.columns = [c.strip() for c in poets.columns]
    works.columns = [c.strip() for c in works.columns]
    key_cols = {
        "poets": ["Poet ID", "Name of the Poet", "Time period of the Poet"],
        "works": ["Work ID", "Author", "Name of the Work", "Genre"],
    }
    for col in key_cols["poets"]:
        if col in poets.columns:
            poets[col] = poets[col].map(clean_cell)
    for col in key_cols["works"]:
        if col in works.columns:
            works[col] = works[col].map(clean_cell)
    return poets, works


def build_poet_works_map(works, work_stems):
    pw_map = {}
    for (_, w), stem in zip(works.iterrows(), work_stems):
        author = first_line(w.get("Author", ""))
        name = str(w.get("Name of the Work", w.get("Title", "Unknown")))
        if author not in pw_map:
            pw_map[author] = []
        pw_map[author].append({"name": name, "stem": stem})
    return pw_map


def build_poet_stem_map(poets, poet_stems):
    pm = {}
    for (_, p), stem in zip(poets.iterrows(), poet_stems):
        name = str(p.get("Name of the Poet", p.get("Title", "Unknown"))).strip()
        pm.setdefault(name, stem)
    return pm


def build_works_by_poet_stem(works, work_stems, poet_stem_map):
    m = {}
    for (_, w), stem in zip(works.iterrows(), work_stems):
        author = first_line(w.get("Author", ""))
        pstem = poet_stem_map.get(author)
        if not pstem:
            continue
        name = str(w.get("Name of the Work", w.get("Title", "Unknown"))).strip()
        m.setdefault(pstem, []).append({"name": name, "stem": stem})
    return m


def generate_poet_qmd(poet, out_dir, stem, pw_map):
    name = str(poet.get("Name of the Poet", poet.get("Title", "Unknown"))).strip()
    filename = stem + ".qmd"
    filepath = os.path.join(out_dir, filename)

    poet_id = str(poet.get("Poet ID", "")).strip()
    time_period = str(poet.get("Time period of the Poet", "")).strip()
    life = str(poet.get("Life of the Poet", "")).strip()
    contribution = str(poet.get("Contribution of the poet to the Sanskrit Literature", "")).strip()

    works_list = pw_map.get(name, [])

    tab_items = []
    tab_panes = []

    tab_items.append(f'<li class="nav-item" role="presentation"><button class="nav-link active" id="nav-{slugify(name)}-overview-tab" data-bs-toggle="tab" data-bs-target="#nav-{slugify(name)}-overview" type="button" role="tab">Overview</button></li>')
    tab_panes.append('<div class="tab-pane fade show active" id="nav-' + slugify(name) + '-overview" role="tabpanel">')
    if time_period and time_period != "nan":
        tab_panes.append('<p class="lead">' + html_content(time_period) + '</p>')
    tab_panes.append('</div>')

    tab_items.append(f'<li class="nav-item" role="presentation"><button class="nav-link" id="nav-{slugify(name)}-life-tab" data-bs-toggle="tab" data-bs-target="#nav-{slugify(name)}-life" type="button" role="tab">Life</button></li>')
    tab_panes.append('<div class="tab-pane fade" id="nav-' + slugify(name) + '-life" role="tabpanel">')
    tab_panes.append(html_content(life) if life and life != "nan" else '<p class="text-muted">No information available.</p>')
    tab_panes.append('</div>')

    tab_items.append(f'<li class="nav-item" role="presentation"><button class="nav-link" id="nav-{slugify(name)}-contribution-tab" data-bs-toggle="tab" data-bs-target="#nav-{slugify(name)}-contribution" type="button" role="tab">Contribution</button></li>')
    tab_panes.append('<div class="tab-pane fade" id="nav-' + slugify(name) + '-contribution" role="tabpanel">')
    tab_panes.append(html_content(contribution) if contribution and contribution != "nan" else '<p class="text-muted">No information available.</p>')
    tab_panes.append('</div>')

    if works_list:
        tab_items.append(f'<li class="nav-item" role="presentation"><button class="nav-link" id="nav-{slugify(name)}-works-tab" data-bs-toggle="tab" data-bs-target="#nav-{slugify(name)}-works" type="button" role="tab">Works ({len(works_list)})</button></li>')
        tab_panes.append('<div class="tab-pane fade" id="nav-' + slugify(name) + '-works" role="tabpanel">')
        tab_panes.append('<ul class="list-group list-group-flush">')
        for w in works_list:
            tab_panes.append('<li class="list-group-item px-0"><a href="../works/' + w["stem"] + '.html">' + html_escape(w["name"]) + '</a></li>')
        tab_panes.append('</ul>')
        tab_panes.append('</div>')

    lines = [
        "---",
        f"title: {yaml_str(name)}",
        "format: html",
        "---",
        "",
        '<ul class="nav nav-tabs nav-justified" id="poetTabs" role="tablist">',
    ]
    for item in tab_items:
        lines.append("  " + item)
    lines.append("</ul>")
    lines.append('<div class="tab-content py-3">')
    for pane in tab_panes:
        lines.append("  " + pane)
    lines.append("</div>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filename


def generate_work_qmd(work, out_dir, stem, poet_stem_map):
    name = str(work.get("Name of the Work", work.get("Title", "Unknown"))).strip()
    filename = stem + ".qmd"
    filepath = os.path.join(out_dir, filename)

    author = str(work.get("Author", "Unknown"))
    author_short = first_line(author)
    poet_stem = poet_stem_map.get(author_short, "")
    author_html = html_escape(author_short)
    if poet_stem:
        author_html = '<a href="../poets/' + poet_stem + '.html">' + author_html + "</a>"
    summary = str(work.get("Summary of the work", "")).strip()
    contents = str(work.get("Contents of the work", "")).strip()
    uniqueness = str(work.get("Uniqueness of the work", "")).strip()
    contribution = str(work.get("Contribution to Sanskrit Literature", "")).strip()
    other_info = str(work.get("Any other notable information", "")).strip()
    genre = str(work.get("Genre", "Unknown"))
    quotations = str(work.get("Quotable Quotations", "")).strip()

    summary = html_content(summary)
    contents = html_content(contents)
    uniqueness = html_content(uniqueness)
    contribution = html_content(contribution)
    other_info = html_content(other_info)
    quotations = html_content(quotations)
    genre = str(genre)

    combined_contribution = contribution
    if other_info and other_info != "nan" and other_info.strip():
        combined_contribution = (contribution + "<br><br>") + other_info if contribution and contribution != "nan" else other_info

    accordion_items = []

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-author">Author</button></h2><div id="work-acc-author" class="accordion-collapse collapse show"><div class="accordion-body"><p class="mb-0 work-author">' + author_html + '</p></div></div></div>')

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-summary">Summary</button></h2><div id="work-acc-summary" class="accordion-collapse collapse"><div class="accordion-body">' + (summary if summary and summary != "nan" else '<p class="text-muted mb-0">No summary available.</p>') + '</div></div></div>')

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-contents">Contents</button></h2><div id="work-acc-contents" class="accordion-collapse collapse"><div class="accordion-body">' + (contents if contents and contents != "nan" else '<p class="text-muted mb-0">No contents available.</p>') + '</div></div></div>')

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-uniqueness">Uniqueness</button></h2><div id="work-acc-uniqueness" class="accordion-collapse collapse"><div class="accordion-body">' + (uniqueness if uniqueness and uniqueness != "nan" else '<p class="text-muted mb-0">No information available.</p>') + '</div></div></div>')

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-contribution">Contribution &amp; Notes</button></h2><div id="work-acc-contribution" class="accordion-collapse collapse"><div class="accordion-body">' + (combined_contribution if combined_contribution and combined_contribution != "nan" else '<p class="text-muted mb-0">No information available.</p>') + '</div></div></div>')

    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-quotations">Quotable Quotations</button></h2><div id="work-acc-quotations" class="accordion-collapse collapse"><div class="accordion-body">' + (quotations if quotations and quotations != "nan" else '<p class="text-muted mb-0">No quotations available.</p>') + '</div></div></div>')

    genre_gs = genre_slug(genre) if genre and genre.lower() != "nan" else ""
    if genre_gs:
        genre_badge = '<a class="badge bg-primary work-genre-badge text-decoration-none" href="../genre.html#' + genre_gs + '">' + html_escape(genre) + '</a>'
    else:
        genre_badge = '<span class="badge bg-secondary work-genre-badge">Uncategorized</span>'
    accordion_items.append('<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#work-acc-genre">Genre</button></h2><div id="work-acc-genre" class="accordion-collapse collapse"><div class="accordion-body"><p class="mb-0">' + genre_badge + '</p></div></div></div>')

    lines = [
        "---",
        f"title: {yaml_str(name)}",
        "format: html",
        "---",
        "",
        '<div class="accordion" id="workAccordion">',
    ]
    for item in accordion_items:
        lines.append(item)
    lines.append("</div>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filename


def generate_genre_data(works):
    genre_counts = works["Genre"].value_counts().reset_index()
    genre_counts.columns = ["genre", "count"]
    genre_counts = genre_counts.sort_values("count", ascending=True)
    out_path = os.path.join(DATA_DIR, "genre_counts.json")
    genre_counts.to_json(out_path, orient="records", indent=2)

    fig = px.bar(
        genre_counts,
        x="count",
        y="genre",
        title="Works by Genre",
        labels={"count": "Number of Works", "genre": "Genre"},
        orientation="h",
        color="count",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"),
    )
    img_path = os.path.join(DATA_DIR, "genre_chart.png")
    fig.write_image(img_path, scale=2)
    print(f"Generated chart: {img_path}")
    return genre_counts


def genre_slug(genre):
    return slugify(genre)


def build_genre_index(works, work_stems, poet_stem_map, poet_stems):
    poet_by_stem = {}
    order = {}
    genres = {}
    for idx, ((_, w), stem) in enumerate(zip(works.iterrows(), work_stems)):
        genre = str(w.get("Genre", "")).strip()
        if not genre or genre.lower() == "nan":
            genre = "Uncategorized"
        gs = genre_slug(genre)
        order.setdefault(gs, genre)
        genres.setdefault(gs, {"genre": genre, "works": [], "poets": {}})
        wname = str(w.get("Name of the Work", w.get("Title", "Unknown"))).strip()
        author = first_line(w.get("Author", ""))
        astem = poet_stem_map.get(author, "")
        genres[gs]["works"].append({"name": wname, "stem": stem, "author": author, "author_stem": astem})
        if astem:
            genres[gs]["poets"].setdefault(astem, author)
    ordered = sorted(genres.items(), key=lambda kv: (-len(kv[1]["works"]), kv[1]["genre"].lower()))
    return ordered


def generate_genre_qmd(works, work_stems, poet_stem_map, poet_stems):
    ordered = build_genre_index(works, work_stems, poet_stem_map, poet_stems)
    n_works = len(works)
    n_genres = len(ordered)

    lines = [
        "---",
        'title: "Browse by Genre"',
        "format: html",
        "toc: false",
        "---",
        "",
        "```{=html}",
        '<div class="genre-controls">',
        '  <input type="text" id="genre-search" class="form-control" placeholder="Filter poets and works by name...">',
        '  <div class="genre-pills" id="genre-pills">',
        '    <button type="button" class="genre-pill active" data-genre="all">All <span class="pill-count">'
        + str(n_works)
        + "</span></button>",
    ]
    for gs, g in ordered:
        lines.append(
            '    <button type="button" class="genre-pill" data-genre="'
            + gs
            + '">'
            + html_escape(g["genre"])
            + ' <span class="pill-count">'
            + str(len(g["works"]))
            + "</span></button>"
        )
    lines.append("  </div>")
    lines.append('  <div id="genre-status" class="text-muted small mt-2"></div>')
    lines.append("</div>")
    lines.append("")

    for gs, g in ordered:
        lines.append(
            '<section class="genre-section" id="'
            + gs
            + '" data-genre="'
            + gs
            + '" data-search="'
            + html_escape(
                fold_text(
                    g["genre"]
                    + " "
                    + " ".join(x["name"] for x in g["works"])
                    + " "
                    + " ".join(g["poets"].values())
                )
            )
            + '">'
        )
        lines.append(
            '  <h2 class="genre-heading">'
            + html_escape(g["genre"])
            + ' <span class="badge bg-primary">'
            + str(len(g["works"]))
            + " works</span> "
            + '<span class="badge bg-primary-subtle text-primary-emphasis">'
            + str(len(g["poets"]))
            + " poets</span></h2>"
        )
        if g["poets"]:
            plist = " ".join(
                '<a class="genre-chip" data-search="'
                + html_escape(fold_text(name))
                + '" href="poets/'
                + s
                + '.html">'
                + html_escape(name)
                + "</a>"
                for s, name in sorted(g["poets"].items(), key=lambda kv: kv[1].lower())
            )
            lines.append('  <p class="genre-poets"><strong>Poets:</strong> ' + plist + "</p>")
        else:
            lines.append('  <p class="genre-poets text-muted">No linked poets.</p>')
        lines.append('  <ul class="genre-works">')
        for w in sorted(g["works"], key=lambda x: x["name"].lower()):
            author_html = (
                '<a href="poets/' + w["author_stem"] + '.html">' + html_escape(w["author"]) + "</a>"
                if w["author_stem"]
                else html_escape(w["author"])
            )
            lines.append(
                '    <li data-search="'
                + html_escape(fold_text(w["name"] + " " + w["author"]))
                + '"><a href="works/'
                + w["stem"]
                + '.html">'
                + html_escape(w["name"])
                + "</a>"
                + (' <span class="genre-work-author">by ' + author_html + "</span>" if w["author"] else "")
                + "</li>"
            )
        lines.append("  </ul>")
        lines.append("</section>")
    lines.append("")

    lines.append("```")
    lines.append("")
    lines.append("```{=html}")
    lines.append(generate_genre_js())
    lines.append("```")
    lines.append("")

    filepath = os.path.join(BASE_DIR, "genre.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_genre_js():
    return (
        "<script>"
        "(function(){"
        "var input=document.getElementById('genre-search');"
        "var pills=document.getElementById('genre-pills');"
        "var status=document.getElementById('genre-status');"
        "var sections=document.querySelectorAll('.genre-section');"
        "if(!sections.length)return;"
        "var active='all';"
        "function fold(s){return (s||'').toString().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();}"
        "function apply(){var q=input?fold(input.value.trim()):'';var visible=0,total=0;"
        "for(var i=0;i<sections.length;i++){var sec=sections[i];"
        "var genreOk=(active==='all'||sec.getAttribute('data-genre')===active);"
        "var items=sec.querySelectorAll('[data-search]');"
        "var shown=0;"
        "for(var j=0;j<items.length;j++){var el=items[j];"
        "var match=!q||el.getAttribute('data-search').indexOf(q)!==-1;"
        "if(el.tagName==='LI'){el.style.display=match?'':'none';}else{el.style.display=match?'':'none';}"
        "if(match)shown++;}"
        "var show=genreOk&&(shown>0||!q);"
        "sec.style.display=show?'':'none';"
        "if(show){visible++;total+=items.length;}}"
        "if(status){status.textContent=q?('Filtering by \"'+input.value.trim()+'\" \\u2014 '+visible+' genre(s) shown'):'';}"
        "}"
        "function setActive(g){active=g;"
        "var all=pills.querySelectorAll('.genre-pill');"
        "for(var i=0;i<all.length;i++){all[i].classList.toggle('active',all[i].getAttribute('data-genre')===g);}"
        "apply();}"
        "if(pills){pills.addEventListener('click',function(e){var b=e.target.closest('.genre-pill');if(!b)return;setActive(b.getAttribute('data-genre'));if(history.replaceState){history.replaceState(null,'',b.getAttribute('data-genre')==='all'?location.pathname:('#'+b.getAttribute('data-genre')));}});}"
        "if(input){input.addEventListener('input',apply);}"
        "var h=(location.hash||'').replace('#','');"
        "if(h){var ok=false;var all=pills?pills.querySelectorAll('.genre-pill'):[];for(var k=0;k<all.length;k++){if(all[k].getAttribute('data-genre')===h)ok=true;}"
        "if(ok){setActive(h);}else{apply();}}else{apply();}"
        "})();</script>"
    )


def generate_table_js(table_id, search_id, info_id, pag_id, size_id, default_size):
    return (
        "<script>"
        "(function(){"
        "var TABLE=document.getElementById('" + table_id + "');if(!TABLE)return;"
        "var SEARCH=document.getElementById('" + search_id + "');"
        "var INFO=document.getElementById('" + info_id + "');"
        "var PAG=document.getElementById('" + pag_id + "');"
        "var SIZE=document.getElementById('" + size_id + "');"
        "var tbody=TABLE.tBodies[0];"
        "var rows=Array.prototype.slice.call(tbody.rows);"
        "var ths=Array.prototype.slice.call(TABLE.tHead.rows[0].cells);"
        "var pageSize=" + str(default_size) + ";var page=1;var sortKey=-1,sortDir=1;"
        "function fold(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();}"
        "function applyFilter(){var q=SEARCH?fold(SEARCH.value):'';"
        "if(q){var f=[];for(var i=0;i<rows.length;i++){if(rows[i].getAttribute('data-search').indexOf(q)!==-1)f.push(rows[i]);}return f;}return rows.slice();}"        "function current(f){var s=f.slice();if(sortKey>=0){var k=sortKey,d=sortDir;"
        "s.sort(function(a,b){var av=a.cells[k].textContent.trim().toLowerCase();var bv=b.cells[k].textContent.trim().toLowerCase();if(av<bv)return-d;if(av>bv)return d;return 0;});}return s;}"
        "function pageList(cur,total){var out=[];var prev=0;for(var i=1;i<=total;i++){if(i===1||i===2||i===cur-1||i===cur||i===cur+1||i===total-1||i===total){if(i-prev>1)out.push('...');out.push(i);prev=i;}}return out;}"
        "function render(){var f=applyFilter();var s=current(f);var total=s.length;"
        "var pages=pageSize<0?1:Math.max(1,Math.ceil(total/pageSize));if(page>pages)page=pages;if(page<1)page=1;"
        "var start=pageSize<0?0:(page-1)*pageSize;var end=pageSize<0?total:Math.min(start+pageSize,total);"
        "for(var i=0;i<rows.length;i++)rows[i].style.display='none';"
        "for(var j=start;j<end;j++)s[j].style.display='';"
        "if(INFO)INFO.textContent='Showing '+(total?(start+1)+'-'+end+' of '+total:'0 of 0')+' entries';"
        "renderPager(pages);updateArrows();}"
        "function renderPager(pages){if(!PAG)return;"
        "var h='<nav><ul class=\"pagination pagination-sm justify-content-center mb-0\">';"
        "h+='<li class=\"page-item'+(page<=1?' disabled':'')+'\"><a class=\"page-link\" href=\"#\" data-page=\"'+(page-1)+'\">&laquo;</a></li>';"
        "var pl=pageList(page,pages);for(var i=0;i<pl.length;i++){"
        "if(pl[i]==='...'){h+='<li class=\"page-item disabled\"><span class=\"page-link\">&hellip;</span></li>';continue;}"
        "h+='<li class=\"page-item'+(pl[i]===page?' active':'')+'\"><a class=\"page-link\" href=\"#\" data-page=\"'+pl[i]+'\">'+pl[i]+'</a></li>';}"
        "h+='<li class=\"page-item'+(page>=pages?' disabled':'')+'\"><a class=\"page-link\" href=\"#\" data-page=\"'+(page+1)+'\">&raquo;</a></li>';"
        "h+='</ul></nav>';PAG.innerHTML=h;"
        "var links=PAG.querySelectorAll('a[data-page]');for(var j=0;j<links.length;j++){"
        "(function(a){a.addEventListener('click',function(e){e.preventDefault();var p=parseInt(a.getAttribute('data-page'),10);if(!isNaN(p)&&p>=1&&p<=pages){page=p;render();}});})(links[j]);}}"
        "function updateArrows(){for(var i=0;i<ths.length;i++){var t=ths[i].querySelector('.sort-indicator');if(!t)continue;t.textContent=(i===sortKey)?(sortDir===1?' \\u2191':' \\u2193'):'';}}"
        "for(var h=0;h<ths.length;h++){(function(th,idx){if(!th.hasAttribute('data-sort'))return;th.style.cursor='pointer';"
        "th.addEventListener('click',function(){if(sortKey===idx){sortDir=-sortDir;}else{sortKey=idx;sortDir=1;}page=1;render();});})(ths[h],h);}"
        "if(SEARCH)SEARCH.addEventListener('input',function(){page=1;render();});"
        "if(SIZE)SIZE.addEventListener('change',function(){pageSize=parseInt(SIZE.value,10);page=1;render();});"
        "render();})();</script>"
    )


DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
IAST_RE = re.compile(r"[āĀīĪūŪṛṚṝṜḷḶṣṢśŚñÑṅṄṇṆḥḤṃṂṭṬḍḌ]")
DANDA_RE = re.compile(r"[।॥]")
QUOTE_NUM_RE = re.compile(r"(?m)^\s*\d+\.\s+")
BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _is_reference(content):
    """A verse reference like `[pañcatantram]` or `[mudrārākṣasam – 2.17]`."""
    return bool(
        DEVANAGARI_RE.search(content)
        or IAST_RE.search(content)
        or re.search(r"\d", content)
    )


def _split_block(block):
    """Return (verse, meaning) for one quotation block.

    A block with Devanagari is the verse (Sanskrit + transliteration + its
    `[reference]`); the English translation follows the reference bracket.
    A block with no Devanagari is treated as all meaning.
    """
    block = re.sub(r"[ \t]+", " ", block)
    block = re.sub(r"\s*\n\s*", " ", block).strip()
    if not block:
        return "", ""

    if not DEVANAGARI_RE.search(block):
        return "", block

    end = -1
    for m in BRACKET_RE.finditer(block):
        if _is_reference(m.group(0)):
            end = m.end()

    if end == -1:
        return block, ""

    verse = block[:end].strip()
    meaning = block[end:].strip()
    meaning = meaning.lstrip(" .,;:—–-)]").strip()
    return verse, meaning


def split_quotation(cell):
    """Split a `Quotable Quotations` cell into a list of (verse, meaning) pairs.

    Each cell may hold several numbered quotations; each is returned as a
    (verse, meaning) pair where `meaning` is the English translation.
    """
    text = str(cell).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or text.lower() == "nan":
        return []
    results = []
    for block in QUOTE_NUM_RE.split(text):
        verse, meaning = _split_block(block)
        if verse or meaning:
            results.append((verse, meaning))
    return results


def _truncate(text, limit):
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def build_quotes_marquee(works):
    items = []
    for _, w in works.iterrows():
        author = first_line(w.get("Author", ""))
        wname = str(w.get("Name of the Work", "")).strip()
        for verse, meaning in split_quotation(w.get("Quotable Quotations", "")):
            items.append(
                (
                    html_escape(_truncate(verse, 220)),
                    html_escape(_truncate(meaning, 320)),
                    html_escape(author),
                    html_escape(_truncate(wname, 60)),
                )
            )
    if not items:
        return []
    item_html = "".join(
        '<div class="marquee-item">'
        + ('<div class="m-quote">' + v + "</div>" if v else "")
        + ('<div class="m-meaning">' + m + "</div>" if m else "")
        + '<div class="m-source">&mdash; ' + a + " &bull; " + wk + "</div>"
        + "</div>"
        for v, m, a, wk in items
    )
    duration = max(160, len(items) * 16)
    track = (
        '<div class="marquee-track" style="animation-duration:'
        + str(duration)
        + 's">'
        + item_html
        + item_html
        + "</div>"
    )
    marquee = (
        '<div class="quotes-marquee" aria-hidden="true" tabindex="-1">'
        + track
        + "</div>"
    )
    return ["", "---", "", "```{=html}", marquee, "```", ""]


def generate_index_qmd(poets, works, genre_counts):
    n_poets = len(poets)
    n_works = len(works)
    n_genres = works["Genre"].nunique()

    lines = [
        "---",
        'title: "Kavi Kaavya Kadambakam"',
        'description: "Explore classical Sanskrit poets and their works"',
        "format: html",
        "---",
        "",
        "## About This Project",
        "",
        "[Edit this section to describe your project. This is a placeholder for project information that you will fill in.]",
        "",
        "## Overview",
        "",
        "::: {.kpi-row}",
        "::: {.value-box}",
        "::: {.value-box-number}",
        f"{n_poets}",
        ":::",
        "Poets",
        ":::",
        "::: {.value-box}",
        "::: {.value-box-number}",
        f"{n_works}",
        ":::",
        "Works",
        ":::",
        "::: {.value-box}",
        "::: {.value-box-number}",
        f"{n_genres}",
        ":::",
        "Genres",
        ":::",
        ":::"]
    lines.append("")
    lines.append("## Genre Distribution")
    lines.append("")
    lines.append("![Works by Genre](data/genre_chart.png)")
    lines.append("")
    lines.append("## Additional Information")
    lines.append("")
    lines.append("[Add markdown files in the `home/` directory to include additional content here.]")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Explore")
    lines.append("")
    lines.append("- [Poets](poets/index.qmd) — Browse all poets")
    lines.append("- [Works](works/index.qmd) — Browse all works")
    lines.append("- [Genres](genre.qmd) — Browse poets and works by genre")
    lines.append("- [Search](search.qmd) — Search the entire corpus")
    lines.append("- [About](about.qmd) — About this site")
    lines.append("")
    lines.extend(build_quotes_marquee(works))

    filepath = os.path.join(BASE_DIR, "index.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_about_qmd():
    lines = [
        "---",
        'title: "About This Site"',
        "format: html",
        "---",
        "",
        "This is a static website built with Quarto and Python, exploring classical Sanskrit poets and their literary works. The data is sourced from CSV files containing information about poets and their contributions to Sanskrit literature.",
        "",
        "## Features",
        "",
        "- Browse poets and works with search and pagination",
        "- Explore detailed information through tabbed and accordion layouts",
        "- View genre distribution of works",
        "",
        "## Data Sources",
        "",
        "- Poets data: `poetsfeed.csv`",
        "- Works data: `worksfeed.csv`",
        "",
        "## Credits",
        "",
        "[Add credits and additional information here.]",
        "",
    ]

    filepath = os.path.join(BASE_DIR, "about.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def clean_text(s, limit=1500):
    s = str(s).strip()
    if s == "nan" or not s:
        return ""
    if limit and len(s) > limit:
        return s[:limit] + "…"
    return s


def build_search_records(poets, works, poet_stems, work_stems, poet_stem_map):
    records = []
    for (_, poet), stem in zip(poets.iterrows(), poet_stems):
        name = str(poet.get("Name of the Poet", poet.get("Title", "Unknown"))).strip()
        period = clean_text(poet.get("Time period of the Poet", ""))
        life = clean_text(poet.get("Life of the Poet", ""))
        contrib = clean_text(poet.get("Contribution of the poet to the Sanskrit Literature", ""))
        parts = []
        if period:
            parts.append("Time period: " + period)
        if life:
            parts.append("Life: " + life)
        if contrib:
            parts.append("Contribution: " + contrib)
        text = "\n".join(parts)
        records.append({
            "type": "poet",
            "name": name,
            "link": "poets/" + stem + ".html",
            "text": text,
            "fhay": fold_text(name + "\n" + text),
        })
    for (_, work), stem in zip(works.iterrows(), work_stems):
        name = str(work.get("Name of the Work", work.get("Title", "Unknown"))).strip()
        author = first_line(work.get("Author", ""))
        genre = clean_text(work.get("Genre", ""))
        summary = clean_text(work.get("Summary of the work", ""))
        contents = clean_text(work.get("Contents of the work", ""))
        uniqueness = clean_text(work.get("Uniqueness of the work", ""))
        contrib = clean_text(work.get("Contribution to Sanskrit Literature", ""))
        other = clean_text(work.get("Any other notable information", ""))
        quotes = clean_text(work.get("Quotable Quotations", ""), limit=0)
        parts = []
        if author:
            parts.append("Author: " + author)
        if genre:
            parts.append("Genre: " + genre)
        if summary:
            parts.append("Summary: " + summary)
        if contents:
            parts.append("Contents: " + contents)
        if uniqueness:
            parts.append("Uniqueness: " + uniqueness)
        if contrib:
            parts.append("Contribution: " + contrib)
        if other:
            parts.append("Notes: " + other)
        if quotes:
            parts.append("Quotable quotations: " + quotes)
        text = "\n".join(parts)
        author_stem = poet_stem_map.get(author, "")
        records.append({
            "type": "work",
            "name": name,
            "link": "works/" + stem + ".html",
            "author": author,
            "authorLink": ("poets/" + author_stem + ".html") if author_stem else "",
            "text": text,
            "fhay": fold_text(name + "\n" + author + "\n" + text),
        })
    return records


def generate_search_js():
    return (
        "(function(){"
        "var el=document.getElementById('search-data');if(!el)return;"
        "var DATA=JSON.parse(el.textContent);"
        "var input=document.getElementById('global-search');var status=document.getElementById('search-status');var out=document.getElementById('search-results');"
        "if(!input)return;"
        "function fold(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();}"
        "function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}"
        "function mark(t,q){var qe=q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');try{return esc(t).replace(new RegExp('('+qe+')','gi'),'<mark>$1</mark>');}catch(e){return esc(t);}}"
        "function snippet(t,q){var low=t.toLowerCase();var lq=q.toLowerCase();var i=low.indexOf(lq);var max=220;"
        "if(i<0){return esc(t.slice(0,max))+(t.length>max?'\\u2026':'');}"
        "var start=Math.max(0,i-60);var slice=t.slice(start,start+max);"
        "return (start>0?'\\u2026':'')+mark(slice,q)+(start+max<t.length?'\\u2026':'');}"
        "function render(q){q=(q||'').trim();if(!q){out.innerHTML='<p class=\"text-muted\">Type in the box to search all poets and works \\u2014 including summaries, contributions and quotable quotations.</p>';status.textContent='';return;}"
        "var lq=fold(q);var poets=[];var works=[];"
        "for(var i=0;i<DATA.length;i++){var d=DATA[i];if(d.fhay.indexOf(lq)===-1)continue;if(d.type==='poet')poets.push(d);else works.push(d);}"
        "var h='';"
        "h+='<h3 class=\"mt-2\">Poets <span class=\"badge bg-secondary align-middle\">'+poets.length+'</span></h3>';"
        "if(poets.length){h+='<ul class=\"list-group list-group-flush mb-4\">';"
        "for(var p=0;p<poets.length;p++){var pd=poets[p];h+='<li class=\"list-group-item px-0\">';"
        "h+='<a class=\"fs-5 fw-semibold\" href=\"'+pd.link+'\">'+mark(pd.name,q)+'</a>';"
        "h+='<div class=\"text-muted small mt-1\">'+snippet(pd.text,q)+'</div></li>';}"
        "h+='</ul>';}else{h+='<p class=\"text-muted\">No matching poets.</p>';}"
        "h+='<h3 class=\"mt-4\">Works <span class=\"badge bg-secondary align-middle\">'+works.length+'</span></h3>';"
        "if(works.length){h+='<ul class=\"list-group list-group-flush mb-4\">';"
        "for(var w=0;w<works.length;w++){var wd=works[w];h+='<li class=\"list-group-item px-0\">';"
        "h+='<a class=\"fs-5 fw-semibold\" href=\"'+wd.link+'\">'+mark(wd.name,q)+'</a>';"
        "if(wd.author){h+=' <span class=\"text-muted small\">by '+(wd.authorLink?'<a href=\"'+wd.authorLink+'\">'+mark(wd.author,q)+'</a>':mark(wd.author,q))+'</span>';}"
        "h+='<div class=\"text-muted small mt-1\">'+snippet(wd.text,q)+'</div></li>';}"
        "h+='</ul>';}else{h+='<p class=\"text-muted\">No matching works.</p>';}"
        "status.textContent=poets.length+works.length+' result(s) for \"'+q+'\"';out.innerHTML=h;}"
        "input.addEventListener('input',function(){render(input.value);});"
        "var params=new URLSearchParams(window.location.search);var q0=params.get('q')||'';if(q0){input.value=q0;render(q0);}"
        "})();"
    )


def generate_search_qmd(poets, works, poet_stems, work_stems, poet_stem_map):
    records = build_search_records(poets, works, poet_stems, work_stems, poet_stem_map)
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    lines = [
        "---",
        'title: "Search"',
        "format: html",
        "---",
        "",
        "```{=html}",
        '<div class="mb-3">',
        '  <input type="text" id="global-search" class="form-control form-control-lg" placeholder="Search poets, works, quotes, summaries..." autofocus>',
        '  <div id="search-status" class="text-muted small mt-2"></div>',
        "</div>",
        '<div id="search-results"></div>',
        "```",
        "",
        "```{=html}",
        '<script type="application/json" id="search-data">',
        data_json,
        "</script>",
        "```",
        "",
        "```{=html}",
        "<script>",
        generate_search_js(),
        "</script>",
        "```",
        "",
    ]

    filepath = os.path.join(BASE_DIR, "search.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_navbar_search_html():
    html = """<script>
(function () {
  function init() {
    var nav = document.querySelector('.navbar .navbar-collapse');
    if (!nav || document.getElementById('navbar-search-form')) return;
    if (document.getElementById('global-search')) return;
    var prefix = '';
    var brand = document.querySelector('.navbar-brand');
    if (brand) {
      var href = brand.getAttribute('href') || '';
      prefix = href.replace(/index\\.html.*$/, '');
    }
    var form = document.createElement('form');
    form.id = 'navbar-search-form';
    form.setAttribute('role', 'search');
    form.className = 'navbar-search ms-auto my-2 my-lg-0';
    form.innerHTML = '<input class="form-control form-control-sm" type="search" placeholder="Search site..." aria-label="Search" autocomplete="off">';
    nav.appendChild(form);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = form.querySelector('input').value.trim();
      if (!q) return;
      window.location.href = prefix + 'search.html?q=' + encodeURIComponent(q);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>"""
    filepath = os.path.join(BASE_DIR, "navbar-search.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {filepath}")


def generate_poets_index_qmd(poets, poet_stems, works_by_stem):
    lines = [
        "---",
        'title: "Poets"',
        "format: html",
        "---",
        "",
        "```{=html}",
        '<div class="mb-3">',
        '      <input type="text" id="poet-search" class="form-control form-control-lg" placeholder="Search poets by name or works...">',
        "</div>",
        '<div class="table-responsive">',
        '<table id="poet-table" class="table table-hover table-striped align-middle">',
        "  <thead>",
        "    <tr>",
        '      <th scope="col" data-sort style="width:90px;">Poet ID</th>',
        '      <th scope="col" data-sort class="poet-name">Name</th>',
        '      <th scope="col" data-sort>Works</th>',
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ]

    for (_, poet), stem in zip(poets.iterrows(), poet_stems):
        name = str(poet.get("Name of the Poet", poet.get("Title", "Unknown"))).strip()
        pid = str(poet.get("Poet ID", "")).strip()
        if pid == "nan":
            pid = ""
        esc_name = html_escape(name)
        wlist = works_by_stem.get(stem, [])
        if wlist:
            works_html = "".join(
                f'<a href="../works/{w["stem"]}.html">{html_escape(w["name"])}</a>'
                for w in wlist
            )
            cell = f'<td class="poet-works">{works_html}</td>'
        else:
            cell = '<td class="poet-works"><span class="text-muted">&mdash;</span></td>'
        work_names = " ".join(w["name"] for w in wlist)
        hay = fold_text(" ".join([pid, name, work_names]))
        lines.append(f'    <tr data-search="{html_escape(hay)}">')
        lines.append(f'      <td class="text-muted">{html_escape(pid)}</td>')
        lines.append(f'      <td class="poet-name"><a href="{stem}.html">{esc_name}</a></td>')
        lines.append(cell)
        lines.append("    </tr>")

    lines.append("  </tbody>")
    lines.append("</table>")
    lines.append("</div>")
    lines.append('<div class="d-flex flex-wrap justify-content-between align-items-center gap-2">')
    lines.append('  <div id="poet-info" class="text-muted small"></div>')
    lines.append('  <div class="d-flex align-items-center gap-2">')
    lines.append('    <label class="small text-muted mb-0" for="poet-page-size">Rows:</label>')
    lines.append('    <select id="poet-page-size" class="form-select form-select-sm" style="width:auto;">')
    lines.append('      <option value="10" selected>10</option>')
    lines.append('      <option value="25">25</option>')
    lines.append('      <option value="50">50</option>')
    lines.append('      <option value="100">100</option>')
    lines.append('      <option value="-1">All</option>')
    lines.append("    </select>")
    lines.append("  </div>")
    lines.append("</div>")
    lines.append('<div id="poet-pagination" class="mt-3"></div>')
    lines.append("```")
    lines.append("")
    lines.append("```{=html}")
    lines.append(generate_table_js("poet-table", "poet-search", "poet-info", "poet-pagination", "poet-page-size", 10))
    lines.append("```")

    filepath = os.path.join(BASE_DIR, "poets", "index.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_works_index_qmd(works, work_stems, poet_stem_map):
    lines = [
        "---",
        'title: "Works"',
        "format: html",
        "---",
        "",
        "```{=html}",
        '<div class="mb-3">',
        '  <input type="text" id="work-search" class="form-control form-control-lg" placeholder="Search works by title, author or genre...">',
        "</div>",
        '<div class="table-responsive">',
        '<table id="work-table" class="table table-hover table-striped align-middle">',
        "  <thead>",
        "    <tr>",
        '      <th scope="col" data-sort>Work ID</th>',
        '      <th scope="col" data-sort>Work</th>',
        '      <th scope="col" data-sort>Author</th>',
        '      <th scope="col" data-sort>Genre</th>',
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ]

    for (_, work), stem in zip(works.iterrows(), work_stems):
        name = str(work.get("Name of the Work", work.get("Title", "Unknown"))).strip()
        wid = str(work.get("Work ID", "")).strip()
        author = first_line(work.get("Author", ""))
        genre = str(work.get("Genre", "")).strip()
        if genre == "nan":
            genre = ""
        esc_name = html_escape(name)
        esc_genre = html_escape(genre)
        esc_author = html_escape(author)
        author_stem = poet_stem_map.get(author, "")
        author_cell = f'<a href="../poets/{author_stem}.html">{esc_author}</a>' if author_stem else esc_author
        hay = fold_text(" ".join([wid, name, author, genre]))
        lines.append(f'    <tr data-search="{html_escape(hay)}">')
        lines.append(f'      <td class="text-muted">{html_escape(wid)}</td>')
        lines.append(f'      <td class="work-name-cell"><a href="{stem}.html">{esc_name}</a></td>')
        lines.append(f'      <td class="work-author-cell">{author_cell}</td>')
        if genre:
            genre_cell = f'<a class="badge bg-primary-subtle text-primary-emphasis text-decoration-none" href="../genre.html#{genre_slug(genre)}">{esc_genre}</a>'
        else:
            genre_cell = '<span class="text-muted">&mdash;</span>'
        lines.append(f'      <td class="work-genre-cell">{genre_cell}</td>')
        lines.append("    </tr>")

    lines.append("  </tbody>")
    lines.append("</table>")
    lines.append("</div>")
    lines.append('<div class="d-flex flex-wrap justify-content-between align-items-center gap-2">')
    lines.append('  <div id="work-info" class="text-muted small"></div>')
    lines.append('  <div class="d-flex align-items-center gap-2">')
    lines.append('    <label class="small text-muted mb-0" for="work-page-size">Rows:</label>')
    lines.append('    <select id="work-page-size" class="form-select form-select-sm" style="width:auto;">')
    lines.append('      <option value="15" selected>15</option>')
    lines.append('      <option value="25">25</option>')
    lines.append('      <option value="50">50</option>')
    lines.append('      <option value="100">100</option>')
    lines.append('      <option value="-1">All</option>')
    lines.append("    </select>")
    lines.append("  </div>")
    lines.append("</div>")
    lines.append('<div id="work-pagination" class="mt-3"></div>')
    lines.append("```")
    lines.append("")
    lines.append("```{=html}")
    lines.append(generate_table_js("work-table", "work-search", "work-info", "work-pagination", "work-page-size", 15))
    lines.append("```")

    filepath = os.path.join(BASE_DIR, "works", "index.qmd")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_quarto_yml():
    lines = [
        "project:",
        "  type: website",
        "  render:",
        '    - "*.qmd"',
        '    - "poets/*.qmd"',
        '    - "works/*.qmd"',
        '  post-render: "python -c \\"import os; p=\'_site/search.json\'; os.path.exists(p) and os.remove(p)\\""',
        "",
        "website:",
        "  title: \"Kavi Kaavya Kadambakam\"",
        '  description: "Explore classical Sanskrit poets and their works"',
        "  search: false",
        "  navbar:",
        "    left:",
        "      - href: index.qmd",
        "        text: Home",
        "      - href: about.qmd",
        "        text: About",
        "      - href: poets/index.qmd",
        "        text: Poets",
        "      - href: works/index.qmd",
        "        text: Works",
        "      - href: genre.qmd",
        "        text: Genres",
        "  page-footer:",
        '    left: "**Kavi Kaavya Kadambakam**"',
        '    center: "[Add footer content here. This footer can be populated later.]"',
        '    right: "Built with [Quarto](https://quarto.org)"',
        "",
        "format:",
        "  html:",
        "    theme: cosmo",
        "    toc: true",
        "    toc-depth: 2",
        "    css: styles.css",
        "    include-in-header: navbar-search.html",
        "",
    ]

    filepath = os.path.join(BASE_DIR, "_quarto.yml")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated: {filepath}")


def generate_styles_css():
    css = """
:root {
  --bg: #fff8ed;
  --bg-soft: #f9efdb;
  --panel: #fffdf7;
  --maroon: #6b0f1a;
  --maroon-dark: #470810;
  --gold: #c8894a;
  --ink: #3f312b;
  --muted: #8a7566;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: var(--bg);
  color: var(--ink);
}

a {
  color: var(--maroon);
}

a:hover {
  color: var(--maroon-dark);
}

strong, b {
  color: var(--maroon-dark);
}

h1, h2, h3, h4, h5, h6 {
  color: var(--maroon-dark);
  font-family: Georgia, "Times New Roman", serif;
}

.quarto-title-block .title {
  color: var(--maroon-dark);
  font-size: 2.4rem;
  font-weight: 700;
}

.quarto-title-block .description {
  color: var(--muted);
  font-style: italic;
}

h1 {
  border-bottom: 2px solid rgba(107, 15, 26, 0.25);
  padding-bottom: 0.3em;
  font-weight: 700;
}

h2 {
  margin-top: 1.5em;
  font-weight: 600;
}

.navbar {
  background-color: var(--bg-soft) !important;
  border-bottom: 2px solid var(--maroon);
}

.navbar .navbar-brand {
  color: var(--maroon-dark);
  font-weight: 700;
}

.navbar .nav-link {
  color: var(--ink);
}

.navbar .nav-link:hover,
.navbar .nav-link.active {
  color: var(--maroon-dark);
  font-weight: 600;
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.25rem;
  margin: 1.5rem 0;
}

.value-box {
  background-color: var(--panel);
  border: 2px solid var(--maroon);
  border-top: 6px solid var(--maroon);
  border-radius: 14px;
  padding: 1.75rem 1.25rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  box-sizing: border-box;
  box-shadow: 0 3px 12px rgba(107, 15, 26, 0.07);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.value-box:hover {
  transform: translateY(-4px);
  box-shadow: 0 10px 26px rgba(107, 15, 26, 0.14);
}

.value-box-number {
  color: var(--maroon);
  font-size: clamp(2.5rem, 3.5vw, 3.25rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.03em;
  white-space: nowrap;
}

.value-box-number p {
  margin: 0;
  font-size: inherit;
  font-weight: inherit;
  line-height: inherit;
  color: inherit;
  white-space: nowrap;
}

.value-box > p {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.card {
  border-radius: 12px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  overflow: hidden;
}

.card-body {
  padding: 1.25rem;
}

.table thead th {
  white-space: nowrap;
  -webkit-user-select: none;
  user-select: none;
  color: var(--maroon-dark);
  background-color: var(--bg-soft);
  border-bottom: 2px solid rgba(107, 15, 26, 0.3);
}

.table thead th .sort-indicator {
  display: inline-block;
  min-width: 0.9rem;
  color: var(--maroon);
}

.table tbody td a {
  text-decoration: none;
}

.table tbody td a:hover {
  text-decoration: underline;
}

.table tbody tr {
  vertical-align: middle;
}

#poet-table th.poet-name,
#poet-table td.poet-name {
  width: 240px;
  min-width: 200px;
  white-space: nowrap;
}

#poet-table td.poet-name,
#poet-table td.poet-name a,
#work-table td.work-name-cell,
#work-table td.work-name-cell a,
#work-table td.work-author-cell,
#work-table td.work-author-cell a {
  font-weight: 700;
  font-size: 1.05rem;
}

#poet-table td.poet-works {
  font-size: 0.9rem;
  line-height: 1.9;
}

#poet-table td.poet-works a {
  margin-right: 0.4rem;
  white-space: nowrap;
}

#poet-table td.poet-works a::after {
  content: "\\00b7";
  margin-left: 0.4rem;
  color: #b89a72;
}

#poet-table td.poet-works a:last-child::after {
  content: "";
  margin-left: 0;
}

mark {
  background-color: #ffe3a3;
  padding: 0 0.1rem;
  border-radius: 3px;
}

.badge.bg-primary {
  background-color: var(--maroon) !important;
  color: #fff8ed !important;
}

.badge.bg-primary-subtle {
  background-color: #f1dfc0 !important;
  color: var(--maroon-dark) !important;
}

.badge.text-primary-emphasis {
  color: var(--maroon-dark) !important;
}

.navbar-search input {
  border-radius: 20px;
  border: 2px solid #e3d3b0;
}

.navbar-search input:focus {
  border-color: var(--maroon);
  box-shadow: 0 0 0 0.2rem rgba(107, 15, 26, 0.12);
}

@media (min-width: 992px) {
  .navbar-search {
    flex: 0 1 280px;
  }
}

.nav-tabs .nav-link {
  font-size: 0.9rem;
  border: none;
  padding: 0.75rem 1.25rem;
  color: var(--muted);
}

.nav-tabs .nav-link.active {
  color: var(--maroon-dark);
  border-bottom: 2px solid var(--maroon);
  background: transparent;
}

.accordion-button {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--maroon-dark);
}

.accordion-button:not(.collapsed) {
  color: var(--maroon-dark);
  background-color: var(--bg-soft);
  box-shadow: none;
}

.accordion-body {
  font-size: 0.9rem;
}

.accordion-body p,
.accordion-body ul {
  font-size: 0.9rem;
}

.accordion-body ul {
  padding-left: 1.5rem;
}

.accordion-body li {
  margin-bottom: 0.3rem;
}

.badge {
  font-size: 0.75rem;
}

.work-author {
  display: block;
  width: 100%;
  white-space: normal;
}

.work-author-cell,
.work-author-cell a {
  white-space: nowrap;
}

.work-genre-cell,
.work-genre-badge {
  white-space: normal;
  word-break: break-word;
}

.work-genre-badge {
  display: inline-block;
  max-width: 100%;
  text-align: left;
  line-height: 1.35;
}

.pagination .page-link {
  color: var(--maroon);
}

.pagination .page-item.active .page-link {
  background-color: var(--maroon);
  border-color: var(--maroon);
  color: #fff8ed;
}

.pagination .btn {
  font-size: 0.85rem;
}

.tab-content {
  padding-top: 1rem;
}

#poet-search,
#work-search,
#global-search {
  max-width: 500px;
  border-radius: 8px;
  border: 2px solid #e3d3b0;
  padding: 0.75rem 1rem;
}

#poet-search:focus,
#work-search:focus,
#global-search:focus {
  border-color: var(--maroon);
  box-shadow: 0 0 0 0.2rem rgba(107, 15, 26, 0.12);
}

.list-group-item {
  border: none;
  padding: 0.5rem 0;
}

.list-group-item a {
  text-decoration: none;
}

.list-group-item a:hover {
  color: var(--maroon-dark);
}

.lead {
  font-size: 1.1rem;
}

.nav-footer {
  background-color: var(--bg-soft);
  border-top: 2px solid var(--maroon);
  color: var(--muted);
  margin-top: 3rem;
}

.nav-footer a {
  color: var(--maroon);
}

.quotes-marquee {
  position: relative;
  overflow: hidden;
  height: 420px;
  max-height: 70vh;
  background: linear-gradient(180deg, var(--maroon-dark), var(--maroon) 50%, var(--maroon-dark));
  color: #fff8ed;
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  margin-top: 2.5rem;
  box-shadow: 0 6px 18px rgba(71, 8, 16, 0.3);
  -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 8%, #000 92%, transparent 100%);
  mask-image: linear-gradient(180deg, transparent 0, #000 8%, #000 92%, transparent 100%);
}

.marquee-track {
  display: flex;
  flex-direction: column;
  will-change: transform;
  animation: marquee-scroll 600s linear infinite;
}

.marquee-item {
  margin: 0 0 2rem;
  border-left: 3px solid #e8b86a;
  padding-left: 1rem;
}

.marquee-item .m-quote {
  display: block;
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1.6;
}

.marquee-item .m-meaning {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.98rem;
  line-height: 1.6;
  color: #f3d9b0;
}

.marquee-item .m-source {
  display: block;
  margin-top: 0.5rem;
  color: #e8b86a;
  font-size: 0.85rem;
  font-style: italic;
}

@keyframes marquee-scroll {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(-50%);
  }
}

.genre-controls {
  margin: 1.25rem 0 1.75rem;
}

.genre-controls #genre-search {
  max-width: 420px;
  border-radius: 8px;
  border: 2px solid #e3d3b0;
  padding: 0.6rem 1rem;
}

.genre-controls #genre-search:focus {
  border-color: var(--maroon);
  box-shadow: 0 0 0 0.2rem rgba(107, 15, 26, 0.12);
}

.genre-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1rem;
}

.genre-pill {
  background: var(--panel);
  border: 1px solid #ecd9b8;
  color: var(--maroon-dark);
  border-radius: 999px;
  padding: 0.35rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.genre-pill:hover {
  border-color: var(--maroon);
}

.genre-pill.active {
  background: var(--maroon);
  border-color: var(--maroon);
  color: #fff8ed;
}

.genre-pill .pill-count {
  display: inline-block;
  margin-left: 0.35rem;
  font-size: 0.72rem;
  opacity: 0.75;
}

.genre-section {
  border-top: 1px solid #ecd9b8;
  padding: 1.25rem 0 0.5rem;
  margin-top: 1rem;
}

.genre-heading {
  margin-top: 0.25rem;
}

.genre-heading .badge {
  vertical-align: middle;
}

.genre-poets {
  font-size: 0.92rem;
  margin-bottom: 0.6rem;
}

.genre-chip {
  display: inline-block;
  background: var(--bg-soft);
  border: 1px solid #ecd9b8;
  border-radius: 999px;
  padding: 0.1rem 0.65rem;
  margin: 0.15rem 0.25rem 0.15rem 0;
  font-size: 0.85rem;
  text-decoration: none;
}

.genre-chip:hover {
  background: #f1dfc0;
}

.genre-works {
  columns: 2;
  column-gap: 2rem;
  padding-left: 1.1rem;
  margin-bottom: 0.5rem;
}

@media (max-width: 768px) {
  .genre-works {
    columns: 1;
  }
}

.genre-work-author {
  color: var(--muted);
  font-size: 0.85rem;
}
"""
    filepath = os.path.join(BASE_DIR, "styles.css")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(css.strip() + "\n")
    print(f"Generated: {filepath}")


if __name__ == "__main__":
    print("Reading CSVs...")
    poets_df, works_df = read_csvs()
    print(f"  Poets: {len(poets_df)} rows")
    print(f"  Works: {len(works_df)} rows")

    for d in (POETS_DIR, WORKS_DIR, DATA_DIR, HOME_DIR):
        os.makedirs(d, exist_ok=True)

    for d in (POETS_DIR, WORKS_DIR):
        for fname in os.listdir(d):
            if fname.endswith(".qmd"):
                os.remove(os.path.join(d, fname))

    poet_stems = assign_stems(poets_df, "Name of the Poet")
    work_stems = assign_stems(works_df, "Name of the Work")
    poet_stem_map = build_poet_stem_map(poets_df, poet_stems)
    pw_map = build_poet_works_map(works_df, work_stems)

    print("\nGenerating poet qmd files...")
    for (_, poet), stem in zip(poets_df.iterrows(), poet_stems):
        generate_poet_qmd(poet, POETS_DIR, stem, pw_map)

    print("Generating work qmd files...")
    for (_, work), stem in zip(works_df.iterrows(), work_stems):
        generate_work_qmd(work, WORKS_DIR, stem, poet_stem_map)

    print("\nGenerating charts and data...")
    genre_counts = generate_genre_data(works_df)

    print("\nGenerating Quarto pages...")
    generate_quarto_yml()
    generate_styles_css()
    generate_index_qmd(poets_df, works_df, genre_counts)
    generate_about_qmd()
    generate_poets_index_qmd(poets_df, poet_stems, build_works_by_poet_stem(works_df, work_stems, poet_stem_map))
    generate_works_index_qmd(works_df, work_stems, poet_stem_map)
    generate_genre_qmd(works_df, work_stems, poet_stem_map, poet_stems)
    generate_search_qmd(poets_df, works_df, poet_stems, work_stems, poet_stem_map)
    generate_navbar_search_html()

    print("\nDone! All files generated. Now run: quarto render")