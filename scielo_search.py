#!/usr/bin/env python3
"""
scielo_search.py  v1.1
======================
Baixa um CSV de artigos do SciELO Search (search.scielo.org) a partir de
termos de busca e filtros de ano/coleção, pronto para alimentar o scielo_scraper.py.

A query gerada segue o padrão combinatório do SciELO Search:
  Para cada par de termos (T1, T2), gera todas as combinações de campos:
    (ti:(T1) AND ab:(T2)) OR (ti:(T1) AND ti:(T2)) OR
    (ab:(T1) AND ab:(T2)) OR (ab:(T1) AND ti:(T2))

  Com apenas 1 termo, busca em título e/ou resumo conforme --fields.

DEPENDÊNCIAS
------------
  uv pip install requests pandas tqdm

UTILIZAÇÃO
----------
  python scielo_search.py [opções]

OPÇÕES
------
  --terms T1 T2 ...   Termos de busca. Por padrão, $ é adicionado automaticamente
                      ao final de cada termo para truncamento (ex: "avalia" → "avalia$").
                      Para desativar, use --no-truncate.
  --years Y1 Y2 ...   Anos a incluir. Pode ser lista (2020 2021) ou intervalo (2010-2022)
  --collection COD    Coleção SciELO (default: scl). Use --list-collections para ver opções
  --fields CAMPO      Campos de busca: ti (só título), ab (só resumo), ti+ab (ambos, default)
  --output FILE       Nome do CSV de saída (default: sc_<timestamp>.csv)
  --no-truncate       Não adicionar $ automaticamente nos termos (usa o termo exato)
  --list-collections  Listar coleções disponíveis e sair
  --show-params       Imprimir parâmetros da busca (params.json) e sair
  --log-level LEVEL   DEBUG | INFO | WARNING | ERROR (default: INFO)
  --version           Mostrar versão e sair
  -h, --help, -?     Mostrar esta mensagem de ajuda e sair

EXEMPLOS
--------
  # Busca por dois termos em ti+ab, ano 2022, coleção Brasil
  python scielo_search.py --terms avalia educa --years 2022 --collection scl
  # → sc_<timestamp>.csv  +  sc_<timestamp>_params.json

  # Truncamento explícito, intervalo de anos
  python scielo_search.py --terms "avalia$" "ensin$" --years 2001-2022

  # Só no título, múltiplas coleções
  python scielo_search.py --terms avalia educa --years 2020 2021 2022 --fields ti

  # Um único termo, todos os campos
  python scielo_search.py --terms avaliação --years 2023 --no-truncate

  # Listar coleções disponíveis
  python scielo_search.py --list-collections

  # Ver parâmetros da última busca
  python scielo_search.py --show-params
"""

__version__ = "1.1"

import argparse
import html as html_mod
import io
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_obrigatorios = {"requests": "requests", "pandas": "pandas"}
_opcionais    = {"tqdm": "tqdm"}
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
import pandas as pd

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ── Constantes ────────────────────────────────────────────────────────────────
SEARCH_BASE       = "https://search.scielo.org/"
COLLECTIONS_URL   = "http://articlemeta.scielo.org/api/v1/collection/identifiers/"
USER_AGENT        = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0.0.0 Safari/537.36")

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


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("scielo_search")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    if hasattr(ch.stream, "reconfigure"):
        ch.stream.reconfigure(encoding="utf-8", errors="replace")
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)
    return logger


# ── Sessão HTTP ───────────────────────────────────────────────────────────────
def build_session() -> requests.Session:
    """Cria sessão com cookie iahx necessário para o SciELO Search."""
    session = requests.Session()
    session.headers.update({
        "User-Agent":      USER_AGENT,
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer":         SEARCH_BASE,
    })
    # Primeira visita para obter o cookie de sessão (iahx)
    try:
        session.get(SEARCH_BASE, timeout=15)
    except Exception:
        pass  # Continua mesmo sem cookie — pode funcionar
    return session


