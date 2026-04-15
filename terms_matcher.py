#!/usr/bin/env python3
"""
terms_matcher.py  v1.0
=======================
Consolida resultado.csv de um ou mais anos e detecta termos de busca
por campo (titulo, resumo, palavras-chave), gerando colunas booleanas
auditáveis em planilha eletrônica.

COLUNAS GERADAS
---------------
  Métricas de texto:
    n_palavras_titulo   — nº de palavras no Titulo_PT
    n_palavras_resumo   — nº de palavras no Resumo_PT
    n_keywords_pt       — nº de keywords separadas por ";"

  Por termo × campo (1 coluna booleana cada):
    <termo>_titulo      — termo encontrado em Titulo_PT
    <termo>_resumo      — termo encontrado em Resumo_PT
    <termo>_keywords    — termo encontrado em Palavras_Chave_PT

    ⚠ ATENÇÃO: o nº de colunas cresce rapidamente.
      T termos × 3 campos = 3T colunas booleanas.
      Padrão (2 termos): 6 colunas. Com 5 termos: 15 colunas.

  Coluna de decisão:
    criterio_ok         — True se TODOS os termos foram encontrados
                          em pelo menos um dos --required-fields
                          (padrão: titulo ou keywords)

UTILIZAÇÃO
----------
  uv run python terms_matcher.py                        # todos os anos, padrões
  uv run python terms_matcher.py --years 2022 2024
  uv run python terms_matcher.py --terms avalia educa   # default
  uv run python terms_matcher.py --required-fields titulo resumo keywords
  uv run python terms_matcher.py --mode api
  uv run python terms_matcher.py --no-truncate
  uv run python terms_matcher.py --output resultado.csv
  uv run python terms_matcher.py -?

CAMPOS DISPONÍVEIS PARA --required-fields
-----------------------------------------
  titulo    → Titulo_PT
  resumo    → Resumo_PT
  keywords  → Palavras_Chave_PT

SAÍDA
-----
  terms_<ts>.csv        — CSV consolidado
  terms_<ts>.log        — log detalhado
  terms_<ts>_stats.json — estatísticas e auditoria

EXEMPLOS
--------
  uv run python terms_matcher.py --years 2022 2023 2024 2025
  uv run python terms_matcher.py --terms avalia educa saude --years 2024
    → gera 9 colunas booleanas (3 termos × 3 campos)
  uv run python terms_matcher.py --required-fields titulo resumo keywords
    → criterio_ok = True se todos os termos estão em qualquer campo
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Dependências ──────────────────────────────────────────────────────────────
try:
    import pandas as pd
except ImportError:
    sys.exit("❌  Pacote necessário não encontrado. Instale com:\n    uv pip install pandas")

# ── Constantes ────────────────────────────────────────────────────────────────
MODO_SUFIXO = {
    "api+html": re.compile(r"_api\+html$"),
    "api":      re.compile(r"_api$"),
    "html":     re.compile(r"_html$"),
}

# Mapeamento campo → coluna do DataFrame
CAMPO_COLUNA = {
    "titulo":   "Titulo_PT",
    "resumo":   "Resumo_PT",
    "keywords": "Palavras_Chave_PT",
}
CAMPOS_DISPONIVEIS  = list(CAMPO_COLUNA.keys())
CAMPOS_DEFAULT      = ["titulo", "keywords"]
TERMOS_DEFAULT      = ["avalia", "educa"]
MODO_DEFAULT        = "api+html"
BASE_DEFAULT        = "exemplos"

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
    logger = logging.getLogger("terms_matcher")
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
    return sorted(int(p.name) for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def descobrir_pasta_modo(ano_dir: Path, modo: str) -> Path | None:
    padrao = MODO_SUFIXO[modo]
    candidatas = [
        p for p in ano_dir.iterdir()
        if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
    ]
    return sorted(candidatas)[-1] if candidatas else None


def carregar_params(ano_dir: Path) -> dict:
    candidatas = sorted(ano_dir.glob("*_params.json"))
    if not candidatas:
        return {}
    with open(candidatas[-1], encoding="utf-8") as f:
        return json.load(f)


def carregar_stats(pasta: Path) -> dict:
    path = pasta / "stats.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Detecção de termos ────────────────────────────────────────────────────────
def _texto(val) -> str:
    """Normaliza valor para string minúscula, ou '' se vazio/NaN."""
    s = str(val).strip() if val and str(val).strip() not in ("", "nan") else ""
    return s.lower()


def _contem(texto: str, raiz: str) -> bool:
    """True se raiz (sem $) está presente no texto (case-insensitive já aplicado)."""
    return bool(raiz) and raiz in texto


def _n_palavras(val) -> int:
    s = _texto(val)
    return len(s.split()) if s else 0


def _n_keywords(val) -> int:
    s = _texto(val)
    return len([k for k in s.split(";") if k.strip()]) if s else 0


# ── Enriquecimento do DataFrame ───────────────────────────────────────────────
def enriquecer(
    df: pd.DataFrame,
    termos: list[str],          # raízes sem $, ex: ["avalia", "educa"]
    campos_required: list[str], # ex: ["titulo", "keywords"]
) -> pd.DataFrame:
    """
    Adiciona ao DataFrame:
      - n_palavras_titulo, n_palavras_resumo, n_keywords_pt
      - <termo>_<campo> (bool) para cada combinação
      - criterio_ok (bool)
    """
    df = df.copy()

    # ── Métricas de texto
    df["n_palavras_titulo"] = df["Titulo_PT"].apply(_n_palavras)
    df["n_palavras_resumo"] = df["Resumo_PT"].apply(_n_palavras)
    df["n_keywords_pt"]     = df["Palavras_Chave_PT"].apply(_n_keywords)

    # ── Pré-normalizar as colunas de texto uma vez só (evita repetir .lower() por linha)
    textos = {
        campo: df[col].apply(_texto)
        for campo, col in CAMPO_COLUNA.items()
    }

    # ── Colunas booleanas: <termo>_<campo>
    bool_cols: dict[str, dict[str, str]] = {}  # termo → {campo → nome_coluna}
    for t in termos:
        bool_cols[t] = {}
        for campo in CAMPOS_DISPONIVEIS:
            nome_col = f"{t}_{campo}"
            df[nome_col] = textos[campo].apply(lambda txt, r=t: _contem(txt, r))
            bool_cols[t][campo] = nome_col

    # ── criterio_ok: todos os termos em pelo menos um dos campos required
    def _criterio(row) -> bool:
        for t in termos:
            # pelo menos um campo required tem o termo?
            if not any(row[bool_cols[t][c]] for c in campos_required):
                return False
        return True

    df["criterio_ok"] = df.apply(_criterio, axis=1)

    return df


# ── Estatísticas por fatia ────────────────────────────────────────────────────
def calcular_stats(df: pd.DataFrame, termos: list[str], campos_required: list[str], label: str) -> dict:
    total = len(df)
    if total == 0:
        return {"label": label, "total": 0}

    def pct(n): return f"{n / total * 100:.1f}%" if total else "—"

    criterio_ok = int(df["criterio_ok"].sum())

    # Presença de cada termo por campo
    por_termo = {}
    for t in termos:
        por_termo[t] = {}
        for campo in CAMPOS_DISPONIVEIS:
            col = f"{t}_{campo}"
            n = int(df[col].sum())
            por_termo[t][campo] = {"n": n, "pct": pct(n)}

    return {
        "label":           label,
        "total":           total,
        "criterio_ok":     criterio_ok,
        "criterio_ok_pct": pct(criterio_ok),
        "campos_required": campos_required,
        "por_termo":       por_termo,
        "n_palavras_titulo_medio":  round(float(df["n_palavras_titulo"].mean()), 1),
        "n_palavras_resumo_medio":  round(float(df["n_palavras_resumo"].mean()), 1),
        "n_keywords_medio":         round(float(df["n_keywords_pt"].mean()), 1),
    }


# ── Argparse ──────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    campos_str = " | ".join(CAMPOS_DISPONIVEIS)
    parser = argparse.ArgumentParser(
        prog="terms_matcher.py",
        description=(
            "Consolida resultado.csv por ano e detecta termos por campo, "
            "gerando colunas booleanas auditáveis em planilha eletrônica."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Campos disponíveis para --required-fields: {campos_str}\n\n"
            "⚠ Colunas booleanas: T termos × 3 campos = 3T colunas.\n"
            "  Padrão (2 termos): 6 colunas. Com 5 termos: 15 colunas.\n\n"
            "Exemplos:\n"
            "  uv run python terms_matcher.py\n"
            "  uv run python terms_matcher.py --years 2022 2024\n"
            "  uv run python terms_matcher.py --terms avalia educa --years 2022 2023 2024 2025\n"
            "  uv run python terms_matcher.py --required-fields titulo resumo keywords\n"
            "  uv run python terms_matcher.py --terms avalia educa saude\n"
            "    # → 9 colunas booleanas (3 termos × 3 campos)\n"
            "  uv run python terms_matcher.py --stats-report\n"
            "    # lê o terms_*_stats.json mais recente e imprime o relatório\n"
            "  uv run python terms_matcher.py --stats-report terms_20260414_stats.json\n"
        ),
        add_help=False,
    )
    parser.add_argument("-h", "--help", "-?", action="help",
                        help="Mostrar esta mensagem e sair")
    parser.add_argument("--base", metavar="DIR", default=BASE_DEFAULT,
                        help=f"Pasta base com subpastas por ano (default: {BASE_DEFAULT})")
    parser.add_argument("--years", nargs="+", type=int, metavar="ANO",
                        help="Anos a incluir (default: todos encontrados em --base)")
    parser.add_argument("--terms", nargs="+", metavar="TERMO", default=TERMOS_DEFAULT,
                        help=f"Termos a detectar — default: {' '.join(TERMOS_DEFAULT)}")
    parser.add_argument("--no-truncate", action="store_true",
                        help="Não remover '$' dos termos antes da busca (truncamento ativo por padrão)")
    parser.add_argument("--required-fields", nargs="+", metavar="CAMPO",
                        default=CAMPOS_DEFAULT, choices=CAMPOS_DISPONIVEIS,
                        help=(
                            f"Campos usados em criterio_ok (default: {' '.join(CAMPOS_DEFAULT)}). "
                            f"Disponíveis: {campos_str}. "
                            "criterio_ok=True se TODOS os termos estão em pelo menos um desses campos."
                        ))
    parser.add_argument("--mode", metavar="MODO", default=MODO_DEFAULT,
                        choices=list(MODO_SUFIXO.keys()),
                        help=f"Modo de extração a usar (default: {MODO_DEFAULT})")
    parser.add_argument("--output", metavar="ARQ",
                        help="Arquivo CSV de saída (default: terms_<timestamp>.csv)")
    parser.add_argument("--stats-report", nargs="?", const=True, metavar="ARQ",
                        help=(
                            "Imprime relatório do stats.json sem processar CSVs. "
                            "Sem ARQ: lê o terms_*_stats.json mais recente no diretório atual. "
                            "Com ARQ: lê o arquivo indicado."
                        ))
    parser.add_argument("--log-level", metavar="LEVEL", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Nível de log (default: INFO)")
    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    return parser


# ── Stats report (modo standalone) ───────────────────────────────────────────
def _cmd_stats_report(arg, log_level: str):
    """Lê e formata um terms_*_stats.json sem processar nenhum CSV."""
    if arg is True:
        # sem arquivo: busca o mais recente no diretório atual
        candidatas = sorted(Path(".").glob("terms_*_stats.json"))
        if not candidatas:
            sys.exit("❌  Nenhum terms_*_stats.json encontrado no diretório atual.")
        path = candidatas[-1]
    else:
        path = Path(arg)
        if not path.exists():
            sys.exit(f"❌  Arquivo não encontrado: {path}")

    with open(path, encoding="utf-8") as f:
        s = json.load(f)

    sep = "─" * 62
    print(f"\n{'=' * 62}")
    print(f"  Terms Matcher — Relatório de Stats")
    print(f"  Arquivo : {path}")
    print(f"  Gerado  : {s.get('timestamp', '—')}")
    print(f"  Versão  : v{s.get('versao_script', '—')}")
    print(f"{'=' * 62}")

    p = s.get("parametros", {})
    print(f"\n  Termos          : {', '.join(p.get('termos_originais', []))}")
    print(f"  Campos required : {', '.join(p.get('campos_required', []))}")
    print(f"  Modo extração   : {p.get('mode', '—')}")
    print(f"  Anos processados: {p.get('anos_processados', '—')}")
    print(f"  Truncamento     : {'ativo' if p.get('truncamento') else 'desativado'}")
    print(f"  Colunas bool    : {p.get('n_colunas_bool', '—')}")

    def _print_fatia(fatia: dict, label: str):
        if not fatia:
            return
        print(f"\n{sep}")
        print(f"  {label}   (total: {fatia.get('total', 0)} artigos)")
        print(sep)
        print(f"  criterio_ok : {fatia.get('criterio_ok', '—')} ({fatia.get('criterio_ok_pct', '—')})")
        print(f"  campos used : {', '.join(fatia.get('campos_required', []))}")
        pt = fatia.get("por_termo", {})
        if pt:
            print()
            for termo, campos in pt.items():
                partes = [f"{c}: {v['n']} ({v['pct']})" for c, v in campos.items()]
                print(f"  '{termo}' → {' | '.join(partes)}")
        print(f"\n  n_palavras_titulo (médio)  : {fatia.get('n_palavras_titulo_medio', '—')}")
        print(f"  n_palavras_resumo (médio)  : {fatia.get('n_palavras_resumo_medio', '—')}")
        print(f"  n_keywords (médio)         : {fatia.get('n_keywords_medio', '—')}")

    for ano, fatia in s.get("por_ano", {}).items():
        _print_fatia(fatia, f"Ano {ano}")

    if s.get("global"):
        _print_fatia(s["global"], "GLOBAL")

    saida = s.get("saida", {})
    print(f"\n{sep}")
    print(f"  CSV   : {saida.get('csv', '—')}")
    print(f"  Log   : {saida.get('log', '—')}")
    print(f"  Total : {saida.get('total_linhas', '—')} linhas × {saida.get('total_colunas', '—')} colunas")
    print(f"  Tempo : {s.get('elapsed_humanizado', '—')}")
    print(f"{'=' * 62}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = build_parser()
    args   = parser.parse_args()

    # ── Modo --stats-report (standalone, sem processar CSVs) ─────────────────
    if args.stats_report:
        _cmd_stats_report(args.stats_report, args.log_level)
        return

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    base       = Path(args.base)
    log_path   = Path(f"terms_{ts}.log")
    stats_path = Path(f"terms_{ts}_stats.json")
    csv_out    = Path(args.output) if args.output else Path(f"terms_{ts}.csv")

    log = setup_logging(log_path, args.log_level)

    log.info("=" * 62)
    log.info(f"  Terms Matcher  v{__version__}")
    log.info("=" * 62)

    # ── Termos: remover $ para busca de substring
    termos_originais = list(args.terms)
    if args.no_truncate:
        termos_deteccao = [t.rstrip("$") for t in termos_originais]
    else:
        # adiciona $ internamente para consistência com o projeto, remove para busca
        termos_deteccao = [t.rstrip("$") for t in termos_originais]

    campos_required = list(args.required_fields)
    n_bool_cols = len(termos_deteccao) * len(CAMPOS_DISPONIVEIS)

    log.info(f"  Pasta base        : {base.resolve()}")
    log.info(f"  Modo extração     : {args.mode}")
    log.info(f"  Termos            : {', '.join(termos_originais)}")
    log.info(f"  Termos (busca)    : {', '.join(termos_deteccao)}")
    log.info(f"  Campos required   : {', '.join(campos_required)}")
    log.info(f"  Colunas booleanas : {n_bool_cols}  ({len(termos_deteccao)} termos × {len(CAMPOS_DISPONIVEIS)} campos)")
    log.info(f"  CSV de saída      : {csv_out}")
    log.info(f"  Log               : {log_path}")
    log.info(f"  Stats             : {stats_path}")
    log.info("─" * 62)

    if not base.is_dir():
        log.error(f"Pasta base não encontrada: {base}")
        sys.exit(1)

    anos_disponiveis = descobrir_anos(base)
    if not anos_disponiveis:
        log.error(f"Nenhuma subpasta de ano encontrada em: {base}")
        sys.exit(1)

    if args.years:
        anos = sorted(set(args.years))
        nao_enc = [a for a in anos if a not in anos_disponiveis]
        if nao_enc:
            log.warning(f"Anos não encontrados em {base}: {nao_enc}")
        anos = [a for a in anos if a in anos_disponiveis]
    else:
        anos = anos_disponiveis

    if not anos:
        log.error("Nenhum ano válido para processar.")
        sys.exit(1)

    log.info(f"  Anos disponíveis  : {anos_disponiveis}")
    log.info(f"  Anos a processar  : {anos}")
    log.info("─" * 62)

    t0        = time.time()
    frames    = []
    auditoria = []
    stats_anos: dict = {}

    for ano in anos:
        ano_dir = base / str(ano)
        pasta   = descobrir_pasta_modo(ano_dir, args.mode)

        if pasta is None:
            log.warning(f"[{ano}] Pasta modo '{args.mode}' não encontrada — ignorado.")
            auditoria.append({"ano": ano, "status": "pasta_ausente", "pasta": None, "linhas": 0})
            continue

        csv_path = pasta / "resultado.csv"
        if not csv_path.exists():
            log.warning(f"[{ano}] resultado.csv não encontrado em {pasta} — ignorado.")
            auditoria.append({"ano": ano, "status": "csv_ausente", "pasta": str(pasta), "linhas": 0})
            continue

        log.info(f"[{ano}] Carregando: {csv_path}")
        try:
            df_bruto = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        except UnicodeDecodeError:
            df_bruto = pd.read_csv(csv_path, dtype=str, encoding="latin-1")
        except Exception as e:
            log.error(f"[{ano}] Erro ao ler CSV: {e}")
            auditoria.append({"ano": ano, "status": "erro_leitura", "pasta": str(pasta), "linhas": 0, "erro": str(e)})
            continue

        n = len(df_bruto)
        log.info(f"[{ano}]   {n} linhas carregadas")

        df_enriq = enriquecer(df_bruto, termos_deteccao, campos_required)
        frames.append(df_enriq)

        s = calcular_stats(df_enriq, termos_deteccao, campos_required, label=str(ano))
        s["pasta_origem"]  = str(pasta)
        s["stats_scraper"] = carregar_stats(pasta)
        s["params_busca"]  = carregar_params(ano_dir)
        stats_anos[ano]    = s

        log.info(f"[{ano}]   criterio_ok: {s['criterio_ok']} ({s['criterio_ok_pct']})")
        for t in termos_deteccao:
            partes = []
            for campo in CAMPOS_DISPONIVEIS:
                info = s["por_termo"][t][campo]
                partes.append(f"{campo}: {info['n']} ({info['pct']})")
            log.info(f"[{ano}]   '{t}' → {' | '.join(partes)}")

        auditoria.append({"ano": ano, "status": "ok", "pasta": str(pasta), "linhas": n})

    if not frames:
        log.error("Nenhum dado carregado. Verifique --base, --years e --mode.")
        sys.exit(1)

    log.info("─" * 62)
    df_final    = pd.concat(frames, ignore_index=True)
    total_geral = len(df_final)
    log.info(f"Total consolidado: {total_geral} linhas ({len(frames)} ano(s))")

    stats_global = None
    if len(frames) > 1:
        stats_global = calcular_stats(df_final, termos_deteccao, campos_required, label="GLOBAL")
        log.info("─" * 62)
        log.info("Estatísticas GLOBAIS:")
        log.info(f"  criterio_ok : {stats_global['criterio_ok']} ({stats_global['criterio_ok_pct']})")
        for t in termos_deteccao:
            partes = []
            for campo in CAMPOS_DISPONIVEIS:
                info = stats_global["por_termo"][t][campo]
                partes.append(f"{campo}: {info['n']} ({info['pct']})")
            log.info(f"  '{t}' → {' | '.join(partes)}")

    log.info("─" * 62)
    df_final.to_csv(csv_out, index=False, encoding="utf-8-sig")
    log.info(f"CSV salvo: {csv_out}  ({total_geral} linhas, {len(df_final.columns)} colunas)")
    log.debug(f"Colunas: {list(df_final.columns)}")

    elapsed = time.time() - t0
    stats_saida = {
        "versao_script":     __version__,
        "timestamp":         datetime.now().isoformat(),
        "parametros": {
            "base":             str(base.resolve()),
            "mode":             args.mode,
            "anos_solicitados": args.years or "todos",
            "anos_processados": anos,
            "termos_originais": termos_originais,
            "termos_deteccao":  termos_deteccao,
            "truncamento":      not args.no_truncate,
            "campos_required":  campos_required,
            "n_colunas_bool":   n_bool_cols,
        },
        "saida": {
            "csv":           str(csv_out),
            "log":           str(log_path),
            "stats":         str(stats_path),
            "total_linhas":  total_geral,
            "total_colunas": len(df_final.columns),
            "colunas":       list(df_final.columns),
        },
        "elapsed_seconds":    round(elapsed, 3),
        "elapsed_humanizado": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
        "auditoria":          auditoria,
        "por_ano":            stats_anos,
        "global":             stats_global,
    }

    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_saida, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Stats salvas: {stats_path}")
    log.info("─" * 62)
    log.info(f"Concluído em {stats_saida['elapsed_humanizado']}  ✓")
    log.info("=" * 62)


if __name__ == "__main__":
    main()
