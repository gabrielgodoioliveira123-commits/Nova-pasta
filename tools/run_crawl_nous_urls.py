#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Executa o rastreador usando a lista explícita fornecida pelo proprietário."""
from pathlib import Path
import crawl_nous

URL_FILE = Path("data/urls_nous.txt")


def explicit_urls(_session):
    urls = set()
    ignored = []
    for raw in URL_FILE.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        normalized = crawl_nous.normalize_url(raw)
        if normalized:
            urls.add(normalized)
        else:
            ignored.append(raw)
    errors = [f"URL ignorada por não ser interna/válida: {u}" for u in ignored]
    return urls, [str(URL_FILE)], errors


crawl_nous.sitemap_urls = explicit_urls
crawl_nous.MAX_URLS = 500
crawl_nous.MAX_CHUNK_BYTES = 350_000
crawl_nous.main()