# ── Anos ──────────────────────────────────────────────────────────────────────
def parse_years(raw: list[str]) -> list[int]:
    """
    Aceita:
      - Lista de anos: ["2020", "2021", "2022"]
      - Intervalo:     ["2010-2022"]
      - Misto:         ["2001-2005", "2010", "2015-2020"]
    """
    years = set()
    for item in raw:
        m = re.match(r"^(\d{4})-(\d{4})$", item.strip())
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                start, end = end, start
            years.update(range(start, end + 1))
        elif re.match(r"^\d{4}$", item.strip()):
            years.add(int(item.strip()))
        else:
            raise ValueError(f"Ano inválido: '{item}'. Use YYYY ou YYYY-YYYY.")
    return sorted(years)


# ── Query builder ─────────────────────────────────────────────────────────────
def add_truncation(term: str, no_truncate: bool) -> str:
    """Adiciona $ ao final do termo se não tiver e --no-truncate não foi passado."""
    if no_truncate:
        return term
    return term if term.endswith("$") else term + "$"


def build_query(terms: list[str], years: list[int], collection: str,
                fields: str, no_truncate: bool) -> str:
    """
    Monta a query string no formato do SciELO Search.

    Com 1 termo:
      Busca em ti e/ou ab conforme --fields.

    Com 2+ termos:
      Gera todas as combinações de campos entre pares consecutivos de termos.
      Ex: T1+T2 → (ti:T1 AND ab:T2) OR (ti:T1 AND ti:T2) OR
                  (ab:T1 AND ab:T2) OR (ab:T1 AND ti:T2)
    """
    processed = [add_truncation(t, no_truncate) for t in terms]

    # ── Bloco de termos ────────────────────────────────────────────────────────
    if len(processed) == 1:
        t = processed[0]
        field_map = {
            "ti":    [f"(ti:({t}))"],
            "ab":    [f"(ab:({t}))"],
            "ti+ab": [f"(ti:({t}))", f"(ab:({t}))"],
        }
        term_parts = field_map.get(fields, field_map["ti+ab"])
        term_block = "+OR+".join(term_parts)

    else:
        # Para cada par de termos adjacentes, gerar combinações de campos
        pair_blocks = []
        for i in range(len(processed) - 1):
            t1, t2 = processed[i], processed[i + 1]
            if fields == "ti":
                combos = [f"(ti:({t1})+AND+ti:({t2}))"]
            elif fields == "ab":
                combos = [f"(ab:({t1})+AND+ab:({t2}))"]
            else:  # ti+ab (default) — 4 combinações
                combos = [
                    f"(ti:({t1})+AND+ab:({t2}))",
                    f"(ti:({t1})+AND+ti:({t2}))",
                    f"(ab:({t1})+AND+ab:({t2}))",
                    f"(ab:({t1})+AND+ti:({t2}))",
                ]
            pair_blocks.append("+OR+".join(combos))

        # Unir blocos de pares com AND
        term_block = "+AND+".join(f"({b})" for b in pair_blocks)

    # ── Bloco de anos ──────────────────────────────────────────────────────────
    year_block = "+OR+".join(f"(year_cluster:({y}))" for y in years)

    # ── Query final ────────────────────────────────────────────────────────────
    query = (
        f"({term_block})"
        f"+AND+({year_block})"
        f'+AND+in:("{collection}")'
    )
    return query


def build_url(query: str, collection: str) -> str:
    return (
        f"{SEARCH_BASE}?q={query}"
        f"&lang=pt&count=-1&from=0&output=csv"
        f"&sort=&format=summary&fb=&page=1"
        f"&filter[in][]={collection}"
    )


