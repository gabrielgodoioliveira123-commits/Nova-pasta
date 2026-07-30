#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta o conteúdo público interno do Círculo de Estudos Nous em HTMLs pequenos.

O rastreador permanece no mesmo domínio, usa sitemap quando disponível, registra
links externos sem visitá-los, não baixa imagens e produz um ZIP portátil para IA.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import zipfile
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, Tag

ROOT = "https://www.circulodeestudosnous.com/"
ALLOWED_HOSTS = {"www.circulodeestudosnous.com", "circulodeestudosnous.com"}
OUT = Path("nous_corpus_web")
MAX_CHUNK_BYTES = 380_000
MAX_URLS = 500
TIMEOUT = 35
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 "
    "NousPublicArchive/1.0"
)

INSTITUTIONAL_PATHS = {
    "/", "/materias", "/comunidade", "/analises-diversas", "/livraria",
    "/login", "/contato", "/perfil", "/cursos",
    "/compromisso-nous-com-a-privacidade", "/termos", "/termos-de-uso",
    "/politica-de-privacidade", "/en/profile",
}

SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".avif",
    ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg", ".pdf", ".doc",
    ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z",
    ".css", ".js", ".json", ".xml", ".txt", ".woff", ".woff2", ".ttf",
}

BLOCK_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote",
    "pre", "figcaption", "dt", "dd", "th", "td",
]

@dataclass
class Record:
    url: str
    canonical: str
    title: str
    page_type: str
    status: int
    author: str
    published: str
    description: str
    text_sha256: str
    text_chars: int
    internal_links: list[str]
    external_links: list[str]
    images: list[dict[str, str]]
    blocks: list[dict[str, str]]
    source_method: str
    notes: list[str]
    output_file: str = ""


def norm_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c)).lower()


def normalize_url(url: str, base: str = ROOT) -> str | None:
    try:
        absolute = urljoin(base, url)
        p = urlparse(absolute)
        host = p.netloc.lower().split(":")[0]
        if host not in ALLOWED_HOSTS:
            return None
        path = re.sub(r"/{2,}", "/", p.path or "/")
        if path != "/":
            path = path.rstrip("/")
        if Path(path).suffix.lower() in SKIP_EXTENSIONS:
            return None
        return urlunparse(("https", "www.circulodeestudosnous.com", path, "", "", ""))
    except Exception:
        return None


def is_external(url: str, base: str) -> bool:
    p = urlparse(urljoin(base, url))
    return bool(p.netloc) and p.netloc.lower().split(":")[0] not in ALLOWED_HOSTS


def same_or_higher_heading(tag: Tag, level: int) -> bool:
    return bool(tag.name and re.fullmatch(r"h[1-6]", tag.name) and int(tag.name[1]) <= level)


def remove_deleted_puzzle(soup: BeautifulSoup, notes: list[str]) -> None:
    """Remove apenas o bloco conhecido como excluído pelo proprietário."""
    candidates = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "div"]):
        text = fold(tag.get_text(" ", strip=True))
        if "decifra-me" in text or "lhe devorarei" in text:
            candidates.append(tag)
    removed = 0
    for tag in candidates:
        if tag.parent is None:
            continue
        if tag.name and re.fullmatch(r"h[1-6]", tag.name):
            level = int(tag.name[1])
            current = tag
            while current is not None:
                nxt = current.find_next_sibling()
                current.decompose()
                removed += 1
                if nxt is None or (isinstance(nxt, Tag) and same_or_higher_heading(nxt, level)):
                    break
                current = nxt
        else:
            text_len = len(tag.get_text(" ", strip=True))
            if text_len < 25_000:
                tag.decompose()
                removed += 1
    if removed:
        notes.append(f"Bloco excluído 'Decifra-me...' removido do corpus ({removed} elemento(s)).")


