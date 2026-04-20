"""
results_report.py — Artefatos científicos publication-ready do projeto e-Aval.

Propósito: gerar o arcabouço completo de resultados científicos a partir do CSV
produzido pelo terms_matcher.py. Não fala sobre o processo técnico — para isso
use process_charts.py.

Contexto: ferramenta do projeto "Estado da Arte da Avaliação" (e-Aval), grupo de
pesquisa do Mestrado Profissional em Avaliação da Fundação Cesgranrio. Os artigos
com criterio_ok=True serão encaminhados para curadoria humana antes de integrar
o banco de dados público (https://eavaleducacao1.websiteseguro.com/).

Artefatos gerados em runs/<ano>/results_<stem_scraping>/ (ou --output-dir):
    Gráficos (sempre com sufixo de idioma, ex: _pt ou _en):
        results_funnel_<lang>.png          — funil: buscado → raspado → criterio_ok
        results_trend_<lang>.png           — evolução temporal de criterio_ok por ano
        results_terms_heatmap_<lang>.png   — heatmap termos × campos (% de ocorrência)
        results_journals_<lang>.png        — top periódicos por n artigos criterio_ok
        results_coverage_<lang>.png        — % de artigos com cada campo PT presente

    Tabelas (CSV — sem sufixo de idioma):
        results_table_summary.csv   — funil por ano + totais
        results_table_terms.csv     — por termo × campo: n e % de ocorrência
        results_table_journals.csv  — periódicos com contagem e % (todos, sem limite)

    Texto (Markdown — sempre com sufixo de idioma):
        results_text_<lang>.md      — seções: Metodologia, Resultados e Limitações

    Metadados:
        results_report.json         — todos os dados calculados (para reúso/consulta)

Uso:
    uv run python results_report.py                       # api+html, todos os anos em runs/
    uv run python results_report.py --mode api            # estratégia alternativa
    uv run python results_report.py --years 2022 2024     # anos específicos
    uv run python results_report.py --base outra/pasta    # pasta raiz alternativa
    uv run python results_report.py --output-dir relat/   # pasta de saída explícita
    uv run python results_report.py --lang en             # inglês
    uv run python results_report.py --lang all            # todos os idiomas
    uv run python results_report.py --top-journals 20     # top 20 periódicos (default: 15)
    uv run python results_report.py --dry-run
    uv run python results_report.py --show-report         # renderiza results_report.json existente
    uv run python results_report.py --help-artifacts      # lista resumida de todos os artefatos
    uv run python results_report.py --help-artifact results_funnel  # ajuda detalhada do artefato
    uv run python results_report.py -?
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

__version__ = "1.2"

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------

IDIOMAS_DISPONIVEIS = ["pt", "en"]

STRINGS: dict[str, dict[str, str]] = {
    # Títulos de gráficos
    "titulo_funnel": {
        "pt": "Funil de seleção — cobertura do processo",
        "en": "Selection funnel — process coverage",
    },
    "titulo_trend": {
        "pt": "Evolução temporal: artigos que atendem ao critério",
        "en": "Temporal trend: articles meeting the criterion",
    },
    "titulo_heatmap": {
        "pt": "Presença dos termos por campo (% do corpus criterio_ok)",
        "en": "Term presence by field (% of criterio_ok corpus)",
    },
    "titulo_journals": {
        "pt": "Periódicos com maior número de artigos (criterio_ok)",
        "en": "Journals with most articles (criterio_ok)",
    },
    "titulo_coverage": {
        "pt": "Cobertura de campos PT por ano",
        "en": "PT field coverage by year",
    },
    # Eixos
    "eixo_n_artigos": {
        "pt": "n artigos",
        "en": "n articles",
    },
    "eixo_ano": {
        "pt": "Ano",
        "en": "Year",
    },
    "eixo_campo": {
        "pt": "Campo",
        "en": "Field",
    },
    "eixo_termo": {
        "pt": "Termo",
        "en": "Term",
    },
    "eixo_pct": {
        "pt": "% artigos",
        "en": "% articles",
    },
    "eixo_periodico": {
        "pt": "Periódico",
        "en": "Journal",
    },
    # Rótulos do funil
    "funnel_buscado": {
        "pt": "Buscados\n(SciELO Search)",
        "en": "Retrieved\n(SciELO Search)",
    },
    "funnel_scrapeado": {
        "pt": "Raspados\n(dados extraídos)",
        "en": "Scraped\n(data extracted)",
    },
    "funnel_criterio": {
        "pt": "Critério ok\n(para curadoria)",
        "en": "Criterion met\n(for curation)",
    },
    # Campos
    "campo_titulo": {
        "pt": "Título",
        "en": "Title",
    },
    "campo_resumo": {
        "pt": "Resumo",
        "en": "Abstract",
    },
    "campo_keywords": {
        "pt": "Palavras-chave",
        "en": "Keywords",
    },
    # Legenda cobertura
    "legenda_campo": {
        "pt": "Campo",
        "en": "Field",
    },
    # Seções do texto
    "sec_metodologia": {
        "pt": "## Metodologia",
        "en": "## Methodology",
    },
    "sec_resultados": {
        "pt": "## Resultados",
        "en": "## Results",
    },
    "sec_limitacoes": {
        "pt": "## Limitações",
        "en": "## Limitations",
    },
    "sec_artefatos": {
        "pt": "## Artefatos gerados",
        "en": "## Generated artifacts",
    },
    # Notas
    "nota_heatmap": {
        "pt": "Base: artigos com criterio_ok=True. Valores = % dos artigos em que o termo aparece no campo.",
        "en": "Base: articles with criterio_ok=True. Values = % of articles where the term appears in the field.",
    },
    "nota_funnel": {
        "pt": "criterio_ok: todos os termos presentes em pelo menos um campo required (padrão: título ou palavras-chave).",
        "en": "criterio_ok: all terms present in at least one required field (default: title or keywords).",
    },
    # Arquivos de saída
    "arquivo_funnel":   {"pt": "results_funnel",         "en": "results_funnel"},
    "arquivo_trend":    {"pt": "results_trend",          "en": "results_trend"},
    "arquivo_heatmap":  {"pt": "results_terms_heatmap",  "en": "results_terms_heatmap"},
    "arquivo_journals": {"pt": "results_journals",       "en": "results_journals"},
    "arquivo_coverage": {"pt": "results_coverage",       "en": "results_coverage"},
    "arquivo_texto":    {"pt": "results_text",           "en": "results_text"},
    # Legenda trend
    "legenda_total_scrapeado": {
        "pt": "total raspado",
        "en": "total scraped",
    },
    "legenda_criterio_ok": {
        "pt": "criterio_ok",
        "en": "criterion met",
    },
    "legenda_pct_criterio": {
        "pt": "% criterio_ok",
        "en": "% criterion met",
    },
}


def s(chave: str, lang: str) -> str:
    return STRINGS[chave].get(lang, STRINGS[chave]["pt"])


# ---------------------------------------------------------------------------
# Catálogo de artefatos (para --help-artifacts / --help-artifact)
# ---------------------------------------------------------------------------

ARTEFATOS_CATALOGO = [
    {
        "nome":     "results_funnel",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_funnel_<lang>.png",
        "descricao_pt": (
            "Funil de seleção com três etapas (recuperados → raspados → criterio_ok) "
            "exibidas em barras separadas por ano. "
            "Mostra a cobertura do processo: quantos artigos foram recuperados, quantos tiveram "
            "metadados extraídos com sucesso, e quantos passaram pelo critério de filtragem automática."
        ),
        "descricao_en": (
            "Selection funnel with three stages (retrieved → scraped → criterion met) "
            "displayed as separate bars per year. "
            "Shows process coverage: how many articles were retrieved, how many had metadata "
            "successfully extracted, and how many passed the automatic filtering criterion."
        ),
        "termos_usados_pt": "Nenhum termo de busca — mostra contagens brutas do processo.",
        "termos_usados_en": "No search terms — shows raw process counts.",
    },
    {
        "nome":     "results_trend",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_trend_<lang>.png",
        "descricao_pt": (
            "Gráfico de barras duplas com linha de % sobreposta, mostrando a evolução temporal "
            "de criterio_ok. Eixo esquerdo: n artigos (total raspado e criterio_ok); "
            "eixo direito: % de artigos que atendem ao critério por ano."
        ),
        "descricao_en": (
            "Dual bar chart with overlaid % line, showing the temporal trend of criterio_ok. "
            "Left axis: n articles (total scraped and criterion met); "
            "right axis: % of articles meeting the criterion per year."
        ),
        "termos_usados_pt": "Nenhum termo de busca — mostra proporções do critério por ano.",
        "termos_usados_en": "No search terms — shows criterion proportions per year.",
    },
    {
        "nome":     "results_terms_heatmap",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_terms_heatmap_<lang>.png",
        "descricao_pt": (
            "Heatmap com termos nas linhas e campos (título, resumo, palavras-chave) nas colunas. "
            "Cada célula mostra a % de artigos do corpus criterio_ok em que o termo aparece naquele campo. "
            "Escala de cores YlOrRd (amarelo=baixo, vermelho=alto)."
        ),
        "descricao_en": (
            "Heatmap with terms as rows and fields (title, abstract, keywords) as columns. "
            "Each cell shows the % of criterio_ok corpus articles where the term appears in that field. "
            "YlOrRd color scale (yellow=low, red=high)."
        ),
        "termos_usados_pt": "Todos os termos de busca detectados no CSV (ex: avalia, educa).",
        "termos_usados_en": "All search terms detected in the CSV (e.g.: avalia, educa).",
    },
    {
        "nome":     "results_journals",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_journals_<lang>.png",
        "descricao_pt": (
            "Gráfico de barras horizontais com os top-N periódicos por número de artigos no corpus "
            "criterio_ok. Cada barra exibe n e % em relação ao total criterio_ok. "
            "N configurável via --top-journals (default: 15)."
        ),
        "descricao_en": (
            "Horizontal bar chart with the top-N journals by number of articles in the criterio_ok corpus. "
            "Each bar shows n and % relative to total criterio_ok. "
            "N configurable via --top-journals (default: 15)."
        ),
        "termos_usados_pt": "Nenhum termo diretamente — periódicos dos artigos com criterio_ok=True.",
        "termos_usados_en": "No terms directly — journals of articles with criterio_ok=True.",
    },
    {
        "nome":     "results_coverage",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_coverage_<lang>.png",
        "descricao_pt": (
            "Gráfico de barras agrupadas com % de artigos que possuem cada campo PT preenchido "
            "(título PT, resumo PT, palavras-chave PT), por ano. "
            "Mostra a qualidade da extração de metadados em português."
        ),
        "descricao_en": (
            "Grouped bar chart with % of articles that have each PT field filled "
            "(PT title, PT abstract, PT keywords), per year. "
            "Shows the quality of Portuguese-language metadata extraction."
        ),
        "termos_usados_pt": "Nenhum termo — mostra presença/ausência de campos PT extraídos.",
        "termos_usados_en": "No terms — shows presence/absence of extracted PT fields.",
    },
    {
        "nome":     "results_table_summary",
        "tipo":     "tabela CSV",
        "arquivo":  "results_table_summary.csv",
        "descricao_pt": (
            "Tabela-resumo do funil de seleção por ano, com linha de totais. "
            "Colunas: ano, total_buscado, total_raspado, ok_completo, ok_parcial, "
            "criterio_ok, criterio_ok_pct."
        ),
        "descricao_en": (
            "Summary table of the selection funnel per year, with totals row. "
            "Columns: year, total retrieved, total scraped, complete OK, partial OK, "
            "criterion met, criterion met %."
        ),
        "termos_usados_pt": "Nenhum termo — contagens absolutas do processo.",
        "termos_usados_en": "No terms — absolute process counts.",
    },
    {
        "nome":     "results_table_terms",
        "tipo":     "tabela CSV",
        "arquivo":  "results_table_terms.csv",
        "descricao_pt": (
            "Tabela de frequência de termos por campo, calculada sobre o corpus criterio_ok. "
            "Colunas: termo, campo, n_criterio_ok, pct_criterio_ok (base: criterio_ok total), "
            "pct_total_raspado (base: todos os artigos raspados)."
        ),
        "descricao_en": (
            "Term frequency table per field, calculated on the criterio_ok corpus. "
            "Columns: term, field, n_criterio_ok, pct_criterio_ok (base: total criterio_ok), "
            "pct_total_scraped (base: all scraped articles)."
        ),
        "termos_usados_pt": "Todos os termos de busca detectados no CSV.",
        "termos_usados_en": "All search terms detected in the CSV.",
    },
    {
        "nome":     "results_table_journals",
        "tipo":     "tabela CSV",
        "arquivo":  "results_table_journals.csv",
        "descricao_pt": (
            "Tabela completa de periódicos com artigos no corpus criterio_ok, ordenada por rank. "
            "Colunas: rank, journal, n_criterio_ok, pct_criterio_ok, anos_presentes. "
            "Inclui todos os periódicos (sem limite), diferente do gráfico results_journals."
        ),
        "descricao_en": (
            "Full table of journals with articles in the criterio_ok corpus, sorted by rank. "
            "Columns: rank, journal, n_criterio_ok, pct_criterio_ok, years_present. "
            "Includes all journals (no limit), unlike the results_journals chart."
        ),
        "termos_usados_pt": "Nenhum termo — periódicos dos artigos com criterio_ok=True.",
        "termos_usados_en": "No terms — journals of articles with criterio_ok=True.",
    },
    {
        "nome":     "results_text",
        "tipo":     "texto Markdown",
        "arquivo":  "results_text_<lang>.md",
        "descricao_pt": (
            "Texto publication-ready com seções de Metodologia, Resultados e Limitações. "
            "Inclui: data da busca, termos, coleção, campos, estratégia de extração, "
            "versões dos scripts, cobertura de extração, análise de termos por campo, "
            "co-ocorrência, periódicos, distribuição por ano e limitações metodológicas."
        ),
        "descricao_en": (
            "Publication-ready text with Methodology, Results, and Limitations sections. "
            "Includes: search date, terms, collection, fields, extraction strategy, "
            "script versions, extraction coverage, term analysis per field, "
            "co-occurrence, journals, yearly distribution, and methodological limitations."
        ),
        "termos_usados_pt": "Todos os termos de busca detectados.",
        "termos_usados_en": "All detected search terms.",
    },
    {
        "nome":     "results_report",
        "tipo":     "metadados JSON",
        "arquivo":  "results_report.json",
        "descricao_pt": (
            "JSON com todos os dados calculados: versão, data de geração, anos, termos, campos, "
            "estatísticas por ano (total_buscado, total_raspado, ok_completo, ok_parcial, "
            "criterio_ok, cobertura_campos, termos_campos, jornais) e totais globais. "
            "Pode ser renderizado em tela com --show-report."
        ),
        "descricao_en": (
            "JSON with all calculated data: version, generation date, years, terms, fields, "
            "per-year statistics (total retrieved, total scraped, complete OK, partial OK, "
            "criterion met, field coverage, term-field counts, journals) and global totals. "
            "Can be rendered on screen with --show-report."
        ),
        "termos_usados_pt": "Todos os termos de busca e campos detectados.",
        "termos_usados_en": "All detected search terms and fields.",
    },
]


def _mostrar_help_artifacts():
    """--help-artifacts: lista resumida de todos os artefatos."""
    print("\nArtefatos gerados por results_report.py\n")
    print(f"  {'Nome':<30} {'Tipo':<18} {'Arquivo'}")
    print("  " + "-" * 75)
    for a in ARTEFATOS_CATALOGO:
        print(f"  {a['nome']:<30} {a['tipo']:<18} {a['arquivo']}")
    print()
    print("Use --help-artifact <nome> para descrição detalhada de cada artefato.")
    print("Use --lang para escolher idioma dos artefatos: pt (default) | en | all\n")


def _mostrar_help_artifact(nome: str):
    """--help-artifact <nome>: descrição detalhada de um artefato."""
    artefato = next((a for a in ARTEFATOS_CATALOGO if a["nome"] == nome), None)
    if artefato is None:
        nomes = [a["nome"] for a in ARTEFATOS_CATALOGO]
        print(f"❌  Artefato '{nome}' não encontrado.", file=sys.stderr)
        print(f"    Disponíveis: {', '.join(nomes)}", file=sys.stderr)
        sys.exit(1)
    print(f"\n{'=' * 60}")
    print(f"  {artefato['nome']}")
    print(f"{'=' * 60}")
    print(f"  Tipo    : {artefato['tipo']}")
    print(f"  Arquivo : {artefato['arquivo']}")
    print()
    print("  [PT-BR]")
    print(f"  {artefato['descricao_pt']}")
    print(f"  Termos usados: {artefato['termos_usados_pt']}")
    print()
    print("  [EN]")
    print(f"  {artefato['descricao_en']}")
    print(f"  Terms used: {artefato['termos_usados_en']}")
    print()


def _mostrar_show_report(path: Path):
    """--show-report: renderiza results_report.json em formato legível."""
    if not path.exists():
        print(f"❌  Arquivo não encontrado: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    versao    = data.get("versao", "?")
    gerado_em = data.get("gerado_em", "?")
    anos      = data.get("anos", [])
    termos    = data.get("termos", [])
    campos    = data.get("campos", [])
    por_ano   = data.get("por_ano", {})
    totais    = data.get("totais", {})

    print(f"\n{'═' * 64}")
    print(f"  results_report.json  —  v{versao}  —  {gerado_em[:16].replace('T', ' ')}")
    print(f"{'═' * 64}")
    print(f"  Anos    : {', '.join(str(a) for a in anos)}")
    print(f"  Termos  : {', '.join(termos)}")
    print(f"  Campos  : {', '.join(campos)}")

    print(f"\n{'─' * 64}")
    print("  RESUMO POR ANO")
    print(f"{'─' * 64}")
    print(f"  {'Ano':<6} {'Buscado':>8} {'Raspado':>10} {'Ok compl':>9} {'Ok parc':>8} {'Critério':>9} {'%':>7}")
    print(f"  {'-'*6} {'-'*8} {'-'*10} {'-'*9} {'-'*8} {'-'*9} {'-'*7}")
    for ano_str, v in sorted(por_ano.items()):
        pct = v.get("criterio_ok_pct", 0)
        print(
            f"  {ano_str:<6} "
            f"{v.get('total_buscado', 0):>8} "
            f"{v.get('total_scrapeado', 0):>10} "
            f"{v.get('ok_completo', 0):>9} "
            f"{v.get('ok_parcial', 0):>8} "
            f"{v.get('criterio_ok', 0):>9} "
            f"{pct:>6.1f}%"
        )
    if len(anos) > 1:
        tc = totais.get("criterio_ok_pct", 0)
        print(f"  {'TOTAL':<6} "
              f"{totais.get('total_buscado', 0):>8} "
              f"{totais.get('total_scrapeado', 0):>10} "
              f"{'':>9} "
              f"{'':>8} "
              f"{totais.get('criterio_ok', 0):>9} "
              f"{tc:>6.1f}%")

    print(f"\n{'─' * 64}")
    print("  TERMOS × CAMPOS  (base: criterio_ok, % de artigos)")
    print(f"{'─' * 64}")
    tc_data = totais.get("termos_campos", {})
    total_ok = totais.get("criterio_ok", 1) or 1
    col_w = max((len(c) for c in campos), default=8) + 2
    header = f"  {'Termo':<14}" + "".join(f"{c:>{col_w}}" for c in campos)
    print(header)
    print(f"  {'-'*14}" + "-" * (col_w * len(campos)))
    for termo in termos:
        linha = f"  {termo:<14}"
        for campo in campos:
            n = tc_data.get(termo, {}).get(campo, 0)
            pct = n / total_ok * 100
            linha += f"{pct:>{col_w-1}.1f}%"
        print(linha)

    print(f"\n{'─' * 64}")
    print("  TOP 10 PERIÓDICOS  (criterio_ok)")
    print(f"{'─' * 64}")
    jornais = sorted(totais.get("jornais", {}).items(), key=lambda x: x[1], reverse=True)[:10]
    for rank, (j, n) in enumerate(jornais, 1):
        pct = n / total_ok * 100
        nome_curto = j[:52] + "…" if len(j) > 52 else j
        print(f"  {rank:>2}. {nome_curto:<54} {n:>3} ({pct:.1f}%)")

    print(f"\n{'═' * 64}\n")


# ---------------------------------------------------------------------------
# Descoberta de pastas e CSVs
# ---------------------------------------------------------------------------

MODO_SUFIXO = {
    "api+html": re.compile(r"_api\+html$"),
    "api":      re.compile(r"_api$"),
    "html":     re.compile(r"_html$"),
}


def descobrir_anos(base: Path) -> list[int]:
    return sorted(int(p.name) for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def descobrir_pasta_modo(ano_dir: Path, modo: str) -> Path | None:
    padrao = MODO_SUFIXO[modo]
    candidatas = [
        p for p in ano_dir.iterdir()
        if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
    ]
    return sorted(candidatas)[-1] if candidatas else None


def descobrir_terms_csv(pasta: Path) -> Path | None:
    """Retorna o terms_*.csv mais recente dentro de uma pasta de scraping."""
    candidatas = sorted(pasta.glob("terms_*.csv"), reverse=True)
    candidatas = [p for p in candidatas if not p.name.endswith("_stats.json")]
    return candidatas[0] if candidatas else None


def carregar_stats_json(pasta: Path) -> dict:
    p = pasta / "stats.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def carregar_params_json(ano_dir: Path) -> dict:
    """Tenta ler o sc_*_params.json mais recente em ano_dir."""
    candidatas = sorted(ano_dir.glob("sc_*_params.json"), reverse=True)
    if not candidatas:
        return {}
    try:
        with open(candidatas[0], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Leitura do CSV de termos
# ---------------------------------------------------------------------------

def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def carregar_terms_csv(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def detectar_termos_e_campos(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Detecta termos e campos a partir das colunas booleanas do CSV."""
    if not rows:
        return [], []
    colunas = list(rows[0].keys())
    campos_possiveis = ["titulo", "resumo", "keywords"]
    termos: list[str] = []
    campos_encontrados: set[str] = set()
    for col in colunas:
        for campo in campos_possiveis:
            if col.endswith(f"_{campo}"):
                termo = col[: -(len(campo) + 1)]
                if termo and termo not in ("n_palavras", "n"):
                    if termo not in termos:
                        termos.append(termo)
                    campos_encontrados.add(campo)
    campos = [c for c in campos_possiveis if c in campos_encontrados]
    return termos, campos