# ── Download ──────────────────────────────────────────────────────────────────
def fetch_csv(url: str, session: requests.Session, logger: logging.Logger,
              timeout: float = 120) -> pd.DataFrame:
    logger.info(f"  🌐 Requisitando: {url[:120]}{'...' if len(url) > 120 else ''}")
    t0 = time.time()
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("  ❌ Timeout na requisição")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"  ❌ HTTP {e.response.status_code}: {e}")
        raise

    content_type = r.headers.get("Content-Type", "")
    if "csv" not in content_type and "text" not in content_type:
        logger.error(f"  ❌ Resposta inesperada: {content_type}")
        logger.debug(f"  Body: {r.text[:300]}")
        raise ValueError(f"Content-Type inesperado: {content_type}")

    elapsed = time.time() - t0
    logger.info(f"  ✓ Resposta recebida em {elapsed:.1f}s")

    df = pd.read_csv(io.StringIO(r.text), dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]

    # Limpar entidades HTML e espaços
    for col in df.columns:
        df[col] = df[col].apply(lambda x: html_mod.unescape(str(x).strip().strip('"')))

    # Remover coluna Fulltext URL (não usada pelo scraper)
    for col in ["Fulltext URL ", "Fulltext URL"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    return df


# ── Coleções ──────────────────────────────────────────────────────────────────
def list_collections(logger: logging.Logger):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        r = requests.get(COLLECTIONS_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        cols = r.json()
    except Exception as e:
        sys.exit(f"❌  Erro ao consultar ArticleMeta: {e}")

    active   = [c for c in cols if c.get("is_active")]
    inactive = [c for c in cols if not c.get("is_active")]

    def print_cols(lst):
        for c in sorted(lst, key=lambda x: x.get("code", "")):
            name   = (c.get("name") or {}).get("pt") or c.get("original_name", "")
            domain = c.get("domain", "")
            docs   = c.get("document_count") or "?"
            print(f"  {c['code']:<12}  {name:<35}  {domain:<38}  {str(docs):>7} docs")

    print(f"\n{'='*62}")
    print(f"  Coleções SciELO disponíveis  ({len(cols)} total)")
    print(f"{'='*62}")
    print(f"\n  {'COD':<12}  {'Nome':<35}  {'Domínio':<38}  {'Artigos':>7}")
    print(f"  {'-'*12}  {'-'*35}  {'-'*38}  {'-'*7}")
    print(f"\n  Ativas ({len(active)}):")
    print_cols(active)
    if inactive:
        print(f"\n  Inativas ({len(inactive)}):")
        print_cols(inactive)
    print(f"\n  Use --collection COD para selecionar. Ex: --collection scl")
    print(f"{'='*62}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=f"SciELO Search Downloader v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        add_help=False,
    )
    ap.add_argument("-h", "--help", "-?", action="help",
        default=argparse.SUPPRESS,
        help="Mostrar esta mensagem de ajuda e sair")
    ap.add_argument("--terms", nargs="+", metavar="TERMO",
        help="Termos de busca. $ é adicionado automaticamente ao final de cada termo "
             "(truncamento). Ex: 'avalia' vira 'avalia$'. Use --no-truncate para desativar.")
    ap.add_argument("--years", nargs="+", metavar="ANO",
        help="Anos (ex: 2022 ou 2010-2022 ou 2001 2005 2010-2015)")
    ap.add_argument("--collection", default="scl", metavar="COD",
        help="Coleção SciELO (default: scl)")
    ap.add_argument("--fields", default="ti+ab",
        choices=["ti", "ab", "ti+ab"],
        help="Campos de busca: ti, ab, ti+ab (default: ti+ab)")
    ap.add_argument("--output", default=None, metavar="FILE",
        help="Arquivo CSV de saída (default: sc_<timestamp>.csv)")
    ap.add_argument("--no-truncate", action="store_true",
        help="Desativar truncamento automático — usa o termo exato sem $ no final")
    ap.add_argument("--list-collections", action="store_true",
        help="Listar coleções disponíveis e sair")
    ap.add_argument("--show-params", action="store_true",
        help="Imprimir parâmetros da busca (params.json) e sair")
    ap.add_argument("--timeout", type=float, default=120.0, metavar="SEG",
        help="Timeout HTTP em segundos (default: 120)")
    ap.add_argument("--log-level", default="INFO", metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ap.add_argument("--version", action="version",
        version=f"scielo_search v{__version__}")
    args = ap.parse_args()

    logger = setup_logging(args.log_level)

    # ── --list-collections ────────────────────────────────────────────────────
    if args.list_collections:
        list_collections(logger)
        return

    # ── --show-params (independente de --terms/--years) ───────────────────────
    if args.show_params:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        # Procura o _params.json mais recente no diretório atual
        candidates = sorted(Path(".").glob("sc_*_params.json"), reverse=True)
        if candidates:
            with open(candidates[0], encoding="utf-8") as f:
                data = json.load(f)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("Nenhum arquivo _params.json encontrado no diretório atual.")
        return

    # ── Validações ────────────────────────────────────────────────────────────
    if not args.terms:
        ap.error("--terms é obrigatório. Ex: --terms avalia educa")
    if not args.years:
        ap.error("--years é obrigatório. Ex: --years 2022 ou --years 2010-2022")

    try:
        years = parse_years(args.years)
    except ValueError as e:
        ap.error(str(e))

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path   = Path(args.output) if args.output else Path(f"sc_{ts}.csv")

    # ── Sumário ───────────────────────────────────────────────────────────────
    logger.info("=" * 62)
    logger.info(f"  SciELO Search Downloader  v{__version__}")
    logger.info("=" * 62)
    logger.info(f"  Termos       : {args.terms}")
    logger.info(f"  Truncamento  : {'não' if args.no_truncate else 'sim ($ automático)'}")
    logger.info(f"  Campos       : {args.fields}")
    logger.info(f"  Anos         : {years[0]}–{years[-1]}  ({len(years)} anos)")
    logger.info(f"  Coleção      : {args.collection}")
    logger.info(f"  Saída        : {out_path}")
    logger.info("─" * 62)

    # ── Montar query e URL ────────────────────────────────────────────────────
    query = build_query(
        terms=args.terms,
        years=years,
        collection=args.collection,
        fields=args.fields,
        no_truncate=args.no_truncate,
    )
    url = build_url(query, args.collection)

    # Parâmetros da busca (salvos após o download)
    params_path = out_path.with_name(out_path.stem + "_params.json")
    params_data = {
        "timestamp":        datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "colecao":          args.collection,
        "termos_originais": args.terms,
        "truncamento":      not args.no_truncate,
        "campos":           args.fields,
        "anos":             years,
        "total_resultados": None,   # preenchido após o download
        "query_url":        url,
    }

    logger.debug(f"  Query: {query}")
    logger.info(f"  URL  : {url[:120]}{'...' if len(url) > 120 else ''}")
    logger.info("─" * 62)

    # ── Download ──────────────────────────────────────────────────────────────
    session = build_session()
    try:
        df = fetch_csv(url, session, logger, timeout=args.timeout)
    except Exception as e:
        logger.error(f"❌  Falha no download: {type(e).__name__}: {e}")
        sys.exit(1)

    if df.empty:
        logger.warning("⚠️  Nenhum resultado encontrado para os filtros informados.")
        sys.exit(0)

    # ── Resultado ─────────────────────────────────────────────────────────────
    logger.info(f"  📊 {len(df)} artigos encontrados")

    # Distribuição por ano
    if "Publication year" in df.columns:
        year_counts = df["Publication year"].value_counts().sort_index()
        logger.info("  Distribuição por ano:")
        for year, count in year_counts.items():
            logger.info(f"    {year}: {count} artigos")

    # PIDs duplicados
    if "ID" in df.columns:
        dups = df["ID"].duplicated().sum()
        if dups:
            logger.warning(f"  ⚠️  {dups} PIDs duplicados no resultado")

    logger.info("─" * 62)

    # ── Salvar ────────────────────────────────────────────────────────────────
    try:
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info(f"  💾 Salvo: {out_path}  ({len(df)} linhas)")
    except Exception as e:
        logger.error(f"  ❌ Erro ao salvar CSV: {e}")
        sys.exit(1)

    # ── Salvar _params.json ───────────────────────────────────────────────────
    params_data["total_resultados"] = len(df)
    try:
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(params_data, f, ensure_ascii=False, indent=2)
        logger.info(f"  📋 Parâmetros: {params_path}")
    except Exception as e:
        logger.warning(f"  ⚠️  Não foi possível salvar params.json: {e}")

    logger.info("=" * 62)
    logger.info(f"  Concluído ✅")
    logger.info(f"  Próximo passo: uv run python scielo_scraper.py {out_path}")
    logger.info("=" * 62)


if __name__ == "__main__":
    main()