def metadata(soup: BeautifulSoup, url: str) -> tuple[str, str, str, str, str]:
    def meta(*selectors: tuple[str, str]) -> str:
        for attr, value in selectors:
            node = soup.find("meta", attrs={attr: value})
            if node and node.get("content"):
                return norm_space(node["content"])
        return ""

    title = meta(("property", "og:title"), ("name", "twitter:title"))
    if not title and soup.title:
        title = norm_space(soup.title.get_text(" ", strip=True))
    if not title:
        h1 = soup.find("h1")
        title = norm_space(h1.get_text(" ", strip=True)) if h1 else url

    description = meta(("name", "description"), ("property", "og:description"))
    author = meta(("name", "author"), ("property", "article:author"))
    published = meta(("property", "article:published_time"), ("name", "date"))
    canonical_tag = soup.find("link", rel=lambda v: v and "canonical" in v)
    canonical = normalize_url(canonical_tag.get("href"), url) if canonical_tag else normalize_url(url)
    return title, description, author, published, canonical or url


def extract_links(soup: BeautifulSoup, url: str) -> tuple[list[str], list[str]]:
    internal, external = set(), set()
    for a in soup.find_all("a", href=True):
        href = norm_space(a.get("href", ""))
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if is_external(href, url):
            external.add(urljoin(url, href))
        else:
            normalized = normalize_url(href, url)
            if normalized:
                internal.add(normalized)
    return sorted(internal), sorted(external)


def extract_images(soup: BeautifulSoup, url: str) -> list[dict[str, str]]:
    out, seen = [], set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if not src:
            continue
        full = urljoin(url, src)
        if full in seen:
            continue
        seen.add(full)
        caption = ""
        fig = img.find_parent("figure")
        if fig:
            cap = fig.find("figcaption")
            if cap:
                caption = norm_space(cap.get_text(" ", strip=True))
        out.append({"url": full, "alt": norm_space(img.get("alt", "")), "legenda": caption})
    return out


def choose_content_root(soup: BeautifulSoup) -> Tag:
    for selector in ["article", "main", "[role=main]"]:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and len(node.get_text(" ", strip=True)) > 200:
            return node
    return soup.body or soup