# ---------------------------------------------------------------------------
# Cálculo de estatísticas
# ---------------------------------------------------------------------------

def calcular_stats(
    rows_por_ano: dict[int, list[dict]],
    termos: list[str],
    campos: list[str],
    params_por_ano: dict[int, dict],
    stats_json_por_ano: dict[int, dict],
) -> dict:
    """
    Retorna dict com todas as estatísticas necessárias para os artefatos.
    """
    anos = sorted(rows_por_ano)

    por_ano: dict[int, dict] = {}
    for ano in anos:
        rows = rows_por_ano[ano]
        total = len(rows)
        criterio_ok = sum(1 for r in rows if _bool(r.get("criterio_ok", "False")))
        ok_completo = sum(1 for r in rows if r.get("status", "") == "ok_completo")
        ok_parcial  = sum(1 for r in rows if r.get("status", "") == "ok_parcial")

        # Campos presentes (não-vazios)
        campo_col = {
            "titulo":   "Titulo_PT",
            "resumo":   "Resumo_PT",
            "keywords": "Palavras_Chave_PT",
        }
        cobertura_campos: dict[str, int] = {}
        for campo, col in campo_col.items():
            cobertura_campos[campo] = sum(1 for r in rows if r.get(col, "").strip())

        # Termos × campos (base: criterio_ok=True)
        rows_ok = [r for r in rows if _bool(r.get("criterio_ok", "False"))]
        termos_campos: dict[str, dict[str, int]] = {}
        for termo in termos:
            termos_campos[termo] = {}
            for campo in campos:
                col = f"{termo}_{campo}"
                termos_campos[termo][campo] = sum(1 for r in rows_ok if _bool(r.get(col, "False")))

        # Co-ocorrência por campo (artigos onde TODOS os termos aparecem no mesmo campo)
        coocorrencia: dict[str, int] = {}
        for campo in campos:
            coocorrencia[campo] = sum(
                1 for r in rows_ok
                if all(_bool(r.get(f"{t}_{campo}", "False")) for t in termos)
            )

        # Periódicos (base: criterio_ok=True)
        jornais: dict[str, int] = defaultdict(int)
        for r in rows_ok:
            j = r.get("Journal", r.get("Source", "")).strip()
            if j:
                jornais[j] += 1

        # Total buscado — do params.json ou fallback para len(rows)
        params = params_por_ano.get(ano, {})
        stats_j = stats_json_por_ano.get(ano, {})
        total_buscado    = params.get("total_resultados", total)
        termos_busca     = params.get("termos_originais", termos)
        colecao          = params.get("colecao", "scl")
        truncamento      = params.get("truncamento", True)
        campos_busca     = params.get("campos", "ti+ab")
        data_busca       = params.get("timestamp", "")
        versao_searcher  = params.get("versao", "")
        versao_scraper   = stats_j.get("versao_scraper", "")
        tempo_scraping   = stats_j.get("tempo_total_segundos", None)
        erros_extracao   = {
            k: v for k, v in stats_j.get("por_status", {}).items()
            if k not in ("ok_completo", "ok_parcial")
        } if stats_j.get("por_status") else {}
        taxa_sucesso     = stats_j.get("taxa_sucesso_pct", None)

        por_ano[ano] = {
            "total_buscado":    total_buscado,
            "total_scrapeado":  total,
            "ok_completo":      ok_completo,
            "ok_parcial":       ok_parcial,
            "criterio_ok":      criterio_ok,
            "criterio_ok_pct":  criterio_ok / total * 100 if total else 0,
            "cobertura_campos": cobertura_campos,
            "termos_campos":    termos_campos,
            "coocorrencia":     coocorrencia,
            "jornais":          dict(jornais),
            "termos_busca":     termos_busca,
            "colecao":          colecao,
            "truncamento":      truncamento,
            "campos_busca":     campos_busca,
            "data_busca":       data_busca,
            "versao_searcher":  versao_searcher,
            "versao_scraper":   versao_scraper,
            "tempo_scraping":   tempo_scraping,
            "erros_extracao":   erros_extracao,
            "taxa_sucesso":     taxa_sucesso,
        }

    # Totais globais
    total_b = sum(v["total_buscado"]   for v in por_ano.values())
    total_s = sum(v["total_scrapeado"] for v in por_ano.values())
    total_c = sum(v["criterio_ok"]     for v in por_ano.values())
    total_r = sum(v["total_scrapeado"] for v in por_ano.values())

    jornais_global: dict[str, int] = defaultdict(int)
    termos_campos_global: dict[str, dict[str, int]] = {t: {c: 0 for c in campos} for t in termos}
    coocorrencia_global: dict[str, int] = {c: 0 for c in campos}
    for v in por_ano.values():
        for j, n in v["jornais"].items():
            jornais_global[j] += n
        for t in termos:
            for c in campos:
                termos_campos_global[t][c] += v["termos_campos"].get(t, {}).get(c, 0)
        for c in campos:
            coocorrencia_global[c] += v["coocorrencia"].get(c, 0)

    return {
        "versao":          __version__,
        "gerado_em":       datetime.now().isoformat(),
        "anos":            anos,
        "termos":          termos,
        "campos":          campos,
        "por_ano":         por_ano,
        "totais": {
            "total_buscado":   total_b,
            "total_scrapeado": total_s,
            "criterio_ok":     total_c,
            "criterio_ok_pct": total_c / total_r * 100 if total_r else 0,
            "jornais":         dict(jornais_global),
            "termos_campos":   termos_campos_global,
            "coocorrencia":    coocorrencia_global,
        },
    }


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------

