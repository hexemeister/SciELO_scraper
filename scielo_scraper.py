#!/usr/bin/env python3
"""
scielo_scraper.py  v2.4
=======================
Extrai título, resumo e palavras-chave em português de artigos SciELO
a partir de um CSV com PIDs, usando duas fontes por ordem de prioridade:

  1. ArticleMeta REST API (ISIS-JSON)   →  extração direta e estruturada
  2. Fallback HTML scraping (scielo.br) →  multi-estratégia:
       a) Acessa a URL legacy e segue o redirect (automático via requests)
       b) Extrai meta tags: name=citation_* E property=og:*
       c) Extrai dados do corpo HTML (h1.article-title, div[data-anchor=Resumo]…)
       d) Se língua ≠ pt: segue link "Texto (Português)" e repete b)+c)
       e) Artigos AoP (PID com "005"): se a URL legacy retornou a home do
          periódico (sem dados), tenta a og:url da página

  Mesmo quando a API retorna dados parciais (ex: só resumo), o fallback HTML
  é ativado para tentar preencher os campos ainda ausentes.

  DEPENDÊNCIAS
  ------------
    pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli

UTILIZAÇÃO
----------
  python scielo_scraper.py [entrada.csv] [opções]
  (sem CSV: usa o sc_*.csv mais recente no diretório atual)

OPÇÕES
------
  --output-dir DIR   Pasta de saída (default: <nome_csv>_s_<timestamp>_<modo>/)
  --delay SEG        Delay mínimo entre requests (default: 1.5)
  --jitter SEG       Variação aleatória máxima do delay (default: 0.5)
  --retries N        Tentativas em erro transitório (default: 3)
  --timeout SEG      Timeout HTTP em segundos (default: 20)
  --workers N        Threads paralelas, 1=sequencial (default: 1, máx: 4)
  --checkpoint N     Salvar CSV a cada N artigos (default: 25). Use 1 para
                     salvar após cada artigo, 0 para salvar apenas no final.
  --resume           Retomar execução anterior (salta artigos já com sucesso)
  --no-resume        Ignorar resultados anteriores e recomeçar do zero
  --only-api         Usar apenas ArticleMeta API, sem fallback HTML
  --only-html        Usar apenas scraping HTML, sem ArticleMeta API
  --stats-report     Sem executar scraping: lê stats.json e imprime o relatório.
                     Procura em --output-dir (se informado) ou na pasta mais
                     recente <nome_csv>_s_*/. CSV opcional se --output-dir dado.
  --log-level LEVEL  DEBUG | INFO | WARNING | ERROR (default: INFO)
  --collection COD   Coleção SciELO: scl=Brasil, arg=Argentina… (default: scl)
  --list-collections Listar todas as coleções SciELO disponíveis e sair
  --version          Mostrar versão e sair
  -h, --help, -?     Mostrar esta mensagem de ajuda e sair

EXEMPLOS
--------
  python scielo_scraper.py lista.csv
  python scielo_scraper.py lista.csv --resume
  python scielo_scraper.py lista.csv --only-api --delay 2.0
  python scielo_scraper.py lista.csv --only-html --workers 2
  python scielo_scraper.py lista.csv --no-resume --log-level DEBUG
  python scielo_scraper.py lista.csv --stats-report --output-dir resultados/
"""

__version__ = "2.5"

import argparse
import html as html_mod
import json
import logging
import random
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

# ── Dependências ──────────────────────────────────────────────────────────────
_obrigatorios = {"requests": "requests", "bs4": "beautifulsoup4 lxml", "pandas": "pandas"}
_opcionais    = {"tqdm": "tqdm", "wakepy": "wakepy", "brotli": "brotli"}
_faltando = []
for _mod, _pkg in {**_obrigatorios, **_opcionais}.items():
    try:
        __import__(_mod)
    except ImportError:
        _faltando.append(_pkg)
if _faltando:
    sys.exit(
        "❌  Pacotes necessários não encontrados. Instale com:\n"
        f"    uv pip install {' '.join(_faltando)}"
    )

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import pandas as pd

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import wakepy
    HAS_WAKEPY = True
except ImportError:
    HAS_WAKEPY = False

# ── Constantes ────────────────────────────────────────────────────────────────
ARTICLEMETA_URL = "http://articlemeta.scielo.org/api/v1/article"
SCIELO_BASE     = "https://www.scielo.br"
SCIELO_HTML_URL = f"{SCIELO_BASE}/scielo.php"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "SciELOBot/1.0 (+https://scielo.org/about/)",
]

OUTPUT_COLUMNS = [
    "ID", "Title", "Author(s)", "Source", "Journal",
    "Language(s)", "Publication year",
    "PID_limpo", "URL_PT",
    "Titulo_PT", "Resumo_PT", "Palavras_Chave_PT",
    "status", "fonte_extracao", "url_acedida",
]

BLACKLIST_COLS = {"Fulltext URL ", "Fulltext URL"}

# ── Logging ───────────────────────────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    C = {
        logging.DEBUG:    "\033[36m",
        logging.INFO:     "\033[32m",
        logging.WARNING:  "\033[33m",
        logging.ERROR:    "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        c  = self.C.get(record.levelno, self.RESET)
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        return f"{ts}  {c}{record.levelname:<8}{self.RESET}  {record.getMessage()}"