def extract_blocks(root: Tag) -> list[dict[str, str]]:
    blocks, seen = [], set()
    for tag in root.find_all(BLOCK_TAGS):
        # Evita repetir células dentro de parágrafos e itens aninhados.
        if tag.find_parent(BLOCK_TAGS):
            continue
        text = norm_space(tag.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        name = tag.name.lower()
        if name in {"th", "td"}:
            name = "p"
        blocks.append({"tag": name, "text": text})
    if not blocks:
        text = norm_space(root.get_text(" ", strip=True))
        if text:
            blocks.append({"tag": "p", "text": text})
    return blocks


def detect_type(url: str, soup: BeautifulSoup, blocks: list[dict[str, str]]) -> str:
    path = urlparse(url).path.rstrip("/") or "/"
    if path in INSTITUTIONAL_PATHS:
        return "institucional"
    og_type = ""
    node = soup.find("meta", attrs={"property": "og:type"})
    if node:
        og_type = node.get("content", "").lower()
    joined = fold(" ".join(b["text"] for b in blocks[:15]))
    if og_type == "article" or "min ler" in joined or "referencias bibliograficas" in joined:
        return "artigo/ensaio"
    return "pagina-interna"


def visible_text_len(soup: BeautifulSoup) -> int:
    return len(norm_space((soup.body or soup).get_text(" ", strip=True)))


def render_with_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(url, wait_until="networkidle", timeout=90_000)
            page.wait_for_timeout(1200)
            content = page.content()
            browser.close()
            return content
    except Exception as exc:
        print(f"[playwright falhou] {url}: {exc}", file=sys.stderr)
        return ""


def fetch_page(session: requests.Session, url: str) -> tuple[int, str, str, list[str]]:
    notes: list[str] = []
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        status = r.status_code
        content_type = r.headers.get("content-type", "")
        if status != 200 or "html" not in content_type.lower():
            return status, "", "requests", notes
        raw = r.text
        soup = BeautifulSoup(raw, "lxml")
        if visible_text_len(soup) < 300:
            rendered = render_with_playwright(url)
            if rendered:
                notes.append("Conteúdo obtido com navegador renderizado por baixa densidade no HTML inicial.")
                return status, rendered, "playwright", notes
        return status, raw, "requests", notes
    except Exception as exc:
        notes.append(f"Falha em requests: {type(exc).__name__}: {exc}")
        rendered = render_with_playwright(url)
        if rendered:
            return 200, rendered, "playwright", notes
        return 0, "", "falha", notes


def sitemap_urls(session: requests.Session) -> tuple[set[str], list[str], list[str]]:
    found: set[str] = set()
    checked: list[str] = []
    errors: list[str] = []
    queue = deque([urljoin(ROOT, "sitemap.xml"), urljoin(ROOT, "sitemap_index.xml")])
    seen = set()
    while queue:
        sitemap = queue.popleft()
        if sitemap in seen:
            continue
        seen.add(sitemap)
        checked.append(sitemap)
        try:
            r = session.get(sitemap, timeout=TIMEOUT)
            if r.status_code != 200:
                errors.append(f"{sitemap}: HTTP {r.status_code}")
                continue
            root = ET.fromstring(r.content)
            locs = [norm_space(n.text or "") for n in root.iter() if n.tag.endswith("loc")]
            if root.tag.endswith("sitemapindex"):
                queue.extend(locs)
            else:
                for loc in locs:
                    n = normalize_url(loc)
                    if n:
                        found.add(n)
        except Exception as exc:
            errors.append(f"{sitemap}: {type(exc).__name__}: {exc}")
    return found, checked, errors


def clean_soup(soup: BeautifulSoup, notes: list[str]) -> None:
    remove_deleted_puzzle(soup, notes)
    for tag in soup.find_all(["script", "style", "noscript", "template", "svg", "canvas"]):
        tag.decompose()
    for selector in [
        "[aria-hidden=true]", ".cookie-banner", "#cookie-banner", ".cky-consent-container",
        ".popup", "[role=dialog]",
    ]:
        for tag in soup.select(selector):
            tag.decompose()


def page_section(record: Record) -> str:
    meta_bits = [
        f"<p><strong>URL:</strong> <a href=\"{html.escape(record.canonical)}\">{html.escape(record.canonical)}</a></p>",
        f"<p><strong>Tipo:</strong> {html.escape(record.page_type)}</p>",
    ]
    if record.author:
        meta_bits.append(f"<p><strong>Autoria:</strong> {html.escape(record.author)}</p>")
    if record.published:
        meta_bits.append(f"<p><strong>Data:</strong> {html.escape(record.published)}</p>")
    if record.description:
        meta_bits.append(f"<p><strong>Descrição:</strong> {html.escape(record.description)}</p>")

    body = []
    for block in record.blocks:
        tag = block["tag"] if block["tag"] in BLOCK_TAGS else "p"
        body.append(f"<{tag}>{html.escape(block['text'])}</{tag}>")

    internal = "".join(f"<li>{html.escape(x)}</li>" for x in record.internal_links)
    external = "".join(f"<li>{html.escape(x)}</li>" for x in record.external_links)
    images = "".join(
        "<li><strong>URL:</strong> " + html.escape(i["url"]) +
        (" | <strong>alt:</strong> " + html.escape(i["alt"]) if i["alt"] else "") +
        (" | <strong>legenda:</strong> " + html.escape(i["legenda"]) if i["legenda"] else "") +
        "</li>" for i in record.images
    )
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in record.notes)
    return f"""
<section class="pagina" data-source-url="{html.escape(record.canonical)}" data-page-type="{html.escape(record.page_type)}">
  <h1>{html.escape(record.title)}</h1>
  <div class="metadados">{''.join(meta_bits)}</div>
  <article>{''.join(body)}</article>
  <details><summary>Links internos ({len(record.internal_links)})</summary><ul>{internal}</ul></details>
  <details><summary>Links externos citados ({len(record.external_links)})</summary><ul>{external}</ul></details>
  <details><summary>Imagens referenciadas ({len(record.images)})</summary><ul>{images}</ul></details>
  <details><summary>Notas de extração</summary><ul>{notes}</ul></details>
</section>
"""