CORES_FUNNEL = ["#2980b9", "#27ae60", "#e67e22"]
CORES_CAMPOS = {"titulo": "#3498db", "resumo": "#2ecc71", "keywords": "#e67e22"}
CORES_ANOS   = ["#2980b9", "#27ae60", "#e67e22", "#8e44ad", "#c0392b",
                 "#16a085", "#d35400", "#2c3e50"]


def grafico_funnel(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):
    anos = stats["anos"]
    por_ano = stats["por_ano"]
    n_anos  = len(anos)

    fig, axes = plt.subplots(1, n_anos, figsize=(4.5 * n_anos, 6), sharey=False)
    if n_anos == 1:
        axes = [axes]
    fig.suptitle(s("titulo_funnel", lang), fontsize=14, fontweight="bold")

    estagios_keys = ["total_buscado", "total_scrapeado", "criterio_ok"]
    estagios_labels = [
        s("funnel_buscado", lang),
        s("funnel_scrapeado", lang),
        s("funnel_criterio", lang),
    ]

    for col, ano in enumerate(anos):
        ax  = axes[col]
        v   = por_ano[ano]
        vals = [v[k] for k in estagios_keys]
        x    = range(len(vals))

        bars = ax.bar(x, vals, color=CORES_FUNNEL, edgecolor="white", linewidth=0.8, zorder=2)
        ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
        ax.set_axisbelow(True)

        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(vals) * 0.01,
                    str(val), ha="center", va="bottom", fontsize=11, fontweight="bold")

        ref = vals[0] if vals[0] else 1
        for i, (bar, val) in enumerate(zip(bars, vals)):
            if i > 0:
                pct = val / ref * 100
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() / 2,
                        f"{pct:.1f}%", ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold")

        ax.set_title(str(ano), fontsize=12, fontweight="bold")
        ax.set_xticks(list(x))
        ax.set_xticklabels(estagios_labels, fontsize=9)
        ax.set_ylabel(s("eixo_n_artigos", lang), fontsize=10)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    fig.text(0.5, -0.03, s("nota_funnel", lang),
             ha="center", fontsize=8.5, color="#666666", style="italic")
    plt.tight_layout()
    dest = output / f"{s('arquivo_funnel', lang)}{lang_suf}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_trend(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]

    vals_ok    = [por_ano[a]["criterio_ok"]     for a in anos]
    vals_total = [por_ano[a]["total_scrapeado"] for a in anos]
    pcts       = [v["criterio_ok_pct"]          for v in [por_ano[a] for a in anos]]

    fig, ax1 = plt.subplots(figsize=(max(7, 2 * len(anos)), 5))
    fig.suptitle(s("titulo_trend", lang), fontsize=13, fontweight="bold")

    x = np.arange(len(anos))
    w = 0.35

    ax1.bar(x - w/2, vals_total, w, label=s("legenda_total_scrapeado", lang),
            color="#bdc3c7", zorder=2)
    ax1.bar(x + w/2, vals_ok,    w, label=s("legenda_criterio_ok", lang),
            color="#27ae60", zorder=2)
    ax1.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax1.set_axisbelow(True)
    ax1.set_ylabel(s("eixo_n_artigos", lang), fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(a) for a in anos], fontsize=11)
    ax1.set_xlabel(s("eixo_ano", lang), fontsize=11)

    ax2 = ax1.twinx()
    ax2.plot(x, pcts, "o--", color="#e74c3c", linewidth=2, markersize=7,
             label=s("legenda_pct_criterio", lang))
    ax2.set_ylabel(s("legenda_pct_criterio", lang), fontsize=11, color="#e74c3c")
    ax2.tick_params(axis="y", labelcolor="#e74c3c")
    ax2.set_ylim(0, 110)

    for xi, pct in zip(x, pcts):
        ax2.text(xi, pct + 3, f"{pct:.1f}%", ha="center", fontsize=9,
                 color="#e74c3c", fontweight="bold")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    # Legenda fora da área do gráfico para evitar colisão com barras
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=3,
        fontsize=9,
        frameon=True,
    )

    plt.tight_layout()
    dest = output / f"{s('arquivo_trend', lang)}{lang_suf}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_heatmap(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):
    termos  = stats["termos"]
    campos  = stats["campos"]
    totais  = stats["totais"]
    total_ok = totais["criterio_ok"]

    if not termos or not campos or total_ok == 0:
        print("  ⚠ Heatmap pulado — sem dados de termos/campos.")
        return

    tc = totais["termos_campos"]
    matriz = np.array([
        [tc.get(t, {}).get(c, 0) / total_ok * 100 for c in campos]
        for t in termos
    ])

    campo_labels = {
        "titulo":   s("campo_titulo", lang),
        "resumo":   s("campo_resumo", lang),
        "keywords": s("campo_keywords", lang),
    }

    fig, ax = plt.subplots(figsize=(max(5, 2.5 * len(campos)), max(4, 1.2 * len(termos))))
    fig.suptitle(s("titulo_heatmap", lang), fontsize=13, fontweight="bold")

    im = ax.imshow(matriz, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label="%", shrink=0.8)

    ax.set_xticks(range(len(campos)))
    ax.set_xticklabels([campo_labels.get(c, c) for c in campos], fontsize=11)
    ax.set_yticks(range(len(termos)))
    ax.set_yticklabels(termos, fontsize=11)
    ax.set_xlabel(s("eixo_campo", lang), fontsize=11)
    ax.set_ylabel(s("eixo_termo", lang), fontsize=11)

    for i in range(len(termos)):
        for j in range(len(campos)):
            val = matriz[i, j]
            cor = "white" if val > 60 else "#333333"
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                    fontsize=11, color=cor, fontweight="bold")

    fig.text(0.5, -0.03, s("nota_heatmap", lang),
             ha="center", fontsize=8.5, color="#666666", style="italic")
    plt.tight_layout()
    dest = output / f"{s('arquivo_heatmap', lang)}{lang_suf}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_journals(stats: dict, output: Path, top_n: int = 15, lang: str = "pt", lang_suf: str = ""):
    jornais = stats["totais"]["jornais"]
    if not jornais:
        print("  ⚠ Gráfico de periódicos pulado — sem dados.")
        return

    total_ok = stats["totais"]["criterio_ok"]
    top = sorted(jornais.items(), key=lambda x: x[1], reverse=True)[:top_n]
    nomes = [t[0] for t in top]
    vals  = [t[1] for t in top]

    nomes_curtos = [n[:55] + "…" if len(n) > 55 else n for n in nomes]

    fig, ax = plt.subplots(figsize=(10, max(5, 0.5 * len(top))))
    fig.suptitle(s("titulo_journals", lang), fontsize=13, fontweight="bold")

    y = np.arange(len(top))
    bars = ax.barh(y, vals, color="#2980b9", edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, vals):
        pct = val / total_ok * 100 if total_ok else 0
        ax.text(bar.get_width() + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val} ({pct:.1f}%)", va="center", fontsize=9)

    ax.set_yticks(y)
    ax.set_yticklabels(nomes_curtos, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel(s("eixo_n_artigos", lang), fontsize=11)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals) * 1.22)

    plt.tight_layout()
    dest = output / f"{s('arquivo_journals', lang)}{lang_suf}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_coverage(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]

    campos_disponiveis = ["titulo", "resumo", "keywords"]
    campo_labels = {
        "titulo":   s("campo_titulo", lang),
        "resumo":   s("campo_resumo", lang),
        "keywords": s("campo_keywords", lang),
    }

    x     = np.arange(len(anos))
    width = 0.25
    n_campos = len(campos_disponiveis)

    fig, ax = plt.subplots(figsize=(max(7, 2 * len(anos)), 5.5))
    fig.suptitle(s("titulo_coverage", lang), fontsize=13, fontweight="bold")

    for i, campo in enumerate(campos_disponiveis):
        pcts = []
        ns   = []
        for ano in anos:
            total = por_ano[ano]["total_scrapeado"]
            n_ok  = por_ano[ano]["cobertura_campos"].get(campo, 0)
            pcts.append(n_ok / total * 100 if total else 0)
            ns.append(n_ok)

        offset = (i - n_campos / 2 + 0.5) * width
        bars = ax.bar(x + offset, pcts, width,
                      label=campo_labels[campo],
                      color=CORES_CAMPOS[campo],
                      edgecolor="white", linewidth=0.5)
        for bar, pct, n_abs in zip(bars, pcts, ns):
            if pct > 3:
                # % acima da barra
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{pct:.1f}%", ha="center", va="bottom", fontsize=7.5,
                        fontweight="bold")
                # n absoluto dentro da barra (centralizado verticalmente)
                if pct > 8:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() / 2,
                            f"n={n_abs}", ha="center", va="center", fontsize=7,
                            color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([str(a) for a in anos], fontsize=11)
    ax.set_xlabel(s("eixo_ano", lang), fontsize=11)
    ax.set_ylabel(s("eixo_pct", lang), fontsize=11)
    ax.set_ylim(0, 122)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)
    # Legenda abaixo do gráfico para evitar colisão com as barras
    ax.legend(
        title=s("legenda_campo", lang),
        fontsize=10,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=n_campos,
        frameon=True,
    )

    plt.tight_layout()
    dest = output / f"{s('arquivo_coverage', lang)}{lang_suf}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Tabelas CSV
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def salvar_table_summary(stats: dict, output: Path):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]
    totais  = stats["totais"]

    dest = output / "results_table_summary.csv"
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ano", "total_buscado", "total_scrapeado",
                    "ok_completo", "ok_parcial", "criterio_ok", "criterio_ok_pct"])
        for ano in anos:
            v = por_ano[ano]
            w.writerow([
                ano,
                v["total_buscado"],
                v["total_scrapeado"],
                v["ok_completo"],
                v["ok_parcial"],
                v["criterio_ok"],
                _pct(v["criterio_ok"], v["total_scrapeado"]),
            ])
        if len(anos) > 1:
            ts = totais["total_scrapeado"]
            w.writerow([
                f"{anos[0]}-{anos[-1]}",
                totais["total_buscado"],
                ts,
                sum(por_ano[a]["ok_completo"] for a in anos),
                sum(por_ano[a]["ok_parcial"]  for a in anos),
                totais["criterio_ok"],
                _pct(totais["criterio_ok"], ts),
            ])
    print(f"  ✓ {dest}")


