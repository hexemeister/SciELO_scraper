#!/usr/bin/env python3
"""
enriquecedor_csv.py  v1.0
=========================
Cria um CSV enriquecido a partir dos resultado.csv gerados pelo SciELO Scraper,
adicionando colunas derivadas úteis para análise e filtragem.

Lê as pastas de scraping em exemplos/<ano>/<stem>_s_<ts>_<modo>/resultado.csv,
agrega os anos solicitados e gera um único CSV consolidado com:

  Colunas originais (15):
    ID, Title, Author(s), Source, Journal, Language(s), Publication year,
    PID_limpo, URL_PT, Titulo_PT, Resumo_PT, Palavras_Chave_PT,
    status, fonte_extracao, url_acedida

  Colunas enriquecidas (novas):
    ano_coleta          — ano da pasta de exemplos (ex: 2022)
    modo_extracao       — modo usado: api+html | api | html
    tem_titulo_pt       — bool: Titulo_PT não-vazio
    tem_resumo_pt       — bool: Resumo_PT não-vazio
    tem_keywords_pt     — bool: Palavras_Chave_PT não-vazio
    n_keywords_pt       — contagem de keywords (separadas por ";")
    n_palavras_resumo   — contagem de palavras no Resumo_PT
    fonte_simplificada  — categoria legível da fonte de extração
    termo_detectado     — termos de busca detectados no título/resumo PT (lista)
    is_aop              — bool: artigo ahead-of-print (PID com "005" pos 14-16)
    ISSN                — extraído do PID (pos 1-9, formatado com hífen)
    ano_publicacao_num  — "Publication year" como int (NaN se inválido)

UTILIZAÇÃO
----------
  uv run python enriquecedor_csv.py                        # todos os anos, modo api+html
  uv run python enriquecedor_csv.py --years 2022 2024      # apenas esses anos
  uv run python enriquecedor_csv.py --terms avalia educa   # outros termos de busca
  uv run python enriquecedor_csv.py --mode api             # modo alternativo
  uv run python enriquecedor_csv.py --base exemplos        # pasta base (default: exemplos)
  uv run python enriquecedor_csv.py --output resultado_enriquecido.csv
  uv run python enriquecedor_csv.py --no-truncate          # não adicionar $ aos termos
  uv run python enriquecedor_csv.py --log-level DEBUG
  uv run python enriquecedor_csv.py -?                     # ajuda

SAÍDA
-----
  <output>              — CSV enriquecido (default: enriquecido_<timestamp>.csv)
  enriquecedor_<ts>.log — log detalhado da execução
  enriquecedor_<ts>_stats.json — estatísticas e auditoria completa

EXEMPLOS
--------
  uv run python enriquecedor_csv.py --years 2022 2023 2024 2025
  uv run python enriquecedor_csv.py --terms avalia --no-truncate --output saida.csv
  uv run python enriquecedor_csv.py --mode html --years 2024
"""

__version__ = "1.0"

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Garantir UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Dependências ──────────────────────────────────────────────────────────────
_obrigatorios = {"pandas": "pandas"}
_faltando = []
for _mod, _pkg in _obrigatorios.items():
    try:
        __import__(_mod)
    except ImportError:
        _faltando.append(_pkg)
if _faltando:
    sys.exit(
        "❌  Pacotes necessários não encontrados. Instale com:\n"
        f"    uv pip install {' '.join(_faltando)}"
    )

import pandas as pd

# ── Constantes ────────────────────────────────────────────────────────────────
MODO_SUFIXO = {
    "api+html": re.compile(r"_api\+html$"),
    "api":      re.compile(r"_api$"),
    "html":     re.compile(r"_html$"),
}

FONTE_SIMPLIFICADA = {
    "articlemeta_isis": "ArticleMeta API",
    "api+html_fallback": "Fallback API+HTML",
    "html_fallback":     "Fallback HTML",
    "sem_fonte":         "Sem fonte",
}