def html_document(title: str, sections: Iterable[str], notice: str = "") -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px/1.58 Georgia,serif;max-width:1040px;margin:0 auto;padding:28px;color:#1d2430;background:#fffdf7}}
a{{color:#0b5660}}.pagina{{padding:28px 0;border-bottom:3px solid #c69a3b}}.metadados{{background:#f7f0df;padding:12px 18px;border-left:5px solid #c69a3b}}article{{max-width:780px}}h1,h2,h3,h4,h5,h6{{line-height:1.2}}details{{margin:14px 0}}code{{word-break:break-all}}.aviso{{padding:14px;background:#0e1b2a;color:#fffdf7}}
</style></head><body><header><h1>{html.escape(title)}</h1>{('<p class="aviso">'+html.escape(notice)+'</p>') if notice else ''}</header>
{''.join(sections)}
</body></html>"""


def write_chunks(records: list[Record], prefix: str, title: str) -> list[Path]:
    paths: list[Path] = []
    current: list[tuple[Record, str]] = []
    current_size = 0
    part = 1

    def flush() -> None:
        nonlocal current, current_size, part
        if not current:
            return
        path = OUT / f"{prefix}_PARTE_{part:03d}.html"
        doc = html_document(f"{title} | Parte {part:03d}", [s for _, s in current])
        path.write_text(doc, encoding="utf-8")
        for rec, _ in current:
            rec.output_file = path.name
        paths.append(path)
        part += 1
        current, current_size = [], 0

    for rec in records:
        section = page_section(rec)
        size = len(section.encode("utf-8"))
        if current and current_size + size > MAX_CHUNK_BYTES:
            flush()
        current.append((rec, section))
        current_size += size
    flush()
    return paths


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"})

    seeds, sitemap_checked, sitemap_errors = sitemap_urls(session)
    seeds.update(normalize_url(x) for x in [
        ROOT, "/materias", "/comunidade", "/analises-diversas", "/livraria",
        "/contato", "/perfil", "/cursos", "/compromisso-nous-com-a-privacidade",
    ] if normalize_url(x))

    queue = deque(sorted(seeds))
    visited: set[str] = set()
    records: list[Record] = []
    failures: list[dict[str, object]] = []

    while queue and len(visited) < MAX_URLS:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        print(f"[{len(visited):03d}] {url}", flush=True)
        status, raw, method, fetch_notes = fetch_page(session, url)
        if not raw:
            failures.append({"url": url, "status": status, "notas": fetch_notes})
            continue

        soup = BeautifulSoup(raw, "lxml")
        title, description, author, published, canonical = metadata(soup, url)
        internal, external = extract_links(soup, url)
        images = extract_images(soup, url)
        notes = list(fetch_notes)
        clean_soup(soup, notes)
        root = choose_content_root(soup)
        # Em artigos, navegação/rodapé repetidos não fazem parte do corpo autoral.
        for tag in root.find_all(["nav", "footer"]):
            tag.decompose()
        blocks = extract_blocks(root)
        page_type = detect_type(url, soup, blocks)
        text = "\n".join(b["text"] for b in blocks)
        if len(text) < 80:
            notes.append("Texto extraído muito curto; revisão humana recomendada.")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        record = Record(
            url=url, canonical=canonical, title=title, page_type=page_type,
            status=status, author=author, published=published, description=description,
            text_sha256=digest, text_chars=len(text), internal_links=internal,
            external_links=external, images=images, blocks=blocks,
            source_method=method, notes=notes,
        )
        records.append(record)
        for link in internal:
            if link not in visited and len(visited) + len(queue) < MAX_URLS:
                queue.append(link)
        time.sleep(0.12)

    # Deduplicação por URL canônica e hash textual.
    deduped, seen_canon, seen_hash = [], set(), set()
    duplicates = []
    for rec in sorted(records, key=lambda r: (r.page_type, r.canonical)):
        if rec.canonical in seen_canon or (rec.text_sha256 in seen_hash and rec.text_chars > 300):
            duplicates.append({"url": rec.url, "canonical": rec.canonical, "hash": rec.text_sha256})
            continue
        seen_canon.add(rec.canonical)
        seen_hash.add(rec.text_sha256)
        deduped.append(rec)
    records = deduped

    institutional = [r for r in records if r.page_type != "artigo/ensaio"]
    articles = [r for r in records if r.page_type == "artigo/ensaio"]
    institutional_files = write_chunks(institutional, "01_PAGINAS_INTERNAS", "Páginas internas do Círculo de Estudos Nous")
    article_files = write_chunks(articles, "02_ARTIGOS_ENSAIOS", "Artigos e ensaios do Círculo de Estudos Nous")

    # Índice geral.
    rows = []
    for n, rec in enumerate(sorted(records, key=lambda r: (r.page_type, r.title.casefold())), 1):
        rows.append(
            f"<tr><td>{n}</td><td>{html.escape(rec.page_type)}</td><td>{html.escape(rec.title)}</td>"
            f"<td><a href=\"{html.escape(rec.canonical)}\">{html.escape(rec.canonical)}</a></td>"
            f"<td>{html.escape(rec.output_file)}</td><td>{rec.text_chars}</td></tr>"
        )
    index_section = f"""
<p>Este índice cobre somente páginas públicas internas que o rastreador conseguiu localizar e baixar. Destinos externos não foram visitados.</p>
<table border="1" cellpadding="6" cellspacing="0"><thead><tr><th>#</th><th>Tipo</th><th>Título</th><th>URL</th><th>Arquivo</th><th>Caracteres</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
"""
    (OUT / "00_INDICE_GERAL.html").write_text(html_document("Índice geral do corpus Nous", [index_section]), encoding="utf-8")

    # CSV de URLs.
    with (OUT / "03_MAPA_DE_URLS.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "tipo", "titulo", "url", "status", "arquivo", "autor", "data", "caracteres", "sha256", "metodo", "observacoes"])
        for n, rec in enumerate(sorted(records, key=lambda r: r.canonical), 1):
            w.writerow([n, rec.page_type, rec.title, rec.canonical, rec.status, rec.output_file, rec.author, rec.published, rec.text_chars, rec.text_sha256, rec.source_method, " | ".join(rec.notes)])

    report_data = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "raiz": ROOT,
        "sitemaps_verificados": sitemap_checked,
        "erros_de_sitemap": sitemap_errors,
        "urls_no_sitemap": len(seeds),
        "urls_visitadas": len(visited),
        "paginas_exportadas": len(records),
        "artigos_ensaios": len(articles),
        "paginas_internas": len(institutional),
        "falhas": failures,
        "duplicatas": duplicates,
        "limite_urls": MAX_URLS,
        "arquivos_institucionais": [p.name for p in institutional_files],
        "arquivos_artigos": [p.name for p in article_files],
        "observacao": "Imagens não foram baixadas; apenas URLs, alt text e legendas foram registradas. Links externos não foram visitados.",
    }
    report_sections = [
        f"<h2>Resumo</h2><ul><li>URLs visitadas: {len(visited)}</li><li>Páginas exportadas: {len(records)}</li><li>Artigos/ensaios: {len(articles)}</li><li>Páginas internas: {len(institutional)}</li><li>Falhas: {len(failures)}</li><li>Duplicatas removidas: {len(duplicates)}</li></ul>",
        "<h2>Sitemaps</h2><pre>" + html.escape(json.dumps({"verificados": sitemap_checked, "erros": sitemap_errors}, ensure_ascii=False, indent=2)) + "</pre>",
        "<h2>Falhas</h2><pre>" + html.escape(json.dumps(failures, ensure_ascii=False, indent=2)) + "</pre>",
        "<h2>Duplicatas</h2><pre>" + html.escape(json.dumps(duplicates, ensure_ascii=False, indent=2)) + "</pre>",
    ]
    (OUT / "04_RELATORIO_DE_COBERTURA.html").write_text(
        html_document("Relatório de cobertura do corpus Nous", report_sections,
                      "Não interprete ausência no pacote como inexistência se houver falhas listadas."),
        encoding="utf-8",
    )
    (OUT / "05_MANIFESTO.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "06_REGISTROS_COMPLETOS.json").write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "LEIA-ME.txt").write_text(
        "CORPUS WEB DO CÍRCULO DE ESTUDOS NOUS\n\n"
        "Arquivos HTML em UTF-8, divididos em partes pequenas para anexação em IA.\n"
        "O conteúdo foi extraído apenas do domínio circulodeestudosnous.com.\n"
        "Destinos externos não foram baixados. Imagens são referências por URL, alt e legenda.\n"
        "Consulte 04_RELATORIO_DE_COBERTURA.html antes de afirmar que a cobertura foi total.\n",
        encoding="utf-8",
    )

    zip_path = Path("CORPUS_WEB_CIRCULO_DE_ESTUDOS_NOUS.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                z.write(path, arcname=path.as_posix())
    print(json.dumps(report_data, ensure_ascii=False, indent=2))
    print(f"ARQUIVO_ZIP={zip_path.resolve()}")


if __name__ == "__main__":
    main()