def salvar_table_terms(stats: dict, output: Path):
    termos  = stats["termos"]
    campos  = stats["campos"]
    totais  = stats["totais"]
    total_ok = totais["criterio_ok"]
    total_s  = totais["total_scrapeado"]

    dest = output / "results_table_terms.csv"
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["termo", "campo", "n_criterio_ok", "pct_criterio_ok", "pct_total_scrapeado"])
        for termo in termos:
            for campo in campos:
                n = totais["termos_campos"].get(termo, {}).get(campo, 0)
                w.writerow([
                    termo,
                    campo,
                    n,
                    _pct(n, total_ok),
                    _pct(n, total_s),
                ])
    print(f"  ✓ {dest}")


def salvar_table_journals(stats: dict, output: Path):
    jornais  = stats["totais"]["jornais"]
    total_ok = stats["totais"]["criterio_ok"]
    anos     = stats["anos"]
    por_ano  = stats["por_ano"]

    jornal_anos: dict[str, list[int]] = defaultdict(list)
    for ano in anos:
        for j in por_ano[ano]["jornais"]:
            jornal_anos[j].append(ano)

    top = sorted(jornais.items(), key=lambda x: x[1], reverse=True)

    dest = output / "results_table_journals.csv"
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "journal", "n_criterio_ok", "pct_criterio_ok", "anos_presentes"])
        for rank, (jornal, n) in enumerate(top, 1):
            w.writerow([
                rank,
                jornal,
                n,
                _pct(n, total_ok),
                ";".join(str(a) for a in sorted(jornal_anos[jornal])),
            ])
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Texto Markdown
# ---------------------------------------------------------------------------