TERMOS_DEFAULT   = ["avalia", "educa"]
MODO_DEFAULT     = "api+html"
BASE_DEFAULT     = "exemplos"

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


def setup_logging(log_path: Path, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("enriquecedor")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    if hasattr(ch.stream, "reconfigure"):
        ch.stream.reconfigure(encoding="utf-8", errors="replace")
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    return logger


# ── Descoberta de pastas ──────────────────────────────────────────────────────
def descobrir_anos(base: Path) -> list[int]:
    """Retorna lista de anos (pastas numéricas) dentro de base/, ordenada."""
    anos = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name.isdigit():
            anos.append(int(p.name))
    return anos


def descobrir_pasta_modo(ano_dir: Path, modo: str) -> Path | None:
    """Pasta de scraping mais recente para um dado modo dentro de ano_dir."""
    padrao = MODO_SUFIXO[modo]
    candidatas = [
        p for p in ano_dir.iterdir()
        if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
    ]
    if not candidatas:
        return None
    return sorted(candidatas)[-1]


def carregar_params(ano_dir: Path) -> dict:
    """Carrega o _params.json mais recente dentro de ano_dir (ou None)."""
    candidatas = sorted(ano_dir.glob("*_params.json"))
    if not candidatas:
        return {}
    with open(candidatas[-1], encoding="utf-8") as f:
        return json.load(f)


def carregar_stats(pasta: Path) -> dict:
    """Carrega stats.json da pasta de scraping, ou {} se ausente."""
    path = pasta / "stats.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Enriquecimento por linha ──────────────────────────────────────────────────
def _bool_col(val) -> bool:
    """True se valor não-nulo e não-vazio."""
    return bool(val and str(val).strip())


def _n_keywords(val) -> int:
    if not _bool_col(val):
        return 0
    return len([k for k in str(val).split(";") if k.strip()])


def _n_palavras(val) -> int:
    if not _bool_col(val):
        return 0
    return len(str(val).split())


def _fonte_simplificada(fonte: str) -> str:
    """Converte fonte_extracao em categoria legível.

    Reconhece formatos:
      "articlemeta_isis[T] | articlemeta_isis[R] | …"  → ArticleMeta API
      "api+html_fallback"                               → Fallback API+HTML
      "html_fallback"  ou  "…←pag1_meta_tags…"         → Fallback HTML
      NaN / vazio                                       → Sem fonte / Falha HTTP
    """
    if not fonte or str(fonte).strip() in ("", "nan"):
        return FONTE_SIMPLIFICADA["sem_fonte"]
    s = str(fonte).lower()
    if "articlemeta_isis" in s:
        return FONTE_SIMPLIFICADA["articlemeta_isis"]
    if "api+html_fallback" in s:
        return FONTE_SIMPLIFICADA["api+html_fallback"]
    # html_fallback direto OU extrações via HTML (←pag1_meta_tags, ←body, etc.)
    if "html_fallback" in s or "←" in s or "<-" in s or "pag" in s:
        return FONTE_SIMPLIFICADA["html_fallback"]
    return FONTE_SIMPLIFICADA["sem_fonte"]


def _termos_detectados(titulo: str, resumo: str, termos: list[str]) -> str:
    """Retorna termos (já com $ removido) encontrados no título ou resumo PT."""
    texto = " ".join([str(titulo or ""), str(resumo or "")]).lower()
    encontrados = []
    for t in termos:
        # remove $ de truncamento para busca de substring
        raiz = t.rstrip("$")
        if raiz and raiz in texto:
            encontrados.append(raiz)
    return "; ".join(sorted(set(encontrados))) if encontrados else ""


def _is_aop(pid: str) -> bool:
    """PIDs ahead-of-print têm '005' nas posições 14-16."""
    s = str(pid).strip()
    return len(s) == 23 and s[14:17] == "005"


def _extrair_issn(pid: str) -> str:
    """Extrai ISSN do PID SciELO (pos 1-9): 'S1517-86922022…' → '1517-8692'."""
    s = str(pid).strip()
    # PID: S<ISSN-8chars><ano4><sufixo> — o ISSN inclui o hífen embutido (9 chars: XXXX-YYYY)
    if len(s) >= 10:
        return s[1:10]  # ex: "1517-8692"
    return ""


def _ano_pub_num(val) -> object:
    """Converte 'Publication year' para int, ou pd.NA se inválido."""
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return pd.NA


# ── Enriquecimento do DataFrame ───────────────────────────────────────────────
def enriquecer(df: pd.DataFrame, ano: int, modo: str, termos: list[str]) -> pd.DataFrame:
    """
    Recebe o DataFrame bruto do resultado.csv e adiciona colunas derivadas.
    termos: lista de termos (já com $ se truncamento ativo).
    """
    df = df.copy()

    df["ano_coleta"]        = ano
    df["modo_extracao"]     = modo
    df["tem_titulo_pt"]     = df["Titulo_PT"].apply(_bool_col)
    df["tem_resumo_pt"]     = df["Resumo_PT"].apply(_bool_col)
    df["tem_keywords_pt"]   = df["Palavras_Chave_PT"].apply(_bool_col)
    df["n_keywords_pt"]     = df["Palavras_Chave_PT"].apply(_n_keywords)
    df["n_palavras_resumo"] = df["Resumo_PT"].apply(_n_palavras)
    df["fonte_simplificada"] = df["fonte_extracao"].apply(_fonte_simplificada)
    df["termo_detectado"]   = df.apply(
        lambda r: _termos_detectados(r.get("Titulo_PT", ""), r.get("Resumo_PT", ""), termos),
        axis=1,
    )
    df["is_aop"]            = df["PID_limpo"].apply(_is_aop)
    df["ISSN"]              = df["PID_limpo"].apply(_extrair_issn)
    df["ano_publicacao_num"] = df["Publication year"].apply(_ano_pub_num)

    return df


# ── Estatísticas por fatia ────────────────────────────────────────────────────
def calcular_stats_fatia(df: pd.DataFrame, label: str) -> dict:
    """Calcula estatísticas de cobertura e qualidade para uma fatia do DF."""
    total = len(df)
    if total == 0:
        return {"label": label, "total": 0}

    ok_completo  = int((df["status"] == "ok_completo").sum())
    ok_parcial   = int((df["status"] == "ok_parcial").sum())
    nada         = int((df["status"] == "nada_encontrado").sum())
    erro_ext     = int((df["status"] == "erro_extracao").sum())
    erro_pid     = int((df["status"] == "erro_pid_invalido").sum())
    sucesso      = ok_completo + ok_parcial

    def pct(n): return f"{n/total*100:.1f}%" if total else "—"

    fontes = (
        df["fonte_simplificada"]
        .value_counts()
        .to_dict()
    )

    termos_dist = {}
    for t in df["termo_detectado"].dropna():
        for item in str(t).split(";"):
            item = item.strip()
            if item:
                termos_dist[item] = termos_dist.get(item, 0) + 1

    return {
        "label":            label,
        "total":            total,
        "ok_completo":      ok_completo,
        "ok_completo_pct":  pct(ok_completo),
        "ok_parcial":       ok_parcial,
        "ok_parcial_pct":   pct(ok_parcial),
        "sucesso_total":    sucesso,
        "sucesso_total_pct": pct(sucesso),
        "nada_encontrado":  nada,
        "nada_encontrado_pct": pct(nada),
        "erro_extracao":    erro_ext,
        "erro_extracao_pct": pct(erro_ext),
        "erro_pid_invalido": erro_pid,
        "erro_pid_pct":     pct(erro_pid),
        "tem_titulo_pt":    int(df["tem_titulo_pt"].sum()),
        "tem_titulo_pt_pct": pct(df["tem_titulo_pt"].sum()),
        "tem_resumo_pt":    int(df["tem_resumo_pt"].sum()),
        "tem_resumo_pt_pct": pct(df["tem_resumo_pt"].sum()),
        "tem_keywords_pt":  int(df["tem_keywords_pt"].sum()),
        "tem_keywords_pt_pct": pct(df["tem_keywords_pt"].sum()),
        "is_aop":           int(df["is_aop"].sum()),
        "is_aop_pct":       pct(df["is_aop"].sum()),
        "n_keywords_medio": round(float(df["n_keywords_pt"].mean()), 2),
        "n_palavras_resumo_medio": round(float(df["n_palavras_resumo"].mean()), 2),
        "por_fonte":        fontes,
        "termos_detectados": termos_dist,
    }


# ── Argparse ──────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enriquecedor_csv.py",
        description=(
            "Cria um CSV enriquecido a partir dos resultado.csv do SciELO Scraper, "
            "adicionando colunas derivadas para análise (cobertura, termos, fontes, AoP…)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  uv run python enriquecedor_csv.py\n"
            "  uv run python enriquecedor_csv.py --years 2022 2024\n"
            "  uv run python enriquecedor_csv.py --terms avalia educa --years 2022 2023 2024 2025\n"
            "  uv run python enriquecedor_csv.py --mode api --no-truncate\n"
            "  uv run python enriquecedor_csv.py --output meu_resultado.csv\n"
        ),
        add_help=False,
    )
    parser.add_argument("-h", "--help", "-?", action="help",
                        help="Mostrar esta mensagem e sair")
    parser.add_argument("--base", metavar="DIR", default=BASE_DEFAULT,
                        help=f"Pasta base com subpastas por ano (default: {BASE_DEFAULT})")
    parser.add_argument("--years", nargs="+", type=int, metavar="YEAR",
                        help="Anos a incluir (default: todos encontrados em --base)")
    parser.add_argument("--terms", nargs="+", metavar="TERMO", default=TERMOS_DEFAULT,
                        help=f"Termos para detectar nos textos PT (default: {' '.join(TERMOS_DEFAULT)})")
    parser.add_argument("--no-truncate", action="store_true",
                        help="Não adicionar '$' no final dos termos (truncamento ativo por padrão)")
    parser.add_argument("--mode", metavar="MODO", default=MODO_DEFAULT,
                        choices=list(MODO_SUFIXO.keys()),
                        help=f"Modo de extração a usar (default: {MODO_DEFAULT})")
    parser.add_argument("--output", metavar="ARQ",
                        help="Arquivo CSV de saída (default: enriquecido_<timestamp>.csv)")
    parser.add_argument("--log-level", metavar="LEVEL", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Nível de log (default: INFO)")
    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    return parser


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = build_parser()
    args   = parser.parse_args()

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    base    = Path(args.base)
    log_path = Path(f"enriquecedor_{ts}.log")
    stats_path = Path(f"enriquecedor_{ts}_stats.json")
    csv_out    = Path(args.output) if args.output else Path(f"enriquecido_{ts}.csv")

    log = setup_logging(log_path, args.log_level)

    log.info("=" * 62)
    log.info(f"  Enriquecedor CSV  v{__version__}")
    log.info("=" * 62)

    # ── Termos (com ou sem truncamento) ───────────────────────────────────────
    termos_originais = list(args.terms)
    if args.no_truncate:
        termos_busca = termos_originais[:]
    else:
        termos_busca = [t if t.endswith("$") else t + "$" for t in termos_originais]
    # Para detecção de texto removemos o $
    termos_deteccao = [t.rstrip("$") for t in termos_busca]

    log.info(f"  Pasta base       : {base.resolve()}")
    log.info(f"  Modo extração    : {args.mode}")
    log.info(f"  Termos originais : {', '.join(termos_originais)}")
    log.info(f"  Termos busca     : {', '.join(termos_busca)}")
    log.info(f"  Truncamento      : {'desativado' if args.no_truncate else 'ativo'}")
    log.info(f"  CSV de saída     : {csv_out}")
    log.info(f"  Log              : {log_path}")
    log.info(f"  Stats            : {stats_path}")
    log.info("─" * 62)

    # ── Validar pasta base ─────────────────────────────────────────────────────
    if not base.is_dir():
        log.error(f"Pasta base não encontrada: {base}")
        sys.exit(1)

    # ── Descobrir anos ─────────────────────────────────────────────────────────
    anos_disponiveis = descobrir_anos(base)
    if not anos_disponiveis:
        log.error(f"Nenhuma subpasta de ano encontrada em: {base}")
        sys.exit(1)

    if args.years:
        anos = sorted(set(args.years))
        nao_encontrados = [a for a in anos if a not in anos_disponiveis]
        if nao_encontrados:
            log.warning(f"Anos solicitados não encontrados em {base}: {nao_encontrados}")
        anos = [a for a in anos if a in anos_disponiveis]
    else:
        anos = anos_disponiveis

    if not anos:
        log.error("Nenhum ano válido para processar.")
        sys.exit(1)

    log.info(f"  Anos disponíveis : {anos_disponiveis}")
    log.info(f"  Anos a processar : {anos}")
    log.info("─" * 62)

    # ── Carregar e enriquecer ─────────────────────────────────────────────────
    t0          = time.time()
    frames      = []           # DataFrames por ano
    auditoria   = []           # registro de cada fonte carregada
    stats_anos  = {}           # stats por ano
    params_anos = {}           # params.json por ano

    for ano in anos:
        ano_dir = base / str(ano)
        pasta   = descobrir_pasta_modo(ano_dir, args.mode)

        if pasta is None:
            log.warning(f"[{ano}] Pasta modo '{args.mode}' não encontrada em {ano_dir} — ano ignorado.")
            auditoria.append({
                "ano": ano, "status": "pasta_ausente",
                "pasta": None, "linhas": 0,
            })
            continue

        csv_path = pasta / "resultado.csv"
        if not csv_path.exists():
            log.warning(f"[{ano}] resultado.csv não encontrado em {pasta} — ano ignorado.")
            auditoria.append({
                "ano": ano, "status": "csv_ausente",
                "pasta": str(pasta), "linhas": 0,
            })
            continue

        # Carrega params.json da pasta do ano (busca original)
        params = carregar_params(ano_dir)
        params_anos[ano] = params

        # Carrega stats.json da pasta de scraping
        stats_scraper = carregar_stats(pasta)

        log.info(f"[{ano}] Carregando: {csv_path}")
        try:
            df_bruto = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        except UnicodeDecodeError:
            df_bruto = pd.read_csv(csv_path, dtype=str, encoding="latin-1")
        except Exception as e:
            log.error(f"[{ano}] Erro ao ler CSV: {e}")
            auditoria.append({
                "ano": ano, "status": "erro_leitura",
                "pasta": str(pasta), "linhas": 0, "erro": str(e),
            })
            continue

        n_linhas = len(df_bruto)
        log.info(f"[{ano}]   {n_linhas} linhas carregadas")
        log.debug(f"[{ano}]   Colunas: {list(df_bruto.columns)}")

        # Enriquecer
        df_enriq = enriquecer(df_bruto, ano, args.mode, termos_deteccao)
        frames.append(df_enriq)

        # Stats desta fatia
        s = calcular_stats_fatia(df_enriq, label=str(ano))
        s["pasta_origem"] = str(pasta)
        s["stats_scraper"] = stats_scraper
        s["params_busca"]  = params
        stats_anos[ano] = s

        log.info(f"[{ano}]   ok_completo: {s['ok_completo']} ({s['ok_completo_pct']})  "
                 f"| ok_parcial: {s['ok_parcial']} ({s['ok_parcial_pct']})  "
                 f"| sucesso: {s['sucesso_total']} ({s['sucesso_total_pct']})")
        log.info(f"[{ano}]   com_titulo: {s['tem_titulo_pt']} ({s['tem_titulo_pt_pct']})  "
                 f"| com_resumo: {s['tem_resumo_pt']} ({s['tem_resumo_pt_pct']})  "
                 f"| AoP: {s['is_aop']} ({s['is_aop_pct']})")
        log.debug(f"[{ano}]   Fontes: {s['por_fonte']}")
        log.debug(f"[{ano}]   Termos detectados: {s['termos_detectados']}")

        auditoria.append({
            "ano": ano, "status": "ok",
            "pasta": str(pasta), "linhas": n_linhas,
        })

    # ── Consolidar ────────────────────────────────────────────────────────────
    if not frames:
        log.error("Nenhum dado carregado. Verifique --base, --years e --mode.")
        sys.exit(1)

    log.info("─" * 62)
    df_final = pd.concat(frames, ignore_index=True)
    total_geral = len(df_final)
    log.info(f"Total consolidado: {total_geral} linhas ({len(frames)} ano(s))")

    # Stats consolidadas (apenas se mais de um ano)
    stats_global = None
    if len(frames) > 1:
        stats_global = calcular_stats_fatia(df_final, label="GLOBAL")
        log.info("─" * 62)
        log.info("Estatísticas GLOBAIS consolidadas:")
        log.info(f"  ok_completo  : {stats_global['ok_completo']} ({stats_global['ok_completo_pct']})")
        log.info(f"  ok_parcial   : {stats_global['ok_parcial']} ({stats_global['ok_parcial_pct']})")
        log.info(f"  sucesso      : {stats_global['sucesso_total']} ({stats_global['sucesso_total_pct']})")
        log.info(f"  com título   : {stats_global['tem_titulo_pt']} ({stats_global['tem_titulo_pt_pct']})")
        log.info(f"  com resumo   : {stats_global['tem_resumo_pt']} ({stats_global['tem_resumo_pt_pct']})")
        log.info(f"  com keywords : {stats_global['tem_keywords_pt']} ({stats_global['tem_keywords_pt_pct']})")
        log.info(f"  AoP          : {stats_global['is_aop']} ({stats_global['is_aop_pct']})")
        log.info(f"  Fontes       : {stats_global['por_fonte']}")
        log.info(f"  Termos       : {stats_global['termos_detectados']}")

    # ── Salvar CSV ────────────────────────────────────────────────────────────
    log.info("─" * 62)
    df_final.to_csv(csv_out, index=False, encoding="utf-8-sig")
    log.info(f"CSV enriquecido salvo: {csv_out}  ({total_geral} linhas, {len(df_final.columns)} colunas)")
    log.debug(f"Colunas: {list(df_final.columns)}")

    # ── Salvar stats.json ─────────────────────────────────────────────────────
    elapsed = time.time() - t0
    stats_saida = {
        "versao_script":     __version__,
        "timestamp":         datetime.now().isoformat(),
        "parametros": {
            "base":              str(base.resolve()),
            "mode":              args.mode,
            "anos_solicitados":  args.years or "todos",
            "anos_processados":  anos,
            "termos_originais":  termos_originais,
            "termos_busca":      termos_busca,
            "termos_deteccao":   termos_deteccao,
            "truncamento":       not args.no_truncate,
        },
        "saida": {
            "csv":              str(csv_out),
            "log":              str(log_path),
            "stats":            str(stats_path),
            "total_linhas":     total_geral,
            "total_colunas":    len(df_final.columns),
            "colunas":          list(df_final.columns),
        },
        "elapsed_seconds":   round(elapsed, 3),
        "elapsed_humanizado": f"{int(elapsed//60)}m {int(elapsed%60)}s",
        "auditoria":         auditoria,
        "por_ano":           stats_anos,
        "global":            stats_global,
    }

    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_saida, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"Stats salvas     : {stats_path}")
    log.info("─" * 62)
    log.info(f"Concluído em {stats_saida['elapsed_humanizado']}  ✓")
    log.info("=" * 62)


if __name__ == "__main__":
    main()