def setup_logging(log_path: Path, level: str = "INFO", append: bool = False) -> logging.Logger:
    logger = logging.getLogger("scielo")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    if hasattr(ch.stream, "reconfigure"):
        ch.stream.reconfigure(encoding="utf-8", errors="replace")
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)
    fh = logging.FileHandler(log_path, mode="a" if append else "w", encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    return logger


# ── Utilitários ───────────────────────────────────────────────────────────────
def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3, backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"], raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "Accept":          "application/json, text/html, */*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    })
    return session


def ua() -> str:
    return random.choice(USER_AGENTS)


def http_get(url, session, timeout, params=None, logger=None, label=""):
    """GET com log da URL completa (após params). Lança exceção em erro HTTP."""
    full_url = requests.Request("GET", url, params=params).prepare().url
    if logger and label:
        logger.info(f"    🌐 [{label}]: {full_url}")
    resp = session.get(
        url, params=params,
        headers={"User-Agent": ua(), "Referer": SCIELO_BASE + "/"},
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp


def clean_pid(raw: str) -> Optional[str]:
    s = str(raw).strip().strip('"').strip("'").strip()
    s = re.sub(r"-(scl|oai)$", "", s, flags=re.IGNORECASE)
    if re.match(r"^[A-Z]\d{4}-\d{3}[\dA-Z]\d{13}$", s):
        return s
    return None


def is_aop(pid: str) -> bool:
    """PIDs ahead-of-print têm '005' na posição 14-16 (após ISSN+ano)."""
    return len(pid) == 23 and pid[14:17] == "005"


def is_article_page(soup: BeautifulSoup) -> bool:
    """Verifica se a página é de um artigo (não a homepage do periódico)."""
    return bool(
        soup.find("meta", {"name": "citation_title"}) or
        soup.find("meta", {"property": "og:title"}) and
            soup.find("div", {"data-anchor": re.compile(r"Resumo|Abstract", re.I)}) or
        soup.find("article", {"id": "articleText"}) or
        soup.find("div", {"data-anchor": "Resumo"})
    )


def humanize_seconds(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


# ── ISIS-JSON (ArticleMeta) ───────────────────────────────────────────────────
def _unescape(text: str) -> str:
    return html_mod.unescape(text).strip()


def extract_pt_from_isis(isis: dict) -> dict:
    art = isis.get("article", {})
    orig_lang = (art.get("v40") or [{}])[0].get("_", "").lower()

    titulo = None
    for e in art.get("v12", []):
        if e.get("l", "").lower() == "pt" and e.get("_", "").strip():
            titulo = _unescape(e["_"]); break
    if not titulo and orig_lang == "pt":
        for e in art.get("v12", []):
            if e.get("_", "").strip():
                titulo = _unescape(e["_"]); break

    resumo = None
    for e in art.get("v83", []):
        if e.get("l", "").lower() == "pt" and e.get("a", "").strip():
            text = _unescape(e["a"])
            resumo = re.sub(r"^resumo\s+", "", text, flags=re.IGNORECASE).strip()
            break
    if not resumo and orig_lang == "pt":
        for e in art.get("v83", []):
            if e.get("a", "").strip():
                text = _unescape(e["a"])
                resumo = re.sub(r"^resumo\s+", "", text, flags=re.IGNORECASE).strip()
                break

    kws = [_unescape(e["k"]) for e in art.get("v85", [])
           if e.get("l", "").lower() == "pt" and e.get("k", "").strip()]
    if not kws and orig_lang == "pt":
        kws = [_unescape(e["k"]) for e in art.get("v85", []) if e.get("k", "").strip()]

    url_pt = (
        isis.get("fulltexts", {}).get("html", {}).get("pt")
        or f"{SCIELO_HTML_URL}?script=sci_arttext&pid={art.get('code','')}&tlng=pt"
    )
    return {
        "titulo": titulo, "resumo": resumo,
        "palavras_chave": "; ".join(kws) if kws else None,
        "url_pt": url_pt,
    }


def fetch_articlemeta(pid, collection, session, timeout, logger):
    resp = http_get(
        ARTICLEMETA_URL, session, timeout,
        params={"code": pid, "collection": collection, "format": "json"},
        logger=logger, label="ArticleMeta API",
    )
    isis = resp.json()
    if not isinstance(isis, dict) or "article" not in isis:
        return None
    result = extract_pt_from_isis(isis)
    if any(result[k] for k in ("titulo", "resumo", "palavras_chave")):
        return result
    return None


# ── HTML parsing ──────────────────────────────────────────────────────────────
def _parse_meta_tags(soup: BeautifulSoup) -> dict:
    """
    Extrai metadados de meta tags — lê AMBOS os atributos name= e property=.
    Prioridade: citation_* (name=) > og:* (property=) para título e resumo.
    """
    def meta_name(name):
        tag = soup.find("meta", {"name": name})
        return tag["content"].strip() if tag and tag.get("content") else None

    def meta_prop(prop):
        tag = soup.find("meta", {"property": prop})
        return tag["content"].strip() if tag and tag.get("content") else None

    lang = (meta_name("citation_language") or "").lower()

    # Título: citation_title primeiro; og:title como fallback
    titulo = meta_name("citation_title") or meta_prop("og:title")

    # Resumo: citation_abstract primeiro; og:description como fallback
    resumo_raw = meta_name("citation_abstract") or meta_prop("og:description")
    resumo = None
    if resumo_raw:
        resumo = re.sub(r"^(resumo|abstract)\s*[:\-]?\s*", "", resumo_raw,
                        flags=re.IGNORECASE).strip()
        if len(resumo) < 30:
            resumo = None   # og:description pode ser apenas um snippet curto

    kws_raw = [t["content"].strip()
               for t in soup.find_all("meta", {"name": "citation_keywords"})
               if t.get("content")]

    og_url_tag = soup.find("meta", {"property": "og:url"})
    og_url = og_url_tag["content"].strip() if og_url_tag and og_url_tag.get("content") else None

    return {
        "titulo":         titulo,
        "resumo":         resumo,
        "palavras_chave": "; ".join(kws_raw) if kws_raw else None,
        "lang":           lang,
        "og_url":         og_url,
    }


def _parse_html_body(soup: BeautifulSoup) -> dict:
    """Extrai título, resumo e keywords do corpo HTML."""
    titulo = None
    resumo = None
    kws    = None

    # Título: h1.article-title — remover sub-elementos (img, a, span)
    for sel in [
        'h1.article-title[lang="pt"]',
        "h1.article-title",
        'p.title[lang="pt"]',
        "h2.articleTitle",
    ]:
        tag = soup.select_one(sel)
        if tag:
            for child in tag.find_all(["img", "a", "span"]):
                child.decompose()
            t = tag.get_text(" ", strip=True)
            if len(t) > 5:
                titulo = t; break

    # Secção do Resumo
    resumo_div = (
        soup.find("div", {"data-anchor": "Resumo"}) or
        soup.find("div", class_=re.compile(r"articleSection--resumo")) or
        soup.find("section", {"lang": "pt"}) or
        soup.find("div", {"id": "abst-pt"})
    )
    if resumo_div:
        # Keywords antes de limpar o div
        kw_tag = resumo_div.find(string=re.compile(r"Palavras[- ]chave", re.IGNORECASE))
        if kw_tag:
            full = kw_tag.parent.get_text(" ", strip=True)
            km = re.search(r"Palavras[- ]chave[:\s]+(.*)", full, re.IGNORECASE)
            if km:
                kws = re.sub(r"\s+", " ", km.group(1)).strip()

        # Limpar headings e parágrafos de keywords
        for tag in resumo_div.find_all(["h2","h3","h4","h5","strong","b"]):
            if any(w in tag.get_text(strip=True).lower()
                   for w in ("resumo","abstract","palavras","keywords")):
                tag.decompose()
        for p in resumo_div.find_all("p"):
            if re.search(r"palavras[- ]chave", p.get_text(), re.IGNORECASE):
                p.decompose()

        raw = re.sub(r"\s+", " ", resumo_div.get_text(" ", strip=True)).strip()
        if len(raw) > 30:
            resumo = raw

    return {"titulo": titulo, "resumo": resumo, "palavras_chave": kws}


def _find_pt_link(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Procura o link para a versão em Português na página."""
    for a in soup.find_all("a", href=True):
        if re.search(r"Texto\s*\(Português\)", a.get_text(strip=True), re.IGNORECASE):
            return urljoin(base_url, a["href"])
    for a in soup.find_all("a", href=re.compile(r"lang=pt", re.IGNORECASE)):
        href = a["href"]
        if "format=pdf" not in href and "abstract" not in href:
            return urljoin(base_url, href)
    return None


# ── Fallback HTML ─────────────────────────────────────────────────────────────
def fetch_html(pid, session, timeout, logger, need_t, need_r, need_k):
    """
    Estratégia de scraping HTML em múltiplas etapas.

    Etapa 1: acessa a URL legacy (?script=sci_arttext&pid=PID&lang=pt).
             requests segue redirects automaticamente → URL final pode já ser
             a URL canônica nova do SciELO (/j/<journal>/a/<hash>/?lang=pt).
    Etapa 2: se a página acessada É um artigo → extrai dados (meta + body).
             Loga por campo: fonte exata (meta_tags ou html_body) e URL.
    Etapa 3: se língua ≠ pt → segue link "Texto (Português)" e repete.
    Etapa 4: apenas para AoP sem dados ainda: se a URL legacy retornou a home
             do periódico, tenta acessar diretamente a og:url da página.

    Nota: requer o pacote 'brotli' instalado para descomprimir respostas
    Content-Encoding: br do servidor SciELO (CDN BunnyCDN/Varnish).
    Sem ele, o body chega corrompido e is_article_page() retorna False
    mesmo para páginas de artigo válidas.
    """
    url_legacy = f"{SCIELO_HTML_URL}?script=sci_arttext&pid={pid}&lang=pt"
    urls_tried = []
    strategies = []
    result     = {"titulo": None, "resumo": None, "palavras_chave": None, "url_pt": url_legacy}

    def try_page(url: str, label: str):
        """Acessa a URL, retorna (meta, body, soup, final_url)."""
        logger.info(f"    🌐 [{label}]: {url}")
        urls_tried.append(url)
        resp = http_get(url, session, timeout, logger=None)
        final_url = resp.url          # URL real após redirect
        soup      = BeautifulSoup(resp.text, "lxml")
        meta      = _parse_meta_tags(soup)
        body      = _parse_html_body(soup)
        return meta, body, soup, final_url

    def apply_missing(meta, body, label_pfx, url):
        """Preenche os campos ainda vazios. Loga campo a campo."""
        applied = False
        if need_t and not result["titulo"]:
            v = meta.get("titulo") or body.get("titulo")
            if v:
                result["titulo"] = v
                src = "meta_tags" if meta.get("titulo") else "html_body"
                strategies.append(f"Titulo_PT←{label_pfx}_{src}")
                logger.info(f"    ✓ Titulo_PT  via [{label_pfx}_{src}]  url={url}")
                applied = True
            else:
                logger.info(f"    ✗ Titulo_PT  não encontrado em [{label_pfx}]  url={url}")
        if need_r and not result["resumo"]:
            v = meta.get("resumo") or body.get("resumo")
            if v:
                result["resumo"] = v
                src = "meta_tags" if meta.get("resumo") else "html_body"
                strategies.append(f"Resumo_PT←{label_pfx}_{src}")
                logger.info(f"    ✓ Resumo_PT  via [{label_pfx}_{src}]  url={url}")
                applied = True
            else:
                logger.info(f"    ✗ Resumo_PT  não encontrado em [{label_pfx}]  url={url}")
        if need_k and not result["palavras_chave"]:
            v = meta.get("palavras_chave") or body.get("palavras_chave")
            if v:
                result["palavras_chave"] = v
                src = "meta_tags" if meta.get("palavras_chave") else "html_body"
                strategies.append(f"Palavras_Chave_PT←{label_pfx}_{src}")
                logger.info(f"    ✓ Palavras_Chave_PT  via [{label_pfx}_{src}]  url={url}")
                applied = True
            else:
                logger.info(f"    ✗ Palavras_Chave_PT  não encontrado em [{label_pfx}]  url={url}")
        return applied

    def still_missing():
        return (
            (need_t and not result["titulo"]) or
            (need_r and not result["resumo"]) or
            (need_k and not result["palavras_chave"])
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Etapas 1+2: URL legacy → segue redirect → parse
    # ─────────────────────────────────────────────────────────────────────────
    try:
        meta_1, body_1, soup_1, final_url_1 = try_page(url_legacy, "pag1_legacy")
    except Exception as e:
        logger.warning(f"    ❌ Erro ao acessar URL legacy [{pid}]: {type(e).__name__}: {e}")
        return None

    lang_orig     = meta_1.get("lang", "").lower()
    page_is_art   = is_article_page(soup_1)
    redirected    = (final_url_1 != url_legacy)

    if redirected:
        logger.info(f"    🔀 Redirect → {final_url_1}")
        urls_tried[-1] = final_url_1   # substituir URL registrada pela final

    if page_is_art:
        # ── A página acessada (redirect ou não) É um artigo → extrair dados ──
        apply_missing(meta_1, body_1, "pag1", final_url_1 if redirected else url_legacy)
        result["url_pt"] = final_url_1 if redirected else url_legacy
    else:
        # ── A página não é um artigo (ex: home do periódico ou 404) ──────────
        logger.info(f"    ✗ Página acessada não é um artigo (home do periódico ou 404)")

        # Etapa 4 (AoP): tentar og:url da página
        if is_aop(pid) and still_missing():
            og_url = meta_1.get("og_url")
            if og_url and og_url.rstrip("/") != url_legacy.rstrip("/"):
                # Garantir lang=pt
                if "lang=" not in og_url:
                    og_url = og_url.rstrip("/") + "?lang=pt"
                else:
                    og_url = re.sub(r"lang=(en|es)", "lang=pt", og_url)
                logger.info(f"    🔀 AoP: tentando og:url → {og_url}")
                try:
                    meta_og, body_og, soup_og, _ = try_page(og_url, "pag_aop_ogurl")
                    if is_article_page(soup_og):
                        lang_orig = meta_og.get("lang", lang_orig).lower()
                        apply_missing(meta_og, body_og, "pag_aop_ogurl", og_url)
                        soup_1 = soup_og
                    else:
                        logger.info(f"    ✗ og:url também não é artigo: {og_url}")
                except Exception as e:
                    logger.warning(f"    ⚠️  og:url erro: {type(e).__name__}: {e}")
            else:
                logger.info(f"    ✗ AoP: sem og:url útil na página home")

    # ─────────────────────────────────────────────────────────────────────────
    # Etapa 3: se língua ≠ pt → seguir link "Texto (Português)"
    # ─────────────────────────────────────────────────────────────────────────
    if still_missing() and lang_orig and lang_orig != "pt":
        pt_link = _find_pt_link(soup_1, SCIELO_BASE)
        if pt_link and pt_link.rstrip("/") not in [u.rstrip("/") for u in urls_tried]:
            logger.info(f"    🔀 Língua='{lang_orig}' → seguindo link PT: {pt_link}")
            try:
                meta_pt, body_pt, _, _ = try_page(pt_link, "pag_pt")
                apply_missing(meta_pt, body_pt, "pag_pt", pt_link)
            except Exception as e:
                logger.warning(f"    ⚠️  pag_pt erro: {type(e).__name__}: {e}")
        elif not pt_link:
            logger.info(f"    ✗ Link 'Texto (Português)' não encontrado")

    # ─────────────────────────────────────────────────────────────────────────
    if not any(result[k] for k in ("titulo", "resumo", "palavras_chave")):
        logger.info(f"    ✗ HTML fallback: nenhum dado encontrado após todas as etapas")
        return None

    result["url_acedida"] = " → ".join(urls_tried)
    result["estrategia"]  = " | ".join(strategies) if strategies else "html_fallback_sem_dados"
    return result


# ── Processar um artigo ───────────────────────────────────────────────────────
def process_article(row, csv_line, session, collection, delay, jitter, timeout,
                    logger, only_api=False, only_html=False):
    raw_id = row.get("ID", "")
    pid    = clean_pid(raw_id)

    out = {col: row.get(col, "") for col in OUTPUT_COLUMNS if col in row}
    for col in OUTPUT_COLUMNS:
        out.setdefault(col, "")

    out["PID_limpo"]         = pid or raw_id
    out["URL_PT"]            = f"{SCIELO_HTML_URL}?script=sci_arttext&pid={pid or raw_id}&tlng=pt"
    out["Titulo_PT"]         = ""
    out["Resumo_PT"]         = ""
    out["Palavras_Chave_PT"] = ""
    out["status"]            = "erro_pid_invalido"
    out["fonte_extracao"]    = ""
    out["url_acedida"]       = ""

    logger.info("─" * 62)
    logger.info(f"Linha CSV {csv_line} | PID: '{pid or raw_id}'"
                + (" [AoP]" if pid and is_aop(pid) else ""))

    if pid is None:
        logger.warning(f"  🔴 PID inválido: {raw_id!r}")
        return out

    titulo_val = ""
    resumo_val = ""
    kws_val    = ""
    url_ac     = ""
    fontes     = []

    # ── 1. ArticleMeta API ────────────────────────────────────────────────────
    if not only_html:
        try:
            api_result = fetch_articlemeta(pid, collection, session, timeout, logger)
            if api_result:
                for field, key, tag in [
                    ("Titulo_PT",         "titulo",         "T"),
                    ("Resumo_PT",         "resumo",         "R"),
                    ("Palavras_Chave_PT", "palavras_chave", "K"),
                ]:
                    val = api_result.get(key)
                    if val:
                        if field == "Titulo_PT":           titulo_val = val
                        elif field == "Resumo_PT":          resumo_val = val
                        elif field == "Palavras_Chave_PT":  kws_val    = val
                        fontes.append(f"articlemeta_isis[{tag}]")
                        logger.info(f"  ✓ {field}  via ArticleMeta ISIS")
                    else:
                        logger.info(f"  ✗ {field}  não encontrado via ArticleMeta ISIS")
                url_ac = f"{ARTICLEMETA_URL}?code={pid}&collection={collection}&format=json"
                if api_result.get("url_pt"):
                    out["URL_PT"] = api_result["url_pt"]
            else:
                logger.info(f"  ✗ ArticleMeta ISIS: sem dados PT para {pid}")
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            logger.warning(f"  ❌ ArticleMeta HTTP {code}: {e}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"  ❌ ArticleMeta: sem conexão (ConnectionError)")
        except requests.exceptions.Timeout:
            logger.warning(f"  ❌ ArticleMeta: timeout")
        except Exception as e:
            logger.warning(f"  ❌ ArticleMeta: {type(e).__name__}: {e}")

    # ── 2. HTML Fallback ──────────────────────────────────────────────────────
    need_t = not titulo_val
    need_r = not resumo_val
    need_k = not kws_val

    if (not only_api) and (need_t or need_r or need_k):
        missing = (["T"] if need_t else []) + (["R"] if need_r else []) + (["K"] if need_k else [])
        logger.info(f"  → HTML fallback para: [{', '.join(missing)}]")
        try:
            html_res = fetch_html(pid, session, timeout, logger, need_t, need_r, need_k)
            if html_res:
                if need_t and html_res.get("titulo"):
                    titulo_val = html_res["titulo"]
                if need_r and html_res.get("resumo"):
                    resumo_val = html_res["resumo"]
                if need_k and html_res.get("palavras_chave"):
                    kws_val = html_res["palavras_chave"]
                if html_res.get("estrategia"):
                    fontes.append(html_res["estrategia"])
                if html_res.get("url_acedida"):
                    url_ac = (url_ac + " | " + html_res["url_acedida"]).strip(" | ")
        except Exception as e:
            logger.warning(f"  ❌ HTML fallback: {type(e).__name__}: {e}")

    # ── Resultado ─────────────────────────────────────────────────────────────
    out["Titulo_PT"]         = titulo_val
    out["Resumo_PT"]         = resumo_val
    out["Palavras_Chave_PT"] = kws_val
    out["fonte_extracao"]    = " | ".join(fontes) if fontes else ""
    out["url_acedida"]       = url_ac

    has_t = bool(titulo_val)
    has_r = bool(resumo_val)
    has_k = bool(kws_val)

    if has_t and has_r and has_k:
        out["status"] = "ok_completo"
    elif has_t or has_r or has_k:
        out["status"] = "ok_parcial"
    elif url_ac:
        out["status"] = "nada_encontrado"
    else:
        out["status"] = "erro_extracao"

    icons = {
        "ok_completo":       "✅",
        "ok_parcial":        "🟡",
        "nada_encontrado":   "⚠️ ",
        "erro_extracao":     "❌",
        "erro_pid_invalido": "🔴",
    }
    logger.info(f"  {icons.get(out['status'],'❓')} Resultado: "
                f"T:{'✓' if has_t else '✗'}  R:{'✓' if has_r else '✗'}  "
                f"KW:{'✓' if has_k else '✗'}  [{out['status']}]")
    if fontes:
        logger.info(f"  fonte : {out['fonte_extracao']}")
    if url_ac:
        logger.info(f"  url   : {url_ac}")

    time.sleep(max(0.2, delay + random.uniform(-jitter, jitter)))
    return out


# ── CSV ───────────────────────────────────────────────────────────────────────
def validate_csv(path: Path, logger):
    logger.info(f"{'─'*62}")
    logger.info(f"Validando CSV: {path.name}")
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as e:
        logger.error(f"Erro ao ler CSV: {e}")
        return False, []
    df.columns = [c.strip() for c in df.columns]
    if "ID" not in df.columns:
        logger.error("Coluna 'ID' não encontrada")
        return False, []
    logger.info(f"  Linhas  : {len(df)}")
    logger.info(f"  Colunas : {list(df.columns)}")
    bad = [(i+2, r["ID"]) for i, r in df.iterrows() if clean_pid(r["ID"]) is None]
    if bad:
        logger.warning(f"  PIDs inválidos ({len(bad)}): {bad[:5]}{'...' if len(bad)>5 else ''}")
    else:
        logger.info(f"  Todos os {len(df)} PIDs são válidos ✓")
    logger.info(f"{'─'*62}")
    return True, df.to_dict("records")


def save_csv(rows: list, path: Path, logger):
    if not rows:
        return
    cols_in = list(rows[0].keys())
    final   = [c for c in OUTPUT_COLUMNS if c in cols_in]
    for c in cols_in:
        if c not in final and c not in BLACKLIST_COLS:
            final.insert(final.index("PID_limpo"), c)
    try:
        df = pd.DataFrame(rows)
        for c in final:
            if c not in df.columns:
                df[c] = ""
        for b in BLACKLIST_COLS:
            if b in df.columns:
                df.drop(columns=[b], inplace=True)
        df[final].to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as e:
        logger.error(f"Erro ao salvar CSV: {e}")


def load_done(result_path: Path, logger) -> dict:
    if not result_path.exists():
        return {}
    try:
        df = pd.read_csv(result_path, dtype=str, keep_default_na=False)
        done = {}
        for _, row in df.iterrows():
            pid = clean_pid(row.get("ID", ""))
            st  = row.get("status", "")
            if pid and st in ("ok_completo", "ok_parcial"):
                done[pid] = row.to_dict()
        logger.info(f"  Resume: {len(done)} artigos com sucesso carregados")
        return done
    except Exception as e:
        logger.warning(f"  Não foi possível carregar resultado anterior: {e}")
        return {}


# ── Stats ─────────────────────────────────────────────────────────────────────
def compute_stats(results: list, elapsed: float, version: str, mode_flags: dict) -> dict:
    total  = len(results)
    counts = {}
    fonte_counts = {}
    for r in results:
        s = r.get("status", "?")
        counts[s] = counts.get(s, 0) + 1
        f_raw = r.get("fonte_extracao", "") or "sem_fonte"
        if "articlemeta_isis" in f_raw and any(
            x in f_raw for x in ("pag1","pag_pt","pag_aop","pag_canonical")
        ):
            f_cat = "api+html_fallback"
        elif "articlemeta_isis" in f_raw:
            f_cat = "articlemeta_isis"
        elif f_raw == "sem_fonte":
            f_cat = "sem_fonte"
        else:
            f_cat = "html_fallback"
        fonte_counts[f_cat] = fonte_counts.get(f_cat, 0) + 1

    def pct(n):
        return f"{n/total*100:.1f}%" if total else "0%"

    ok_c = counts.get("ok_completo", 0)
    ok_p = counts.get("ok_parcial",  0)

    return {
        "versao_script":       version,
        "timestamp":           datetime.now().isoformat(),
        "modo":                mode_flags,
        "total":               total,
        "ok_completo":         ok_c,
        "ok_completo_pct":     pct(ok_c),
        "ok_parcial":          ok_p,
        "ok_parcial_pct":      pct(ok_p),
        "sucesso_total":       ok_c + ok_p,
        "sucesso_total_pct":   pct(ok_c + ok_p),
        "nada_encontrado":     counts.get("nada_encontrado",   0),
        "nada_encontrado_pct": pct(counts.get("nada_encontrado", 0)),
        "erro_extracao":       counts.get("erro_extracao",     0),
        "erro_extracao_pct":   pct(counts.get("erro_extracao", 0)),
        "erro_pid_invalido":   counts.get("erro_pid_invalido", 0),
        "erro_pid_pct":        pct(counts.get("erro_pid_invalido", 0)),
        "elapsed_seconds":     round(elapsed, 2),
        "elapsed_humanizado":  humanize_seconds(elapsed),
        "avg_per_article_s":   round(elapsed / total, 2) if total else 0,
        "por_status":          {k: {"n": v, "pct": pct(v)}
                                for k, v in sorted(counts.items(), key=lambda x: -x[1])},
        "por_fonte_extracao":  {k: {"n": v, "pct": pct(v)}
                                for k, v in sorted(fonte_counts.items(), key=lambda x: -x[1])},
    }


def format_stats_report(stats: dict) -> str:
    """Relatório idêntico ao que aparece no log — retorna string."""
    L = []
    L.append("=" * 62)
    L.append(f"  ESTATÍSTICAS FINAIS  (script v{stats['versao_script']})")
    if stats.get("modo"):
        L.append(f"  Modo: {stats['modo']}")
    L.append(f"  Timestamp: {stats.get('timestamp','')}")
    L.append("=" * 62)
    pairs = [
        ("Total processados",    stats["total"]),
        ("✅  ok_completo",       f"{stats['ok_completo']}  ({stats['ok_completo_pct']})"),
        ("🟡  ok_parcial",        f"{stats['ok_parcial']}  ({stats['ok_parcial_pct']})"),
        ("✅+🟡 sucesso total",   f"{stats['sucesso_total']}  ({stats['sucesso_total_pct']})"),
        ("⚠️   nada_encontrado",  f"{stats['nada_encontrado']}  ({stats['nada_encontrado_pct']})"),
        ("❌  erro_extracao",     f"{stats['erro_extracao']}  ({stats['erro_extracao_pct']})"),
        ("🔴  erro_pid_invalido", f"{stats['erro_pid_invalido']}  ({stats['erro_pid_pct']})"),
        ("⏱   Tempo total",       f"{stats['elapsed_seconds']}s  ({stats['elapsed_humanizado']})"),
        ("⏱   Média por artigo",  f"{stats['avg_per_article_s']}s"),
    ]
    for k, v in pairs:
        L.append(f"    {k:<32}: {v}")
    L.append("─" * 62)
    L.append("  Por fonte de extração:")
    for k, v in stats["por_fonte_extracao"].items():
        L.append(f"    {k:<40}: {v['n']}  ({v['pct']})")
    L.append("─" * 62)
    L.append("  Por status:")
    for k, v in stats["por_status"].items():
        L.append(f"    {k:<40}: {v['n']}  ({v['pct']})")
    L.append("=" * 62)
    return "\n".join(L)


def log_stats(stats: dict, logger):
    for line in format_stats_report(stats).splitlines():
        logger.info(line)


# ── Rastreabilidade ───────────────────────────────────────────────────────────
def _origem(args) -> dict:
    """Reconstrói o comando CLI que gerou este JSON para rastreabilidade."""
    import sys
    cmd = ["uv", "run", "python", "scielo_scraper.py"]
    if args.input_csv:
        cmd.append(str(args.input_csv))
    if getattr(args, "only_api", False):
        cmd.append("--only-api")
    if getattr(args, "only_html", False):
        cmd.append("--only-html")
    if getattr(args, "output_dir", None):
        cmd += ["--output-dir", str(args.output_dir)]
    if args.collection != "scl":
        cmd += ["--collection", args.collection]
    if args.workers != 1:
        cmd += ["--workers", str(args.workers)]
    if args.delay != 1.5:
        cmd += ["--delay", str(args.delay)]
    if args.checkpoint != 25:
        cmd += ["--checkpoint", str(args.checkpoint)]
    if getattr(args, "no_resume", False):
        cmd.append("--no-resume")
    return {
        "comando": " ".join(cmd),
        "argv":    sys.argv[1:],
        "cwd":     str(Path(".").resolve()),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=f"SciELO Scraper v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        add_help=False,
    )
    ap.add_argument("-h", "--help", "-?", action="help",
        help="Mostrar esta mensagem de ajuda e sair")
    ap.add_argument("input_csv", nargs="?", default=None,
        help="CSV com coluna 'ID' (PIDs SciELO)")
    ap.add_argument("--output-dir",   default=None,   metavar="DIR",
        help="Pasta de saída (também usada por --stats-report para localizar stats.json)")
    ap.add_argument("--delay",        type=float, default=1.5,  metavar="SEG")
    ap.add_argument("--jitter",       type=float, default=0.5,  metavar="SEG")
    ap.add_argument("--retries",      type=int,   default=3,    metavar="N")
    ap.add_argument("--timeout",      type=float, default=20.0, metavar="SEG")
    ap.add_argument("--workers",      type=int,   default=1,    metavar="N")
    ap.add_argument("--checkpoint",   type=int,   default=25,   metavar="N",
        help="Salvar CSV a cada N artigos processados (default: 25). "
             "Use 1 para salvar após cada artigo, 0 para salvar apenas no final.")
    ap.add_argument("--resume",       action="store_true")
    ap.add_argument("--no-resume",    action="store_true")
    ap.add_argument("--no-clean",     action="store_true",
        help="Não remover pastas incompletas (sem resultado.csv) — apenas avisar")
    ap.add_argument("--only-api",     action="store_true",
        help="Usar apenas ArticleMeta API (sem HTML)")
    ap.add_argument("--only-html",    action="store_true",
        help="Usar apenas scraping HTML (sem API)")
    ap.add_argument("--stats-report", action="store_true",
        help="Apenas imprimir stats.json formatado (não executa scraping). "
             "Requer --output-dir com stats.json existente.")
    ap.add_argument("--dry-run", action="store_true",
        help="Mostra CSV de entrada, pasta de saída e parâmetros sem fazer requisições nem gravar nada")
    ap.add_argument("--log-level",    default="INFO", metavar="LEVEL",
        choices=["DEBUG","INFO","WARNING","ERROR"])
    ap.add_argument("--collection",       default="scl",  metavar="COD")
    ap.add_argument("--list-collections", action="store_true",
        help="Listar coleções SciELO disponíveis (via ArticleMeta API) e sair.")
    ap.add_argument("--version", action="version", version=f"scielo_scraper v{__version__}")
    args = ap.parse_args()

    # ── Modo --list-collections ───────────────────────────────────────────────
    if args.list_collections:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        url = "http://articlemeta.scielo.org/api/v1/collection/identifiers/"
        try:
            r = requests.get(url, headers={"User-Agent": ua()}, timeout=15)
            r.raise_for_status()
            cols = r.json()
        except Exception as e:
            sys.exit(f"❌  Erro ao consultar ArticleMeta: {e}")

        active   = [c for c in cols if c.get("is_active")]
        inactive = [c for c in cols if not c.get("is_active")]

        def print_cols(lst):
            for c in sorted(lst, key=lambda x: x.get("code", "")):
                name = (c.get("name") or {}).get("pt") or c.get("original_name", "")
                domain = c.get("domain", "")
                docs   = c.get("document_count") or "?"
                print(f"  {c['code']:<6}  {name:<30}  {domain:<35}  {str(docs):>7} docs")

        print(f"\n{'='*62}")
        print(f"  Coleções SciELO disponíveis  ({len(cols)} total)")
        print(f"{'='*62}")
        print(f"\n  {'COD':<6}  {'Nome':<30}  {'Domínio':<35}  {'Artigos':>7}")
        print(f"  {'-'*6}  {'-'*30}  {'-'*35}  {'-'*7}")
        print(f"\n  Ativas ({len(active)}):")
        print_cols(active)
        if inactive:
            print(f"\n  Inativas ({len(inactive)}):")
            print_cols(inactive)
        print(f"\n  Use --collection COD para selecionar. Ex: --collection scl")
        print(f"{'='*62}\n")
        return

    # ── Modo --stats-report: apenas ler e imprimir, sem scraping ──────────────
    if args.stats_report:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        # Procurar stats.json na pasta indicada ou na mais recente
        if not args.input_csv and not args.output_dir:
            sys.exit("❌  --stats-report requer o CSV de entrada ou --output-dir.")
        input_path = Path(args.input_csv).resolve() if args.input_csv else Path(".")
        base_name  = input_path.stem

        search_dirs = []
        if args.output_dir:
            search_dirs.append(Path(args.output_dir))
        # Pasta mais recente com o mesmo nome base
        if input_path.parent.exists():
            candidates = sorted(
                [d for d in input_path.parent.iterdir()
                 if d.is_dir() and d.name.startswith(base_name + "_")],
                reverse=True,
            )
            search_dirs.extend(candidates)

        stats_file = None
        for d in search_dirs:
            candidate = d / "stats.json"
            if candidate.exists():
                stats_file = candidate
                break

        if not stats_file:
            print(f"❌  stats.json não encontrado. Use --output-dir para indicar a pasta.",
                  file=sys.stderr)
            sys.exit(1)

        try:
            with open(stats_file, encoding="utf-8") as f:
                stats = json.load(f)
            print(f"  (lido de: {stats_file})\n")
            print(format_stats_report(stats))
        except Exception as e:
            print(f"❌  Erro ao ler {stats_file}: {e}", file=sys.stderr)
            sys.exit(1)
        return   # ← sai sem executar scraping

    # ── Execução normal ───────────────────────────────────────────────────────
    if args.only_api and args.only_html:
        sys.exit("❌  --only-api e --only-html são mutuamente exclusivos")

    if not args.input_csv:
        candidates = sorted(Path(".").glob("sc_*.csv"), reverse=True)
        if not candidates:
            sys.exit("❌  Nenhum CSV sc_*.csv encontrado no diretório atual. Informe o arquivo explicitamente.")
        args.input_csv = str(candidates[0])
        print(f"  CSV não informado — usando o mais recente: {candidates[0].name}")

    input_path = Path(args.input_csv).resolve()
    if not input_path.exists():
        sys.exit(f"❌  Arquivo não encontrado: {input_path}")

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = input_path.stem
    mode_str  = ("apenas-api" if args.only_api
                 else "apenas-html" if args.only_html
                 else "api+html")
    mode_slug = ("api" if args.only_api
                 else "html" if args.only_html
                 else "api+html")

    # ── Detectar e limpar pastas incompletas (sem resultado.csv) ────────────────
    incompletas = [
        d for d in input_path.parent.iterdir()
        if d.is_dir()
        and d.name.startswith(base_name + "_s_")
        and not (d / "resultado.csv").exists()
    ]
    if incompletas:
        for d in sorted(incompletas):
            if args.no_clean:
                print(f"⚠  Pasta incompleta (sem resultado.csv): {d.name} — mantida (--no-clean)")
            else:
                print(f"⚠  Pasta incompleta (sem resultado.csv): {d.name} — removida")
                shutil.rmtree(d)

    # ── Detectar pasta de resume antes de definir out_dir ────────────────────
    resume_dir  = None
    elapsed_prev = 0.0
    if not args.no_resume:
        candidates = sorted(
            [d for d in input_path.parent.iterdir()
             if d.is_dir() and d.name.startswith(base_name + "_s_")],
            reverse=True,
        )
        for cand in candidates:
            if (cand / "resultado.csv").exists():
                resume_dir = cand
                # Carregar tempo acumulado da execução anterior
                prev_stats = cand / "stats.json"
                if prev_stats.exists():
                    try:
                        with open(prev_stats, encoding="utf-8") as f:
                            elapsed_prev = json.load(f).get("elapsed_seconds", 0.0)
                    except Exception:
                        pass
                break

    if args.output_dir:
        out_dir = Path(args.output_dir)
    elif resume_dir and not args.no_resume:
        out_dir = resume_dir          # reutiliza pasta existente
    else:
        out_dir = input_path.parent / f"{base_name}_s_{ts}_{mode_slug}"

    out_dir.mkdir(parents=True, exist_ok=True)

    log_path    = out_dir / "scraper.log"
    result_path = out_dir / "resultado.csv"
    stats_path  = out_dir / "stats.json"

    is_continued = resume_dir is not None and out_dir == resume_dir and not args.no_resume
    logger = setup_logging(log_path, args.log_level, append=is_continued)

    if is_continued:
        logger.info("═" * 62)
        logger.info(f"  RETOMADA — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("═" * 62)
    else:
        logger.info("=" * 62)
        logger.info(f"  SciELO Scraper  v{__version__}")
        logger.info("=" * 62)

    logger.info(f"  CSV de entrada   : {input_path.name}")

    # ── Parâmetros da busca (params.json do scielo_search.py) ────────────────
    params_path = input_path.with_name(input_path.stem + "_params.json")
    if params_path.exists():
        try:
            import json as _json
            with open(params_path, encoding="utf-8") as _pf:
                _p = _json.load(_pf)
            logger.info(f"  Origem busca     : SciELO Search")
            _anos = _p.get("anos", [])
            if _anos:
                logger.info(f"  Anos buscados    : {', '.join(str(a) for a in sorted(_anos))}")
            _termos = _p.get("termos_originais", [])
            if _termos:
                logger.info(f"  Termos de busca  : {', '.join(_termos)}"
                            + (" (truncados com $)" if _p.get("truncamento") else ""))
            _col = _p.get("colecao")
            if _col:
                logger.info(f"  Coleção busca    : {_col}")
            _campos = _p.get("campos")
            if _campos:
                logger.info(f"  Campos busca     : {_campos}")
            _total = _p.get("total_resultados")
            if _total is not None:
                logger.info(f"  Total buscado    : {_total} artigos")
        except Exception:
            pass  # params.json malformado — ignora silenciosamente
    # ─────────────────────────────────────────────────────────────────────────

    logger.info(f"  Coleção          : {args.collection}")
    logger.info(f"  Pasta de saída   : {out_dir}")
    logger.info(f"  Modo extração    : {mode_str}")
    logger.info(f"  Delay / Jitter   : {args.delay}s ± {args.jitter}s")
    logger.info(f"  Timeout          : {args.timeout}s")
    logger.info(f"  Workers          : {args.workers}")
    logger.info(f"  Log level        : {args.log_level}")
    logger.info(f"  wakepy           : {'disponível ✓' if HAS_WAKEPY else 'não instalado'}")
    logger.info(f"  API              : {ARTICLEMETA_URL}")

    if args.dry_run:
        logger.info("─" * 62)
        logger.info("[dry-run] Nenhuma requisição feita. Nenhum arquivo gravado.")
        logger.info(f"[dry-run] Leria     : {input_path}")
        logger.info(f"[dry-run] Gravaria  : {out_dir}/resultado.csv")
        logger.info(f"[dry-run] Gravaria  : {out_dir}/scraper.log")
        logger.info(f"[dry-run] Gravaria  : {out_dir}/stats.json")
        return

    ok, records = validate_csv(input_path, logger)
    if not ok:
        sys.exit(1)

    # ── Resume — carregar artigos já concluídos ───────────────────────────────
    done: dict = {}
    if not args.no_resume and result_path.exists():
        done = load_done(result_path, logger)

    resume_mode = "CONTINUED" if is_continued else ("RESUME" if done else "NEW")
    logger.info(f"  Modo execução    : {resume_mode}  ({len(done)} já concluídos)")
    if is_continued:
        logger.info(f"  Tempo anterior   : {humanize_seconds(elapsed_prev)}")
    logger.info("─" * 62)

    # Mapear PID → linha CSV (linha 2 = primeiro artigo, linha 1 = cabeçalho)
    pid_to_line = {}
    for i, r in enumerate(records, start=2):
        pid = clean_pid(r.get("ID","")) or r.get("ID","")
        pid_to_line[pid] = i

    to_process = [
        r for r in records
        if not (not args.no_resume and clean_pid(r.get("ID","")) in done)
    ]
    logger.info(f"  Total artigos    : {len(records)}")
    logger.info(f"  A processar      : {len(to_process)}")
    logger.info("─" * 62)

    # ── Teste de conectividade ────────────────────────────────────────────────
    session = build_session()
    if not args.only_html:
        logger.info("  Testando ArticleMeta API...")
        try:
            test_r = session.get(
                ARTICLEMETA_URL,
                params={"code": "S1984-92302022000400750",
                        "collection": args.collection, "format": "json"},
                headers={"User-Agent": ua()}, timeout=10,
            )
            if test_r.status_code == 200 and "article" in test_r.json():
                r_ = extract_pt_from_isis(test_r.json())
                logger.info(f"  API              : ✓ OK  ('{(r_['titulo'] or '')[:40]}')")
            else:
                logger.warning(f"  API              : HTTP {test_r.status_code}")
        except Exception as e:
            logger.warning(f"  API              : ❌ ({type(e).__name__})")
    logger.info("─" * 62)

    def run_one(row):
        pid     = clean_pid(row.get("ID","")) or row.get("ID","")
        csvline = pid_to_line.get(pid, "?")
        return process_article(
            row, csvline, session, args.collection,
            args.delay, args.jitter, args.timeout, logger,
            only_api=args.only_api, only_html=args.only_html,
        )

    # ── Processamento com wakepy ──────────────────────────────────────────────
    all_results = list(done.values())
    t_start     = time.time()

    def run_processing():
        nonlocal all_results
        if args.workers <= 1:
            itr = (tqdm(enumerate(to_process, 1), total=len(to_process), unit="art")
                   if HAS_TQDM else enumerate(to_process, 1))
            for i, row in itr:
                res = run_one(row)
                all_results.append(res)
                logger.info(f"  Progresso: {i}/{len(to_process)}")
                if args.checkpoint and i % args.checkpoint == 0:
                    save_csv(all_results, result_path, logger)
                    logger.info(f"  💾 Checkpoint: {i} artigos salvos")
        else:
            futures = {executor.submit(run_one, row): i
                       for i, row in enumerate(to_process, 1)}
            done_n = 0
            for future in as_completed(futures):
                done_n += 1
                i = futures[future]
                try:
                    all_results.append(future.result())
                    logger.info(f"  Progresso: {done_n}/{len(to_process)}")
                except Exception as e:
                    logger.error(f"  Worker erro artigo {i}: {type(e).__name__}: {e}")
                if args.checkpoint and done_n % args.checkpoint == 0:
                    save_csv(all_results, result_path, logger)
                    logger.info(f"  💾 Checkpoint: {done_n} artigos salvos")

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            if HAS_WAKEPY:
                logger.info("  wakepy: mantendo sistema acordado...")
                try:
                    with wakepy.keep.running(on_fail="warn"):
                        run_processing()
                except Exception as e:
                    logger.warning(f"  wakepy falhou ({e}), continuando sem keep-awake")
                    run_processing()
            else:
                run_processing()
    else:
        executor = None
        if HAS_WAKEPY:
            logger.info("  wakepy: mantendo sistema acordado...")
            try:
                with wakepy.keep.running(on_fail="warn"):
                    run_processing()
            except Exception as e:
                logger.warning(f"  wakepy falhou ({e}), continuando sem keep-awake")
                run_processing()
        else:
            run_processing()

    # ── Finalizar ─────────────────────────────────────────────────────────────
    elapsed = time.time() - t_start + elapsed_prev  # tempo acumulado se retomada
    logger.info("─" * 62)
    save_csv(all_results, result_path, logger)
    logger.info(f"  CSV final: {result_path.name}  ({len(all_results)} linhas)")

    mode_flags = {
        "extracao": mode_str, "resume": resume_mode,
        "workers": args.workers, "collection": args.collection,
    }
    stats = compute_stats(all_results, elapsed, __version__, mode_flags)
    stats["origem"] = _origem(args)
    log_stats(stats, logger)

    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    logger.info(f"  Arquivos em: {out_dir}")
    logger.info(f"    📄 resultado.csv  |  📋 scraper.log  |  📊 stats.json")
    logger.info("=" * 62)
    logger.info(f"  Concluído ✅  (v{__version__})")
    logger.info("=" * 62)


if __name__ == "__main__":
    main()