def _anos_str(anos: list[int], lang: str) -> str:
    """Retorna string dos anos para uso em texto corrido (ex: '2025–2026')."""
    if len(anos) == 1:
        return str(anos[0])
    if anos == list(range(anos[0], anos[-1] + 1)):
        return f"{anos[0]}–{anos[-1]}" if lang == "pt" else f"{anos[0]} to {anos[-1]}"
    return ", ".join(str(a) for a in anos)


def _anos_cobertura_str(anos: list[int], lang: str) -> str:
    """String para 'abrangendo o ano de X' ou 'abrangendo os anos X–Y'."""
    if lang == "pt":
        if len(anos) == 1:
            return f"o ano de {anos[0]}"
        return f"os anos {_anos_str(anos, lang)}"
    else:
        if len(anos) == 1:
            return f"the year {anos[0]}"
        return f"the years {_anos_str(anos, lang)}"


def _formato_data_busca(ts: str, lang: str) -> str:
    """Formata timestamp ISO (ou YYYYMMDD_HHMMSS) para data legível."""
    if not ts:
        return ""
    MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    dt = None
    try:
        dt = datetime.fromisoformat(ts[:19])
    except Exception:
        pass
    if dt is None:
        try:
            dt = datetime.strptime(ts[:15], "%Y%m%d_%H%M%S")
        except Exception:
            pass
    if dt is None:
        return ts
    if lang == "pt":
        return f"{dt.day} de {MESES_PT[dt.month - 1]} de {dt.year}"
    return dt.strftime("%B %d, %Y")


def _formato_tempo(segundos) -> str:
    """Formata segundos em string legível (ex: 2h 15min ou 3min 42s)."""
    if segundos is None:
        return ""
    try:
        seg = int(float(segundos))
    except (ValueError, TypeError):
        return ""
    if seg >= 3600:
        h, resto = divmod(seg, 3600)
        m = resto // 60
        return f"{h}h {m}min"
    if seg >= 60:
        m, sec = divmod(seg, 60)
        return f"{m}min {sec}s"
    return f"{seg}s"


def gerar_texto(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]
    totais  = stats["totais"]
    termos  = stats["termos"]
    campos  = stats["campos"]

    primeiro_ano_v = por_ano[anos[0]]
    termos_busca  = primeiro_ano_v.get("termos_busca", termos)
    colecao       = primeiro_ano_v.get("colecao", "scl")
    truncamento   = primeiro_ano_v.get("truncamento", True)
    campos_busca  = primeiro_ano_v.get("campos_busca", "ti+ab")
    data_busca_ts = primeiro_ano_v.get("data_busca", "")
    versao_searcher = primeiro_ano_v.get("versao_searcher", "")
    versao_scraper  = primeiro_ano_v.get("versao_scraper", "")

    anos_str  = _anos_str(anos, lang)
    total_b   = totais["total_buscado"]
    total_s   = totais["total_scrapeado"]
    total_ok  = totais["criterio_ok"]
    pct_ok    = totais["criterio_ok_pct"]

    # Tempo total de scraping (soma dos anos)
    tempo_total_s = sum(
        v.get("tempo_scraping") or 0 for v in por_ano.values()
        if v.get("tempo_scraping") is not None
    )
    tempo_str = _formato_tempo(tempo_total_s) if tempo_total_s > 0 else ""

    # Taxa de sucesso média
    taxas = [v.get("taxa_sucesso") for v in por_ano.values() if v.get("taxa_sucesso") is not None]
    taxa_media = sum(taxas) / len(taxas) if taxas else None

    # Erros de extração globais
    erros_global: dict[str, int] = defaultdict(int)
    for v in por_ano.values():
        for k, n in v.get("erros_extracao", {}).items():
            erros_global[k] += n

    # Top 3 periódicos
    top3 = sorted(totais["jornais"].items(), key=lambda x: x[1], reverse=True)[:3]

    # Análise de termos globais
    tc_global = totais["termos_campos"]
    cooc_global = totais.get("coocorrencia", {})

    # Distribuição por ano
    por_ano_str_list = [
        f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
        for a in anos
    ]

    # ---- helpers de formatação ----
    def _fmt_termos_busca(sep: str) -> str:
        return sep.join(f'"{t}"' for t in termos_busca)

    def _fmt_campos_busca(cb: str, l: str) -> str:
        if l == "pt":
            return {"ti+ab": "título e resumo", "ti": "título", "ab": "resumo"}.get(cb, cb)
        return {"ti+ab": "title and abstract", "ti": "title", "ab": "abstract"}.get(cb, cb)

    def _fmt_colecao(col: str, l: str) -> str:
        if l == "pt":
            return {"scl": "SciELO Brasil", "arg": "SciELO Argentina"}.get(col, col)
        return {"scl": "SciELO Brazil", "arg": "SciELO Argentina"}.get(col, col)

    # Monta descrição da data
    data_fmt = _formato_data_busca(data_busca_ts, lang)

    # ---- Seção: Artefatos ----
    def _gerar_artefatos_section(l: str) -> str:
        linhas = []
        if l == "pt":
            linhas.append("### Gráficos\n")
            linhas.append("| Arquivo | Descrição |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "gráfico" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_pt'].split('.')[0]}. |")
            linhas.append("\n### Tabelas\n")
            linhas.append("| Arquivo | Descrição |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "tabela" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_pt'].split('.')[0]}. |")
            linhas.append("\n### Texto e Metadados\n")
            linhas.append("| Arquivo | Descrição |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "texto" in a["tipo"] or "metadados" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_pt'].split('.')[0]}. |")
        else:
            linhas.append("### Charts\n")
            linhas.append("| File | Description |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "gráfico" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_en'].split('.')[0]}. |")
            linhas.append("\n### Tables\n")
            linhas.append("| File | Description |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "tabela" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_en'].split('.')[0]}. |")
            linhas.append("\n### Text and Metadata\n")
            linhas.append("| File | Description |")
            linhas.append("|---|---|")
            for a in ARTEFATOS_CATALOGO:
                if "texto" in a["tipo"] or "metadados" in a["tipo"]:
                    linhas.append(f"| `{a['arquivo']}` | {a['descricao_en'].split('.')[0]}. |")
        return "\n".join(linhas)

    # ---- PT-BR ----
    if lang == "pt":
        trunc_str = " com truncamento automático (operador $)" if truncamento else ""
        cbf = _fmt_campos_busca(campos_busca, "pt")
        colf = _fmt_colecao(colecao, "pt")
        termos_fmt = _fmt_termos_busca(" e ")
        data_str = f", conduzida em {data_fmt}," if data_fmt else ""

        # Versões
        ver_parts = []
        if versao_searcher:
            ver_parts.append(f"scielo_search.py v{versao_searcher}")
        if versao_scraper:
            ver_parts.append(f"scielo_scraper.py v{versao_scraper}")
        ver_str = f" ({'; '.join(ver_parts)})" if ver_parts else ""

        # Cobertura
        ok_compl_total = sum(v["ok_completo"] for v in por_ano.values())
        ok_parc_total  = sum(v["ok_parcial"]  for v in por_ano.values())
        cob_str = f"{ok_compl_total} artigos com extração completa (título + resumo + palavras-chave)"
        if ok_parc_total:
            cob_str += f" e {ok_parc_total} com extração parcial"

        # Tempo
        tempo_part = f" O tempo total de extração foi de {tempo_str}." if tempo_str else ""

        # Taxa sucesso
        taxa_part = f" A taxa de sucesso de extração foi de {taxa_media:.1f}%." if taxa_media is not None else ""

        cob_anos_str = _anos_cobertura_str(anos, "pt")
        metodologia = f"""\
A busca bibliográfica{data_str} foi realizada na plataforma SciELO ({colf}), \
utilizando os termos {termos_fmt}{trunc_str}, \
nos campos de {cbf}, \
abrangendo {cob_anos_str}. \
Foram recuperados {total_b} registros. \
Os metadados em português (título, resumo e palavras-chave) foram extraídos \
por meio do script SciELO Scraper (estratégia api+html){ver_str}, \
resultando em {cob_str}. \
{total_s} artigos tiveram dados disponíveis para análise.{tempo_part}{taxa_part} \
A etapa de filtragem automática verificou a presença simultânea de todos os termos \
em pelo menos um dos campos requeridos (título ou palavras-chave), \
identificando {total_ok} artigos ({pct_ok:.1f}%) como potencialmente relevantes \
para curadoria humana."""

        # --- Resultados ---
        # Distribuição anual
        dist_str = "; ".join(por_ano_str_list)

        # Termos × campos — análise detalhada
        termos_analise_parts = []
        for t in termos:
            partes_t = []
            for c in campos:
                n = tc_global.get(t, {}).get(c, 0)
                pct = n / total_ok * 100 if total_ok else 0
                label_c, prep_c = {
                    "titulo":   ("título", "no"),
                    "resumo":   ("resumo", "no"),
                    "keywords": ("palavras-chave", "nas"),
                }.get(c, (c, "no"))
                partes_t.append(f"{n} ({pct:.1f}%) {prep_c} {label_c}")
            termos_analise_parts.append(
                f'O termo "{t}" foi identificado em: ' + "; ".join(partes_t) + "."
            )
        termos_analise = " ".join(termos_analise_parts)

        # Co-ocorrência
        cooc_parts = []
        for c in campos:
            n_c = cooc_global.get(c, 0)
            if n_c > 0:
                pct_c = n_c / total_ok * 100
                label_c, prep_c = {
                    "titulo":   ("título", "no"),
                    "resumo":   ("resumo", "no"),
                    "keywords": ("palavras-chave", "nas"),
                }.get(c, (c, "no"))
                cooc_parts.append(f"{n_c} ({pct_c:.1f}%) {prep_c} {label_c}")
        cooc_str = ""
        if cooc_parts:
            cooc_str = (
                f"A co-ocorrência simultânea de todos os termos foi verificada em: "
                + "; ".join(cooc_parts) + ". "
            )

        # Periódicos
        top3_str = "; ".join(f"{j} (n={n})" for j, n in top3)
        n_journals_total = len(totais["jornais"])

        resultados = f"""\
Dos {total_s} artigos recuperados e processados, \
{total_ok} ({pct_ok:.1f}%) atenderam ao critério de filtragem automática \
e foram encaminhados para verificação humana pelo grupo de pesquisa. \
"""
        if len(anos) > 1:
            resultados += f"A distribuição por ano foi: {dist_str}. "

        resultados += termos_analise + " "
        resultados += cooc_str

        if top3:
            resultados += (
                f"Os artigos critério foram identificados em {n_journals_total} periódicos distintos. "
                f"Os periódicos com maior representação foram: {top3_str}. "
            )

        # Limitações
        limitacoes = """\
A busca automatizada com truncamento pode recuperar artigos que contêm os radicais dos \
termos em contextos não relacionados ao tema principal desta revisão, exigindo curadoria humana \
para validação da pertinência. \
A filtragem automática baseia-se exclusivamente na presença simultânea dos termos nos campos \
selecionados (título ou palavras-chave), sem análise semântica ou de contexto. \
A cobertura da plataforma SciELO está limitada a periódicos indexados nessa base, \
não contemplando publicações em outros repositórios (ex: LILACS, PubMed, Scopus). \
Artigos no estágio Ahead of Print (AoP) podem não estar indexados via API e dependem \
de extração por HTML, podendo apresentar menor estabilidade nos metadados. \
A análise de co-ocorrência indica presença dos termos nos mesmos campos, \
mas não garante relação semântica direta entre eles."""

    else:  # EN
        trunc_str = " with automatic truncation ($ operator)" if truncamento else ""
        cbf = _fmt_campos_busca(campos_busca, "en")
        colf = _fmt_colecao(colecao, "en")
        termos_fmt = _fmt_termos_busca(" and ")
        data_str = f", conducted on {data_fmt}," if data_fmt else ""

        ver_parts = []
        if versao_searcher:
            ver_parts.append(f"scielo_search.py v{versao_searcher}")
        if versao_scraper:
            ver_parts.append(f"scielo_scraper.py v{versao_scraper}")
        ver_str = f" ({'; '.join(ver_parts)})" if ver_parts else ""

        ok_compl_total = sum(v["ok_completo"] for v in por_ano.values())
        ok_parc_total  = sum(v["ok_parcial"]  for v in por_ano.values())
        cob_str = f"{ok_compl_total} articles with complete extraction (title + abstract + keywords)"
        if ok_parc_total:
            cob_str += f" and {ok_parc_total} with partial extraction"

        tempo_part = f" Total extraction time was {tempo_str}." if tempo_str else ""
        taxa_part = f" Extraction success rate was {taxa_media:.1f}%." if taxa_media is not None else ""

        cob_anos_str_en = _anos_cobertura_str(anos, "en")
        metodologia = f"""\
The bibliographic search{data_str} was conducted on the {colf} platform, \
using the terms {termos_fmt}{trunc_str}, \
in the {cbf} fields, \
covering {cob_anos_str_en}. \
A total of {total_b} records were retrieved. \
Portuguese-language metadata (title, abstract, and keywords) were extracted \
using the SciELO Scraper script (api+html strategy){ver_str}, \
resulting in {cob_str}. \
{total_s} articles had data available for analysis.{tempo_part}{taxa_part} \
The automatic filtering step verified the simultaneous presence of all terms \
in at least one required field (title or keywords), \
identifying {total_ok} articles ({pct_ok:.1f}%) as potentially relevant \
for human curation."""

        dist_str = "; ".join(por_ano_str_list)

        termos_analise_parts = []
        for t in termos:
            partes_t = []
            for c in campos:
                n = tc_global.get(t, {}).get(c, 0)
                pct = n / total_ok * 100 if total_ok else 0
                label_c = {"titulo": "title", "resumo": "abstract", "keywords": "keywords"}.get(c, c)
                partes_t.append(f"{n} ({pct:.1f}%) in the {label_c}")
            termos_analise_parts.append(
                f'The term "{t}" was identified in: ' + "; ".join(partes_t) + "."
            )
        termos_analise = " ".join(termos_analise_parts)

        cooc_parts = []
        for c in campos:
            n_c = cooc_global.get(c, 0)
            if n_c > 0:
                pct_c = n_c / total_ok * 100
                label_c = {"titulo": "title", "resumo": "abstract", "keywords": "keywords"}.get(c, c)
                cooc_parts.append(f"{n_c} ({pct_c:.1f}%) in the {label_c}")
        cooc_str = ""
        if cooc_parts:
            cooc_str = (
                "Simultaneous co-occurrence of all terms was found in: "
                + "; ".join(cooc_parts) + ". "
            )

        top3_str = "; ".join(f"{j} (n={n})" for j, n in top3)
        n_journals_total = len(totais["jornais"])

        resultados = f"""\
Of the {total_s} articles retrieved and processed, \
{total_ok} ({pct_ok:.1f}%) met the automatic filtering criterion \
and were forwarded for human review by the research group. \
"""
        if len(anos) > 1:
            resultados += f"Annual distribution: {dist_str}. "

        resultados += termos_analise + " "
        resultados += cooc_str

        if top3:
            resultados += (
                f"The criterion articles were identified across {n_journals_total} distinct journals. "
                f"The journals with the highest representation were: {top3_str}. "
            )

        limitacoes = """\
Automated searching with truncation may retrieve articles containing the term stems in contexts \
unrelated to the main topic of this review, requiring human curation to validate relevance. \
The automatic filtering is based solely on the simultaneous presence of terms in selected fields \
(title or keywords), without semantic or contextual analysis. \
SciELO platform coverage is limited to journals indexed in this database, \
and does not include publications in other repositories (e.g., LILACS, PubMed, Scopus). \
Articles in Ahead of Print (AoP) status may not be indexed via the API and rely on HTML extraction, \
which may result in lower metadata stability. \
Co-occurrence analysis indicates the presence of terms in the same fields, \
but does not guarantee a direct semantic relationship between them."""

    # Seção de artefatos
    artefatos_section = _gerar_artefatos_section(lang)

    dest = output / f"results_text{lang_suf}.md"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(f"<!-- Gerado por results_report.py v{__version__} em {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n\n")
        f.write(s("sec_metodologia", lang) + "\n\n")
        f.write(metodologia + "\n\n")
        f.write(s("sec_resultados", lang) + "\n\n")
        f.write(resultados.strip() + "\n\n")
        f.write(s("sec_limitacoes", lang) + "\n\n")
        f.write(limitacoes + "\n\n")
        f.write(s("sec_artefatos", lang) + "\n\n")
        f.write(artefatos_section + "\n")
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# JSON de metadados
# ---------------------------------------------------------------------------

def salvar_json(stats: dict, output: Path):
    dest = output / "results_report.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Alias -? → --help
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    # --help-artifacts: antes do parser para não conflitar
    if "--help-artifacts" in sys.argv:
        _mostrar_help_artifacts()
        sys.exit(0)

    # --help-artifact <nome>
    if "--help-artifact" in sys.argv:
        idx = sys.argv.index("--help-artifact")
        if idx + 1 >= len(sys.argv):
            print("❌  --help-artifact requer um nome de artefato.", file=sys.stderr)
            print(f"    Disponíveis: {', '.join(a['nome'] for a in ARTEFATOS_CATALOGO)}", file=sys.stderr)
            sys.exit(1)
        _mostrar_help_artifact(sys.argv[idx + 1])
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description=(
            "Gera artefatos científicos publication-ready do projeto e-Aval.\n"
            "Lê o terms_*.csv produzido pelo terms_matcher.py."
        ),
        epilog="Exemplo: uv run python results_report.py --years 2022 2023 2024 2025",
    )
    parser.add_argument(
        "--base", default=None, metavar="DIR",
        help="Pasta raiz com subpastas por ano (default: runs/)",
    )
    parser.add_argument(
        "--years", nargs="+", type=int, metavar="YEAR",
        help="Anos a incluir (default: todos os encontrados em --base)",
    )
    parser.add_argument(
        "--mode", default="api+html", choices=["api+html", "api", "html"], metavar="MODO",
        help="Estratégia de scraping cujo terms_*.csv será lido (default: api+html)",
    )
    parser.add_argument(
        "--scrape-dir", default=None, metavar="DIR",
        help="Pasta de scraping direta (ex: sc_<ts>_s_<ts>_api+html/). "
             "Ignora --base/--years/--mode e lê o terms_*.csv desta pasta.",
    )
    parser.add_argument(
        "--output-dir", default=None, metavar="DIR",
        help="Pasta de saída explícita. Se omitido, cria results_<stem>/ dentro da pasta do run.",
    )
    parser.add_argument(
        "--lang", default="pt", choices=["pt", "en", "all"], metavar="LANG",
        help="Idioma dos artefatos: pt (default) | en | all",
    )
    parser.add_argument(
        "--top-journals", type=int, default=15, metavar="N",
        help="Número de periódicos no gráfico de periódicos (default: 15)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra o que faria sem gravar nenhum arquivo",
    )
    parser.add_argument(
        "--show-report", default=None, metavar="JSON",
        nargs="?", const="results_report.json",
        help="Renderiza results_report.json em formato legível. "
             "Aceita caminho opcional (default: results_report.json no diretório atual).",
    )
    parser.add_argument(
        "--help-artifacts", action="store_true",
        help="Lista resumida de todos os artefatos gerados.",
    )
    parser.add_argument(
        "--help-artifact", metavar="NOME",
        help="Descrição detalhada de um artefato específico.",
    )
    args = parser.parse_args()

    # --show-report (modo standalone)
    if args.show_report is not None:
        _mostrar_show_report(Path(args.show_report))
        return

    langs_a_gerar = IDIOMAS_DISPONIVEIS if args.lang == "all" else [args.lang]

    # Carregar dados por ano
    rows_por_ano:       dict[int, list[dict]] = {}
    params_por_ano:     dict[int, dict]       = {}
    stats_json_por_ano: dict[int, dict]       = {}
    stem_por_ano:       dict[int, str]        = {}

    if args.scrape_dir:
        pasta = Path(args.scrape_dir)
        if not pasta.is_dir():
            print(f"❌  Pasta '{pasta}' não encontrada.", file=sys.stderr)
            sys.exit(1)
        terms_csv = descobrir_terms_csv(pasta)
        if terms_csv is None:
            print(f"❌  Nenhum terms_*.csv em '{pasta}'.", file=sys.stderr)
            sys.exit(1)
        rows = carregar_terms_csv(terms_csv)
        if not rows:
            print(f"❌  {terms_csv.name} está vazio.", file=sys.stderr)
            sys.exit(1)
        params_cand = sorted(pasta.parent.glob("sc_*_params.json"), reverse=True)
        params_data = {}
        if params_cand:
            try:
                with open(params_cand[0], encoding="utf-8") as f:
                    params_data = json.load(f)
            except Exception:
                pass
        anos_dados = params_data.get("anos", [])
        if not anos_dados:
            anos_set: set[int] = set()
            for r in rows:
                yr = r.get("Publication year", "").strip()
                if yr.isdigit():
                    anos_set.add(int(yr))
            anos_dados = sorted(anos_set) if anos_set else [0]
        ano_key = anos_dados[0]
        rows_por_ano[ano_key]       = rows
        params_por_ano[ano_key]     = params_data
        try:
            stats_json_por_ano[ano_key] = carregar_stats_json(pasta)
        except FileNotFoundError:
            stats_json_por_ano[ano_key] = {}
        stem_por_ano[ano_key] = pasta.name
        if len(anos_dados) > 1:
            rows_por_ano.clear()
            for ano in anos_dados:
                rows_ano = [r for r in rows
                            if r.get("Publication year", "").strip() == str(ano)]
                if rows_ano:
                    rows_por_ano[ano]       = rows_ano
                    params_por_ano[ano]     = params_data
                    stats_json_por_ano[ano] = stats_json_por_ano.get(ano_key, {})
                    stem_por_ano[ano]       = pasta.name
    else:
        base = Path(args.base) if args.base else Path("runs")
        if not base.is_dir():
            print(f"❌  Pasta base '{base}' não encontrada.", file=sys.stderr)
            sys.exit(1)

        anos = args.years if args.years else descobrir_anos(base)
        if not anos:
            print(f"❌  Nenhum ano encontrado em '{base}'.", file=sys.stderr)
            sys.exit(1)

        for ano in anos:
            ano_dir = base / str(ano)
            if not ano_dir.is_dir():
                print(f"  Aviso: pasta '{ano_dir}' não encontrada — ano {ano} ignorado.")
                continue

            pasta = descobrir_pasta_modo(ano_dir, args.mode)
            if pasta is None:
                print(f"  Aviso: nenhuma pasta '{args.mode}' em {ano_dir} — ano {ano} ignorado.")
                continue

            terms_csv = descobrir_terms_csv(pasta)
            if terms_csv is None:
                print(f"  Aviso: nenhum terms_*.csv em {pasta} — ano {ano} ignorado.")
                continue

            rows = carregar_terms_csv(terms_csv)
            if not rows:
                print(f"  Aviso: {terms_csv.name} vazio — ano {ano} ignorado.")
                continue

            rows_por_ano[ano]       = rows
            params_por_ano[ano]     = carregar_params_json(ano_dir)
            try:
                stats_json_por_ano[ano] = carregar_stats_json(pasta)
            except FileNotFoundError:
                stats_json_por_ano[ano] = {}
            stem_por_ano[ano]       = pasta.name

    if not rows_por_ano:
        print("❌  Nenhum dado carregado. Verifique se o terms_matcher.py foi executado.", file=sys.stderr)
        sys.exit(1)

    todas_rows = [r for rows in rows_por_ano.values() for r in rows]
    termos, campos = detectar_termos_e_campos(todas_rows)

    print(f"\nAnos carregados  : {sorted(rows_por_ano)}")
    print(f"Modo             : {args.mode}")
    print(f"Termos detectados: {termos}")
    print(f"Campos detectados: {campos}")
    print(f"Idioma(s)        : {', '.join(langs_a_gerar)}")

    stats = calcular_stats(rows_por_ano, termos, campos, params_por_ano, stats_json_por_ano)

    # Determinar pasta de saída
    if args.output_dir:
        output = Path(args.output_dir)
    elif args.scrape_dir:
        pasta_sd = Path(args.scrape_dir)
        output = pasta_sd.parent / f"results_{pasta_sd.name}"
    else:
        ultimo_ano = sorted(rows_por_ano)[-1]
        stem = stem_por_ano[ultimo_ano]
        output = base / str(ultimo_ano) / f"results_{stem}"

    print(f"Pasta de saída   : {output.resolve()}")

    # Sufixo de idioma: sempre _<lang> (ex: _pt, _en)
    artefatos = []
    for lang in langs_a_gerar:
        lang_suf = f"_{lang}"
        artefatos += [
            f"{s('arquivo_funnel',   lang)}{lang_suf}.png",
            f"{s('arquivo_trend',    lang)}{lang_suf}.png",
            f"{s('arquivo_heatmap',  lang)}{lang_suf}.png",
            f"{s('arquivo_journals', lang)}{lang_suf}.png",
            f"{s('arquivo_coverage', lang)}{lang_suf}.png",
            f"results_text{lang_suf}.md",
        ]
    artefatos += [
        "results_table_summary.csv",
        "results_table_terms.csv",
        "results_table_journals.csv",
        "results_report.json",
    ]
    print(f"Artefatos        : {len(artefatos)} arquivos")

    if args.dry_run:
        print("\n[dry-run] Nenhum arquivo gravado.")
        for a in artefatos:
            print(f"  gravaria: {output / a}")
        return

    output.mkdir(parents=True, exist_ok=True)
    print()

    for lang in langs_a_gerar:
        lang_suf = f"_{lang}"
        if len(langs_a_gerar) > 1:
            print(f"  [{lang.upper()}]")
        grafico_funnel(stats, output, lang, lang_suf)
        grafico_trend(stats, output, lang, lang_suf)
        grafico_heatmap(stats, output, lang, lang_suf)
        grafico_journals(stats, output, args.top_journals, lang, lang_suf)
        grafico_coverage(stats, output, lang, lang_suf)
        gerar_texto(stats, output, lang, lang_suf)

    salvar_table_summary(stats, output)
    salvar_table_terms(stats, output)
    salvar_table_journals(stats, output)
    salvar_json(stats, output)

    print(f"\nPronto. Artefatos em: {output.resolve()}")


if __name__ == "__main__":
    main()
