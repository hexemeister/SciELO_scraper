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
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Verificação de dependências (antes de qualquer import externo)
# ---------------------------------------------------------------------------

_DEPS_REQUERIDAS = {
    "matplotlib": "matplotlib",
    "numpy":      "numpy",
}
_DEPS_OPCIONAIS = {
    "matplotlib_venn": "matplotlib-venn",
    "upsetplot":       "upsetplot",
}

def _verificar_deps():
    ausentes = [pkg for mod, pkg in _DEPS_REQUERIDAS.items()
                if importlib.util.find_spec(mod) is None]
    if ausentes:
        print("❌  Dependências ausentes. Execute:")
        print(f"    uv pip install {' '.join(ausentes)}")
        sys.exit(1)

_verificar_deps()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

__version__ = "1.8"

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
    # Venn
    "titulo_venn": {
        "pt": "Sobreposição de termos por campo — corpus completo",
        "en": "Term overlap by field — full corpus",
    },
    "titulo_upset": {
        "pt": "Sobreposição de termos por campo (UpSet) — corpus completo",
        "en": "Term overlap by field (UpSet) — full corpus",
    },
    "nota_venn": {
        "pt": (
            "Base: todos os artigos extraídos (n={n_total}). "
            "Cada painel mostra a sobreposição dos termos de busca no campo indicado. "
            "Nota: o resumo é coletado mas não é usado no critério de matching padrão."
        ),
        "en": (
            "Base: all extracted articles (n={n_total}). "
            "Each panel shows the overlap of search terms in the indicated field. "
            "Note: abstract is collected but not used in the default matching criterion."
        ),
    },
    "nota_upset": {
        "pt": (
            "Base: todos os artigos extraídos (n={n_total}). UpSet plot usado porque há {n_termos} termos "
            "(Venn legível apenas para ≤3 termos). Cada coluna representa uma intersecção de conjuntos."
        ),
        "en": (
            "Base: all extracted articles (n={n_total}). UpSet plot used because there are {n_termos} terms "
            "(Venn readable only for ≤3 terms). Each column represents a set intersection."
        ),
    },
    "venn_apenas_a": {
        "pt": "só {t}",
        "en": "only {t}",
    },
    "venn_nenhum": {
        "pt": "sem nenhum dos termos: n={n}",
        "en": "with none of the terms: n={n}",
    },
    "venn_legenda_titulo": {
        "pt": "Termos",
        "en": "Terms",
    },
    "arquivo_venn":     {"pt": "results_venn",           "en": "results_venn"},
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
        "nome":     "results_venn",
        "tipo":     "gráfico PNG",
        "arquivo":  "results_venn_<lang>.png",
        "descricao_pt": (
            "Diagrama de Venn (≤3 termos) ou UpSet plot (≥4 termos) mostrando a sobreposição "
            "dos termos de busca por campo (título, resumo, palavras-chave). "
            "Base: corpus completo (todos os artigos extraídos, não apenas criterio_ok). "
            "Com 2 termos: um painel por campo disponível. "
            "Com ≥4 termos: substituído por UpSet plot com aviso ao usuário."
        ),
        "descricao_en": (
            "Venn diagram (≤3 terms) or UpSet plot (≥4 terms) showing the overlap "
            "of search terms by field (title, abstract, keywords). "
            "Base: full corpus (all extracted articles, not only criterio_ok). "
            "With 2 terms: one panel per available field. "
            "With ≥4 terms: replaced by UpSet plot with user notice."
        ),
        "termos_usados_pt": "Todos os termos de busca detectados no CSV.",
        "termos_usados_en": "All search terms detected in the CSV.",
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


# Aliases curtos para --artifacts / --skip-artifacts
ARTEFATO_ALIASES = {
    "funnel":         "results_funnel",
    "trend":          "results_trend",
    "heatmap":        "results_terms_heatmap",
    "journals":       "results_journals",
    "coverage":       "results_coverage",
    "venn":           "results_venn",
    "text":           "results_text",
    "table_summary":  "results_table_summary",
    "table_terms":    "results_table_terms",
    "table_journals": "results_table_journals",
    "report":         "results_report",
}
# Inclui também o nome completo como alias de si mesmo
for _a in ARTEFATOS_CATALOGO:
    ARTEFATO_ALIASES[_a["nome"]] = _a["nome"]

_TODOS_NOMES = {a["nome"] for a in ARTEFATOS_CATALOGO}


def _resolver_artefatos(nomes: list[str]) -> set[str]:
    """Converte lista de aliases/nomes para o conjunto de nomes canônicos."""
    resolvidos = set()
    invalidos  = []
    for n in nomes:
        if n in ARTEFATO_ALIASES:
            resolvidos.add(ARTEFATO_ALIASES[n])
        else:
            invalidos.append(n)
    if invalidos:
        validos_str = ", ".join(sorted(ARTEFATO_ALIASES.keys()))
        print(f"❌  Artefato(s) desconhecido(s): {', '.join(invalidos)}")
        print(f"    Disponíveis: {validos_str}")
        sys.exit(1)
    return resolvidos


def _mostrar_help_artifacts():
    """--help-artifacts: lista resumida de todos os artefatos."""
    print("\nArtefatos gerados por results_report.py\n")
    print(f"  {'Alias curto':<22} {'Nome completo':<30} {'Tipo':<18} {'Arquivo'}")
    print("  " + "-" * 95)
    alias_inv = {v: k for k, v in ARTEFATO_ALIASES.items() if k != v}
    for a in ARTEFATOS_CATALOGO:
        alias = alias_inv.get(a["nome"], "—")
        print(f"  {alias:<22} {a['nome']:<30} {a['tipo']:<18} {a['arquivo']}")
    print()
    print("  Use --artifacts <alias> [alias ...] para gerar apenas esses artefatos.")
    print("  Use --skip-artifacts <alias> [alias ...] para pular artefatos específicos.")
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
    origem    = data.get("origem", {})

    print(f"\n{'═' * 64}")
    print(f"  results_report.json  —  v{versao}  —  {gerado_em[:16].replace('T', ' ')}")
    print(f"{'═' * 64}")
    print(f"  Anos    : {', '.join(str(a) for a in anos)}")
    print(f"  Termos  : {', '.join(termos)}")
    print(f"  Campos  : {', '.join(campos)}")
    if origem:
        print(f"  Comando : {origem.get('comando', '?')}")
        if origem.get("cwd"):
            print(f"  Dir     : {origem['cwd']}")

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
        versao_searcher  = params.get("versao_searcher", "")   # gravado a partir de v1.3
        query_url        = params.get("query_url", "")
        versao_scraper   = stats_j.get("versao_script", "")    # campo real em stats.json
        tempo_scraping   = stats_j.get("elapsed_seconds", None)  # campo real em stats.json
        tempo_humanizado = stats_j.get("elapsed_humanizado", "")
        avg_por_artigo   = stats_j.get("avg_per_article_s", None)
        erros_extracao   = {
            k: v["n"] if isinstance(v, dict) else v
            for k, v in stats_j.get("por_status", {}).items()
            if k not in ("ok_completo", "ok_parcial")
        } if stats_j.get("por_status") else {}
        taxa_sucesso     = stats_j.get("sucesso_total_pct", None)  # campo real em stats.json
        fontes_extracao  = stats_j.get("por_fonte_extracao", {})

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
            "query_url":        query_url,
            "versao_searcher":  versao_searcher,
            "versao_scraper":   versao_scraper,
            "tempo_scraping":   tempo_scraping,
            "tempo_humanizado": tempo_humanizado,
            "avg_por_artigo":   avg_por_artigo,
            "erros_extracao":   erros_extracao,
            "taxa_sucesso":     taxa_sucesso,
            "fontes_extracao":  fontes_extracao,
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

# Paleta default (usada apenas quando o estilo ativo não define prop_cycle)
_CORES_DEFAULT = ["#2980b9", "#27ae60", "#e67e22", "#8e44ad", "#c0392b",
                  "#16a085", "#d35400", "#2c3e50"]

# Colormaps sequenciais disponíveis para o heatmap (--colormap)
COLORMAPS_DISPONIVEIS = ["viridis", "plasma", "inferno", "magma", "cividis", "YlOrRd"]
_COLORMAP_DEFAULT     = "viridis"

# Colormap global ativo (alterado por --colormap em main())
_colormap_ativo: str = _COLORMAP_DEFAULT


def _cycle_colors(n: int) -> list[str]:
    """Retorna n cores do prop_cycle do estilo matplotlib atualmente ativo."""
    cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", _CORES_DEFAULT)
    # Repete o ciclo se n > len(cycle)
    return [cycle[i % len(cycle)] for i in range(n)]


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

        cores = _cycle_colors(len(vals))
        bars = ax.bar(x, vals, color=cores, edgecolor="white", linewidth=0.8, zorder=2)
        ax.yaxis.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, zorder=0)
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

    cores = _cycle_colors(3)
    c_total, c_ok, c_pct = cores[0], cores[1], cores[2]

    ax1.bar(x - w/2, vals_total, w, label=s("legenda_total_scrapeado", lang),
            color=c_total, alpha=0.6, zorder=2)
    ax1.bar(x + w/2, vals_ok,    w, label=s("legenda_criterio_ok", lang),
            color=c_ok, zorder=2)
    ax1.yaxis.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, zorder=0)
    ax1.set_axisbelow(True)
    ax1.set_ylabel(s("eixo_n_artigos", lang), fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(a) for a in anos], fontsize=11)
    ax1.set_xlabel(s("eixo_ano", lang), fontsize=11)

    ax2 = ax1.twinx()
    ax2.plot(x, pcts, "o--", color=c_pct, linewidth=2, markersize=7,
             label=s("legenda_pct_criterio", lang))
    ax2.set_ylabel(s("legenda_pct_criterio", lang), fontsize=11, color=c_pct)
    ax2.tick_params(axis="y", labelcolor=c_pct)
    ax2.set_ylim(0, 110)

    for xi, pct in zip(x, pcts):
        ax2.text(xi, pct + 3, f"{pct:.1f}%", ha="center", fontsize=9,
                 color=c_pct, fontweight="bold")

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

    im = ax.imshow(matriz, aspect="auto", cmap=_colormap_ativo, vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label="%", shrink=0.8)

    ax.set_xticks(range(len(campos)))
    ax.set_xticklabels([campo_labels.get(c, c) for c in campos], fontsize=11)
    ax.set_yticks(range(len(termos)))
    ax.set_yticklabels(termos, fontsize=11)
    ax.set_xlabel(s("eixo_campo", lang), fontsize=11)
    ax.set_ylabel(s("eixo_termo", lang), fontsize=11)

    # Cor do texto adaptada à luminância do colormap no ponto dado
    cmap_obj = plt.get_cmap(_colormap_ativo)
    for i in range(len(termos)):
        for j in range(len(campos)):
            val = matriz[i, j]
            rgba = cmap_obj(val / 100)
            # Luminância perceptual (ITU-R BT.709)
            lum = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            cor = "white" if lum < 0.45 else "#1a1a1a"
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
    bars = ax.barh(y, vals, color=_cycle_colors(1)[0], edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, vals):
        pct = val / total_ok * 100 if total_ok else 0
        ax.text(bar.get_width() + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val} ({pct:.1f}%)", va="center", fontsize=9)

    ax.set_yticks(y)
    ax.set_yticklabels(nomes_curtos, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel(s("eixo_n_artigos", lang), fontsize=11)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, zorder=0)
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

    cores_campos = _cycle_colors(len(campos_disponiveis))
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
                      color=cores_campos[i],
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
    ax.yaxis.grid(True, linestyle="--", linewidth=0.5, alpha=0.5, zorder=0)
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
# Venn / UpSet — sobreposição de termos por campo
# ---------------------------------------------------------------------------

_CAMPO_COL_BOOL = {
    "titulo":   "titulo",
    "resumo":   "resumo",
    "keywords": "keywords",
}

_CAMPO_LABEL = {
    "titulo":   {"pt": "Título",        "en": "Title"},
    "resumo":   {"pt": "Resumo",        "en": "Abstract"},
    "keywords": {"pt": "Palavras-chave","en": "Keywords"},
}

_UPSET_THRESHOLD = 4   # ≥ N termos → UpSet em vez de Venn


def _venn_sets_por_campo(
    todas_rows: list[dict],
    termos: list[str],
    campos: list[str],
) -> dict[str, list[set]]:
    """
    Para cada campo, retorna uma lista de sets (um por termo) com os índices
    dos artigos em que o termo aparece naquele campo.
    """
    resultado: dict[str, list[set]] = {}
    for campo in campos:
        sets_campo = []
        for termo in termos:
            col = f"{termo}_{campo}"
            s_idx = {
                i for i, r in enumerate(todas_rows)
                if _bool(r.get(col, "False"))
            }
            sets_campo.append(s_idx)
        resultado[campo] = sets_campo
    return resultado


def _venn_legenda(ax, termos: list[str], cores: list, lang: str):
    """Adiciona legenda de cores (termo → cor) ao eixo do Venn."""
    import matplotlib.patches as mpatches
    patches = [mpatches.Patch(color=c, alpha=0.6, label=t)
               for t, c in zip(termos, cores)]
    ax.legend(
        handles=patches,
        title=s("venn_legenda_titulo", lang),
        fontsize=8,
        title_fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=len(termos),
        frameon=True,
        framealpha=0.8,
    )


def _grafico_venn2(ax, sets: list[set], termos: list[str], n_total: int, lang: str):
    """Renderiza Venn de 2 conjuntos em `ax`."""
    from matplotlib_venn import venn2  # importação local

    A, B = sets[0], sets[1]
    cores = _cycle_colors(2)
    v = venn2(subsets=(len(A - B), len(B - A), len(A & B)),
              set_labels=("", ""),   # ocultamos labels do venn (usamos legenda)
              ax=ax,
              set_colors=(cores[0], cores[1]),
              alpha=0.55)

    # n absoluto em cada região
    for label_id, label_txt in [("10", f"n={len(A-B)}"),
                                 ("01", f"n={len(B-A)}"),
                                 ("11", f"n={len(A&B)}")]:
        lbl = v.get_label_by_id(label_id)
        if lbl:
            lbl.set_text(label_txt)
            lbl.set_fontsize(9)

    # Artigos sem nenhum dos termos — texto acima da legenda
    nenhum = n_total - len(A | B)
    txt = s("venn_nenhum", lang).format(n=nenhum)
    ax.text(0.5, -0.06, txt, transform=ax.transAxes,
            ha="center", va="top", fontsize=8, color="#555555")

    # Legenda de cores por termo
    _venn_legenda(ax, termos, cores, lang)


def _grafico_venn3(ax, sets: list[set], termos: list[str], n_total: int, lang: str):
    """Renderiza Venn de 3 conjuntos em `ax`."""
    from matplotlib_venn import venn3  # importação local

    A, B, C = sets[0], sets[1], sets[2]
    cores = _cycle_colors(3)
    v = venn3(subsets=(
                len(A - B - C),
                len(B - A - C),
                len(A & B - C),
                len(C - A - B),
                len(A & C - B),
                len(B & C - A),
                len(A & B & C),
              ),
              set_labels=("", "", ""),   # ocultamos labels do venn (usamos legenda)
              ax=ax,
              set_colors=tuple(cores[:3]),
              alpha=0.55)

    # n absoluto em cada região
    regions = {
        "100": len(A - B - C), "010": len(B - A - C),
        "110": len(A & B - C), "001": len(C - A - B),
        "101": len(A & C - B), "011": len(B & C - A),
        "111": len(A & B & C),
    }
    for region_id, n_val in regions.items():
        lbl = v.get_label_by_id(region_id)
        if lbl:
            lbl.set_text(f"n={n_val}")
            lbl.set_fontsize(8.5)

    nenhum = n_total - len(A | B | C)
    txt = s("venn_nenhum", lang).format(n=nenhum)
    ax.text(0.5, -0.06, txt, transform=ax.transAxes,
            ha="center", va="top", fontsize=8, color="#555555")

    # Legenda de cores por termo
    _venn_legenda(ax, termos, cores, lang)


def grafico_venn(
    todas_rows: list[dict],
    termos: list[str],
    campos: list[str],
    stats: dict,
    output: Path,
    lang: str = "pt",
    lang_suf: str = "",
):
    """
    Gera results_venn_<lang>.png.

    • ≤3 termos → Venn (matplotlib-venn), um painel por campo
    • ≥4 termos → UpSet plot (upsetplot), único painel
    Base: corpus completo (todas_rows), não só criterio_ok.
    """
    n_total = len(todas_rows)
    n_termos = len(termos)
    dest = output / f"{s('arquivo_venn', lang)}{lang_suf}.png"

    # ---- UpSet (≥ _UPSET_THRESHOLD termos) -----------------------------------
    if n_termos >= _UPSET_THRESHOLD:
        try:
            from upsetplot import UpSet, from_memberships  # importação local
        except ImportError:
            print(f"  ⚠  upsetplot não instalado — pulando {dest.name}. "
                  "Execute: uv pip install upsetplot")
            return

        print(f"  ⚠  {n_termos} termos detectados: usando UpSet plot em vez de Venn.")

        # Para UpSet: memberships por artigo (quais termos × campos estão True)
        # Agrupa: artigo pertence a conjunto "termo_campo" se booleana for True
        # Usamos a union sobre campos (any campo) para não explodir dimensões
        memberships = []
        for r in todas_rows:
            grupos = []
            for termo in termos:
                em_algum_campo = any(
                    _bool(r.get(f"{termo}_{campo}", "False"))
                    for campo in campos
                )
                if em_algum_campo:
                    grupos.append(termo)
            memberships.append(grupos)

        data = from_memberships(memberships, data=[1] * n_total)
        upset = UpSet(data, subset_size="count", show_counts=True,
                      sort_by="cardinality", totals_plot_elements=3)

        fig = upset.plot()
        nota = s("nota_upset", lang).format(n_total=n_total, n_termos=n_termos)
        fig["matrix"].set_title(s("titulo_upset", lang), fontsize=11, fontweight="bold")
        fig["matrix"].annotate(nota, xy=(0.5, -0.25), xycoords="axes fraction",
                               ha="center", fontsize=7.5, color="gray",
                               wrap=True)
        plt.savefig(dest, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  ✓ {dest}")
        return

    # ---- Venn (2 ou 3 termos) ------------------------------------------------
    try:
        import matplotlib_venn  # noqa: F401 — só testa disponibilidade
    except ImportError:
        print(f"  ⚠  matplotlib-venn não instalado — pulando {dest.name}. "
              "Execute: uv pip install matplotlib-venn")
        return

    sets_por_campo = _venn_sets_por_campo(todas_rows, termos, campos)

    # Filtra campos sem dados (nenhum artigo com qualquer termo)
    campos_com_dados = [
        c for c in campos
        if any(len(s_) > 0 for s_ in sets_por_campo[c])
    ]
    if not campos_com_dados:
        print(f"  ⚠  Nenhum dado para Venn — pulando {dest.name}.")
        return

    n_paineis = len(campos_com_dados)
    fig_w = max(4.5, 4.5 * n_paineis)
    fig, axes = plt.subplots(1, n_paineis, figsize=(fig_w, 5.4))
    if n_paineis == 1:
        axes = [axes]

    fig.suptitle(s("titulo_venn", lang), fontsize=12, fontweight="bold", y=1.01)

    for ax, campo in zip(axes, campos_com_dados):
        campo_label = _CAMPO_LABEL.get(campo, {}).get(lang, campo)
        ax.set_title(campo_label, fontsize=11, pad=10)

        sets = sets_por_campo[campo]
        if n_termos == 2:
            _grafico_venn2(ax, sets, termos, n_total, lang)
        else:  # 3
            _grafico_venn3(ax, sets, termos, n_total, lang)

    nota = s("nota_venn", lang).format(n_total=n_total)
    # Nota de rodapé: só mostra aviso sobre resumo se "resumo" está nos campos
    if "resumo" not in campos_com_dados:
        nota = nota.split("Nota:")[0].split("Note:")[0].strip()

    plt.tight_layout()
    fig.subplots_adjust(bottom=0.22)   # espaço para legenda de cores + nota
    fig.text(0.5, 0.01, nota, ha="center", fontsize=7.5, color="gray",
             wrap=True, transform=fig.transFigure)

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


def gerar_texto(stats: dict, output: Path, lang: str = "pt", lang_suf: str = ""):  # noqa: C901
    anos    = stats["anos"]
    por_ano = stats["por_ano"]
    totais  = stats["totais"]
    termos  = stats["termos"]
    campos  = stats["campos"]  # campos detectados no CSV (podem incluir resumo)

    # Campos do critério automático (usados em criterio_ok)
    # Derivamos dos dados: campos onde há co-ocorrência reportada
    campos_criterio = [c for c in campos if c != "resumo"] or campos

    primeiro_ano_v  = por_ano[anos[0]]
    termos_busca    = primeiro_ano_v.get("termos_busca", termos)
    colecao         = primeiro_ano_v.get("colecao", "scl")
    truncamento     = primeiro_ano_v.get("truncamento", True)
    campos_busca    = primeiro_ano_v.get("campos_busca", "ti+ab")
    data_busca_ts   = primeiro_ano_v.get("data_busca", "")
    query_url       = primeiro_ano_v.get("query_url", "")
    versao_searcher = primeiro_ano_v.get("versao_searcher", "")
    versao_scraper  = primeiro_ano_v.get("versao_scraper", "")

    total_b  = totais["total_buscado"]
    total_s  = totais["total_scrapeado"]
    total_ok = totais["criterio_ok"]
    pct_ok   = totais["criterio_ok_pct"]

    ok_compl_total = sum(v["ok_completo"] for v in por_ano.values())
    ok_parc_total  = sum(v["ok_parcial"]  for v in por_ano.values())

    # Tempo total de scraping (soma dos anos com dados disponíveis)
    tempos_disponiveis = [v["tempo_scraping"] for v in por_ano.values()
                          if v.get("tempo_scraping") is not None]
    tempo_total_s  = sum(tempos_disponiveis) if tempos_disponiveis else None
    tempo_hum_list = [v["tempo_humanizado"] for v in por_ano.values()
                      if v.get("tempo_humanizado")]

    # Taxa de sucesso (string já formatada como "99.8%" ou None)
    taxas_str = [v["taxa_sucesso"] for v in por_ano.values()
                 if v.get("taxa_sucesso") is not None]

    # Erros globais
    erros_global: dict[str, int] = defaultdict(int)
    for v in por_ano.values():
        for k, n in v.get("erros_extracao", {}).items():
            erros_global[k] += n

    top3 = sorted(totais["jornais"].items(), key=lambda x: x[1], reverse=True)[:3]
    tc_global   = totais["termos_campos"]
    cooc_global = totais.get("coocorrencia", {})

    # ---- helpers de formatação ----
    def _fmt_termos(sep: str) -> str:
        return sep.join(f'"{t}"' for t in termos_busca)

    def _fmt_campos_busca_legivel(cb: str, l: str) -> str:
        if l == "pt":
            return {"ti+ab": "título e resumo", "ti": "título", "ab": "resumo"}.get(cb, cb)
        return {"ti+ab": "title and abstract", "ti": "title", "ab": "abstract"}.get(cb, cb)

    def _fmt_colecao(col: str, l: str) -> str:
        if l == "pt":
            return {"scl": "SciELO Brasil", "arg": "SciELO Argentina"}.get(col, col)
        return {"scl": "SciELO Brazil", "arg": "SciELO Argentina"}.get(col, col)

    def _fmt_campos_criterio(clist: list[str], l: str) -> str:
        labels_pt = {"titulo": "título", "resumo": "resumo", "keywords": "palavras-chave"}
        labels_en = {"titulo": "title",  "resumo": "abstract", "keywords": "keywords"}
        labels = labels_pt if l == "pt" else labels_en
        partes = [labels.get(c, c) for c in clist]
        if len(partes) == 1:
            return partes[0]
        conj = " e " if l == "pt" else " and "
        return ", ".join(partes[:-1]) + conj + partes[-1]

    def _fmt_ver(vs: str, vc: str, l: str) -> str:
        """Monta string de versões; avisa se ausentes."""
        parts = []
        if vs:
            parts.append(f"SciELO Search v{vs}" if l == "pt" else f"SciELO Search v{vs}")
        else:
            parts.append("SciELO Search [versão não disponível — execute com scielo_search.py v1.3+]"
                         if l == "pt" else
                         "SciELO Search [version unavailable — run with scielo_search.py v1.3+]")
        if vc:
            parts.append(f"SciELO Scraper v{vc}")
        else:
            parts.append("SciELO Scraper [versão não disponível]"
                         if l == "pt" else
                         "SciELO Scraper [version unavailable]")
        return "; ".join(parts)

    data_fmt = _formato_data_busca(data_busca_ts, lang)
    cob_anos_str = _anos_cobertura_str(anos, lang)

    # ── Helpers para seções de figuras ───────────────────────────────────────
    def _nome_arquivo_figura(chave_arquivo: str) -> str:
        """Retorna o nome de arquivo do gráfico incluindo o lang_suf atual."""
        return f"{s(chave_arquivo, lang)}{lang_suf}.png"

    def _link_figura(chave_arquivo: str, titulo_fig: str) -> str:
        nome = _nome_arquivo_figura(chave_arquivo)
        return f"[{titulo_fig}]({nome})"

    # nomes de arquivo para os links
    arq_funnel   = _nome_arquivo_figura("arquivo_funnel")
    arq_trend    = _nome_arquivo_figura("arquivo_trend")
    arq_heatmap  = _nome_arquivo_figura("arquivo_heatmap")
    arq_journals = _nome_arquivo_figura("arquivo_journals")
    arq_coverage = _nome_arquivo_figura("arquivo_coverage")

    # ── Seção de artefatos ────────────────────────────────────────────────────
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

    # =========================================================================
    # PT-BR
    # =========================================================================
    if lang == "pt":
        trunc_str   = " com truncamento automático (operador $)" if truncamento else ""
        cbf         = _fmt_campos_busca_legivel(campos_busca, "pt")
        colf        = _fmt_colecao(colecao, "pt")
        termos_fmt  = _fmt_termos(" e ")
        data_str    = f", conduzida em {data_fmt}," if data_fmt else ""
        ver_str     = _fmt_ver(versao_searcher, versao_scraper, "pt")
        ccrit_str   = _fmt_campos_criterio(campos_criterio, "pt")

        # Cobertura de extração
        cob_str = f"{ok_compl_total} artigos com extração completa (título + resumo + palavras-chave)"
        if ok_parc_total:
            cob_str += f" e {ok_parc_total} com extração parcial"

        # Cobertura por ano (detalhado)
        cob_ano_parts = []
        for a in anos:
            v = por_ano[a]
            cob_ano_parts.append(
                f"{a}: {v['ok_completo']} completos"
                + (f", {v['ok_parcial']} parcial" if v["ok_parcial"] else "")
            )
        cob_por_ano_str = "; ".join(cob_ano_parts) if len(anos) > 1 else ""

        # Tempo de extração
        if tempo_total_s is not None:
            t_fmt = _formato_tempo(tempo_total_s)
            if len(anos) > 1 and tempo_hum_list:
                tempo_part = (
                    f" O tempo total de extração foi de {t_fmt}"
                    f" ({'; '.join(f'{a}: {h}' for a, h in zip(anos, tempo_hum_list))})."
                )
            else:
                tempo_part = f" O tempo total de extração foi de {t_fmt}."
        else:
            tempo_part = ""

        # Taxa de sucesso
        taxa_part = f" Taxa de sucesso da extração: {taxas_str[0]}." if taxas_str else ""

        # Erros
        if erros_global:
            erros_items = []
            erros_label = {
                "nada_encontrado": "sem dados encontrados",
                "erro_extracao":   "erro de acesso (ex: 404)",
                "erro_pid_invalido": "PID inválido",
            }
            for k, n in erros_global.items():
                erros_items.append(f"{n} {erros_label.get(k, k)}")
            erros_part = f" Foram identificadas as seguintes ocorrências na extração: {'; '.join(erros_items)}."
        else:
            erros_part = " Não foram identificadas falhas de acesso durante a extração."

        # Distribuição por ano dos registros buscados
        if len(anos) > 1:
            dist_busca_parts = [f"{a}: {por_ano[a]['total_buscado']} registros" for a in anos]
            dist_busca_str = (
                f"distribuídos por ano da seguinte forma: {'; '.join(dist_busca_parts)}"
            )
        else:
            dist_busca_str = ""

        # Metodologia — parágrafo 1: busca
        p_busca = (
            f"A busca bibliográfica{data_str} foi realizada na plataforma SciELO ({colf}) "
            f"por meio do SciELO Search ({ver_str.split(';')[0].strip()}), "
            f"utilizando os termos {termos_fmt}{trunc_str}, "
            f"nos campos de {cbf}, "
            f"abrangendo {cob_anos_str}. "
            f"Foram recuperados {total_b} registros"
            + (f", {dist_busca_str}" if dist_busca_str else "")
            + "."
        )

        # Metodologia — parágrafo 2: estratégia de extração
        p_estrategia = (
            "A extração dos metadados em português (título, resumo e palavras-chave) foi "
            "realizada por meio do SciELO Scraper, utilizando a estratégia denominada "
            "**api+html**. Nessa abordagem, o sistema consulta primeiramente a "
            "ArticleMeta API — uma interface de programação mantida pela SciELO que "
            "fornece metadados estruturados dos artigos indexados. Quando a API retorna "
            "dados incompletos ou não retorna dados para um determinado artigo (o que "
            "ocorre com frequência em artigos no estágio Ahead of Print, ou seja, "
            "publicados online antes de receberem numeração definitiva de fascículo), "
            "o sistema recorre automaticamente à raspagem direta do HTML da página do "
            "artigo no portal SciELO — técnica conhecida como *fallback* (alternativa "
            "de contingência). Essa estratégia combinada maximiza a taxa de extração "
            "bem-sucedida em comparação com o uso exclusivo da API ou do HTML."
        )

        # Metodologia — parágrafo 3: extração + filtragem
        p_extracao = (
            f"A extração resultou em {cob_str}"
            + (f" ({cob_por_ano_str})" if cob_por_ano_str else "")
            + f".{tempo_part}{taxa_part}{erros_part} "
            f"A etapa de filtragem automática verificou a presença simultânea de todos "
            f"os termos em pelo menos um dos campos requeridos ({ccrit_str}), "
            f"identificando {total_ok} artigos ({pct_ok:.1f}%) como potencialmente "
            f"relevantes para curadoria humana"
            + (
                f" (distribuição por ano: "
                + "; ".join(
                    f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                    for a in anos
                ) + ")"
                if len(anos) > 1 else ""
            )
            + "."
        )

        metodologia = p_busca + "\n\n" + p_estrategia + "\n\n" + p_extracao

        # Nota técnica: URL da query
        if query_url:
            nota_tecnica = (
                "### Nota técnica — URL da busca\n\n"
                "A consulta foi executada na seguinte URL (pode ser utilizada como "
                "nota de rodapé ou referência metodológica):\n\n"
                f"```\n{query_url}\n```"
            )
        else:
            nota_tecnica = ""

        # ── Resultados ────────────────────────────────────────────────────────
        # Apenas os campos do critério entram na análise de termos dos resultados
        termos_analise_parts = []
        for t in termos:
            partes_t = []
            for c in campos_criterio:
                n   = tc_global.get(t, {}).get(c, 0)
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

        # Co-ocorrência — apenas campos do critério
        cooc_parts = []
        for c in campos_criterio:
            n_c = cooc_global.get(c, 0)
            if n_c > 0:
                pct_c = n_c / total_ok * 100
                label_c, prep_c = {
                    "titulo":   ("título", "no"),
                    "resumo":   ("resumo", "no"),
                    "keywords": ("palavras-chave", "nas"),
                }.get(c, (c, "no"))
                cooc_parts.append(f"{n_c} ({pct_c:.1f}%) {prep_c} {label_c}")
        cooc_str = (
            "A co-ocorrência simultânea de todos os termos foi verificada em: "
            + "; ".join(cooc_parts) + ". "
        ) if cooc_parts else ""

        top3_str = "; ".join(f"{j} (n={n})" for j, n in top3)
        n_journals_total = len(totais["jornais"])

        resultados = (
            f"{total_ok} ({pct_ok:.1f}%) dos {total_s} artigos extraídos "
            f"atenderam ao critério de filtragem automática e foram encaminhados "
            f"para verificação humana pelo grupo de pesquisa."
        )
        if len(anos) > 1:
            dist_ok_parts = [
                f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            ]
            resultados += f" Distribuição por ano: {'; '.join(dist_ok_parts)}."

        resultados += "\n\n" + termos_analise
        if cooc_str:
            resultados += " " + cooc_str.strip()

        if top3:
            resultados += (
                f"\n\nOs artigos critério foram identificados em {n_journals_total} "
                f"periódicos distintos. Os periódicos com maior representação foram: "
                f"{top3_str}."
            )

        # ── Limitações ────────────────────────────────────────────────────────
        limitacoes = (
            "A busca automatizada com truncamento pode recuperar artigos que contêm os "
            "radicais dos termos em contextos não relacionados ao tema principal desta "
            "revisão, exigindo curadoria humana para validação da pertinência. "
            "A filtragem automática baseia-se exclusivamente na presença simultânea dos "
            f"termos nos campos selecionados ({ccrit_str}), sem análise semântica ou de "
            "contexto. "
            "A cobertura da plataforma SciELO está limitada a periódicos indexados nessa "
            "base, não contemplando publicações em outros repositórios (ex: LILACS, "
            "PubMed, Scopus). "
            "Artigos no estágio Ahead of Print (AoP) podem não estar indexados via API e "
            "dependem de extração por HTML, podendo apresentar menor estabilidade nos "
            "metadados. "
            "A análise de co-ocorrência indica presença dos termos nos mesmos campos, "
            "mas não garante relação semântica direta entre eles."
        )

        # ── Figuras ───────────────────────────────────────────────────────────
        n_anos = len(anos)

        def _fig_funil_pt() -> str:
            short = (
                "O funil de seleção apresenta três etapas sequenciais de redução do "
                "corpus: recuperação via busca na plataforma, extração de metadados por "
                "raspagem e aplicação do critério de filtragem automática."
            )
            linhas_longa = []
            for a in anos:
                v = por_ano[a]
                tb = v["total_buscado"]
                ts = v["total_scrapeado"]
                tok = v["criterio_ok"]
                pok = v["criterio_ok_pct"]
                pras = ts / tb * 100 if tb else 0
                linhas_longa.append(
                    f"Em {a}, foram recuperados {tb} registros na busca. "
                    f"Todos os {ts} registros tiveram metadados extraídos ({pras:.1f}%), "
                    f"dos quais {tok} ({pok:.1f}%) atenderam ao critério de filtragem."
                )
            if n_anos > 1:
                pok_total = total_ok / total_b * 100 if total_b else 0
                linhas_longa.append(
                    f"Considerando o período completo ({cob_anos_str}), a taxa de "
                    f"retenção da busca ao corpus criterio_ok foi de "
                    f"{pok_total:.1f}% ({total_ok}/{total_b})."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Versão curta (legenda expandida)\n\n{short}\n\n"
                f"#### Versão longa (substituto textual)\n\n{long}"
            )

        def _fig_trend_pt() -> str:
            if n_anos == 1:
                return (
                    "#### Nota\n\n"
                    "Análise temporal não aplicável — apenas 1 ano disponível no corpus."
                )
            short = (
                "O gráfico apresenta a evolução anual do número de artigos criterio_ok "
                "e sua proporção em relação ao total extraído."
            )
            pcts = [por_ano[a]["criterio_ok_pct"] for a in anos]
            tendencia = "estável" if max(pcts) - min(pcts) < 3 else (
                "crescente" if pcts[-1] > pcts[0] else "decrescente"
            )
            series = "; ".join(
                f"{a}: {por_ano[a]['criterio_ok']}/{por_ano[a]['total_scrapeado']} "
                f"({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            )
            long = (
                f"A proporção de artigos criterio_ok manteve-se {tendencia} ao longo "
                f"do período analisado ({series}), "
                f"com variação de {min(pcts):.1f}% a {max(pcts):.1f}%."
            )
            return (
                f"#### Versão curta (legenda expandida)\n\n{short}\n\n"
                f"#### Versão longa (substituto textual)\n\n{long}"
            )

        def _fig_heatmap_pt() -> str:
            short = (
                f"O mapa de calor exibe a frequência relativa de cada termo nos campos "
                f"detectados, calculada sobre os {total_ok} artigos criterio_ok."
            )
            linhas_longa = []
            for t in termos:
                campo_max = max(campos, key=lambda c: tc_global.get(t, {}).get(c, 0))
                n_max = tc_global.get(t, {}).get(campo_max, 0)
                pct_max = n_max / total_ok * 100 if total_ok else 0
                label_max, prep_max = {
                    "titulo":   ("título", "no"), "resumo": ("resumo", "no"),
                    "keywords": ("palavras-chave", "nas"),
                }.get(campo_max, (campo_max, "no"))
                outros = [
                    f"{tc_global.get(t,{}).get(c,0)} ({tc_global.get(t,{}).get(c,0)/total_ok*100:.1f}%) "
                    + {"titulo": "no título", "resumo": "no resumo",
                       "keywords": "nas palavras-chave"}.get(c, c)
                    for c in campos if c != campo_max
                ]
                linhas_longa.append(
                    f'O termo "{t}" apresentou maior ocorrência '
                    f"{prep_max} {label_max} ({n_max}; {pct_max:.1f}%)"
                    + (f", seguido de {'; '.join(outros)}" if outros else "")
                    + "."
                )
            # campo com maior co-ocorrência
            if cooc_global:
                campo_cooc = max(cooc_global, key=lambda c: cooc_global.get(c, 0))
                n_cooc = cooc_global[campo_cooc]
                pct_cooc = n_cooc / total_ok * 100 if total_ok else 0
                prep_cooc = {"titulo": "no", "resumo": "no", "keywords": "nas"}.get(campo_cooc, "no")
                label_cooc = {"titulo": "título", "resumo": "resumo",
                               "keywords": "palavras-chave"}.get(campo_cooc, campo_cooc)
                linhas_longa.append(
                    f"O campo com maior co-ocorrência simultânea de todos os termos foi "
                    f"{prep_cooc} {label_cooc} ({n_cooc}; {pct_cooc:.1f}%)."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Versão curta (legenda expandida)\n\n{short}\n\n"
                f"#### Versão longa (substituto textual)\n\n{long}"
            )

        def _fig_journals_pt() -> str:
            n_journals = len(totais["jornais"])
            short = (
                "O gráfico apresenta os periódicos com maior número de artigos no "
                "corpus criterio_ok, ordenados de forma decrescente."
            )
            top3_detalhes = "; ".join(
                f"{j} (n={n}; {n/total_ok*100:.1f}%)" for j, n in top3
            )
            n_top3 = sum(n for _, n in top3)
            pct_top3 = n_top3 / total_ok * 100 if total_ok else 0
            long = (
                f"Os {total_ok} artigos criterio_ok distribuíram-se por "
                f"{n_journals} periódicos distintos. "
                f"Os três periódicos com maior representação foram: {top3_detalhes}. "
                f"Em conjunto, esses três periódicos concentraram {pct_top3:.1f}% "
                f"({n_top3}/{total_ok}) do corpus criterio_ok."
            )
            return (
                f"#### Versão curta (legenda expandida)\n\n{short}\n\n"
                f"#### Versão longa (substituto textual)\n\n{long}"
            )

        def _fig_coverage_pt() -> str:
            short = (
                "O gráfico exibe, por ano, a proporção de artigos com cada campo de "
                "metadados em português preenchido (título, resumo e palavras-chave)."
            )
            linhas_longa = []
            for a in anos:
                v    = por_ano[a]
                ts_a = v["total_scrapeado"]
                cob  = v["cobertura_campos"]
                partes = []
                for c in ["titulo", "resumo", "keywords"]:
                    n_c = cob.get(c, 0)
                    pct_c = n_c / ts_a * 100 if ts_a else 0
                    label = {"titulo": "título", "resumo": "resumo",
                             "keywords": "palavras-chave"}.get(c, c)
                    partes.append(f"{pct_c:.1f}% possuíam {label} em português (n={n_c})")
                linhas_longa.append(f"Em {a}: {'; '.join(partes)}.")
            if ok_parc_total:
                linhas_longa.append(
                    f"A extração parcial registrada ({ok_parc_total} artigo(s)) "
                    "não comprometeu de forma significativa a completude do corpus."
                )
            else:
                linhas_longa.append(
                    "Não foram registradas extrações parciais; todos os artigos "
                    "apresentaram cobertura completa de metadados."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Versão curta (legenda expandida)\n\n{short}\n\n"
                f"#### Versão longa (substituto textual)\n\n{long}"
            )

        # Monta seção de figuras
        figuras_section = (
            "As seções a seguir descrevem cada figura gerada em duas versões: "
            "uma **versão curta**, adequada para uso como legenda expandida em "
            "publicações científicas, e uma **versão longa**, que substitui "
            "integralmente o gráfico quando o formato do veículo não permite "
            "a inclusão de imagens.\n"
        )
        fig_num = 1
        figuras_section += (
            f"\n### Figura {fig_num} — Funil de seleção "
            f"([{arq_funnel}]({arq_funnel}))\n\n"
            + _fig_funil_pt()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figura {fig_num} — Evolução temporal "
            f"([{arq_trend}]({arq_trend}))\n\n"
            + _fig_trend_pt()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figura {fig_num} — Distribuição de termos por campo "
            f"([{arq_heatmap}]({arq_heatmap}))\n\n"
            + _fig_heatmap_pt()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figura {fig_num} — Periódicos com maior representação "
            f"([{arq_journals}]({arq_journals}))\n\n"
            + _fig_journals_pt()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figura {fig_num} — Cobertura de metadados em português "
            f"([{arq_coverage}]({arq_coverage}))\n\n"
            + _fig_coverage_pt()
        )

    # =========================================================================
    # EN
    # =========================================================================
    else:
        trunc_str  = " with automatic truncation ($ operator)" if truncamento else ""
        cbf        = _fmt_campos_busca_legivel(campos_busca, "en")
        colf       = _fmt_colecao(colecao, "en")
        termos_fmt = _fmt_termos(" and ")
        data_str   = f", conducted on {data_fmt}," if data_fmt else ""
        ver_str    = _fmt_ver(versao_searcher, versao_scraper, "en")
        ccrit_str  = _fmt_campos_criterio(campos_criterio, "en")

        cob_str = f"{ok_compl_total} articles with complete extraction (title + abstract + keywords)"
        if ok_parc_total:
            cob_str += f" and {ok_parc_total} with partial extraction"

        cob_ano_parts = []
        for a in anos:
            v = por_ano[a]
            cob_ano_parts.append(
                f"{a}: {v['ok_completo']} complete"
                + (f", {v['ok_parcial']} partial" if v["ok_parcial"] else "")
            )
        cob_por_ano_str = "; ".join(cob_ano_parts) if len(anos) > 1 else ""

        if tempo_total_s is not None:
            t_fmt = _formato_tempo(tempo_total_s)
            if len(anos) > 1 and tempo_hum_list:
                tempo_part = (
                    f" Total extraction time was {t_fmt}"
                    f" ({'; '.join(f'{a}: {h}' for a, h in zip(anos, tempo_hum_list))})."
                )
            else:
                tempo_part = f" Total extraction time was {t_fmt}."
        else:
            tempo_part = ""

        taxa_part = f" Extraction success rate: {taxas_str[0]}." if taxas_str else ""

        if erros_global:
            erros_items = []
            erros_label = {
                "nada_encontrado": "no data found",
                "erro_extracao":   "access error (e.g. 404)",
                "erro_pid_invalido": "invalid PID",
            }
            for k, n in erros_global.items():
                erros_items.append(f"{n} {erros_label.get(k, k)}")
            erros_part = f" The following extraction issues were identified: {'; '.join(erros_items)}."
        else:
            erros_part = " No access failures were identified during extraction."

        if len(anos) > 1:
            dist_busca_parts = [f"{a}: {por_ano[a]['total_buscado']} records" for a in anos]
            dist_busca_str = f"distributed as follows: {'; '.join(dist_busca_parts)}"
        else:
            dist_busca_str = ""

        cob_anos_str_en = _anos_cobertura_str(anos, "en")

        p_busca = (
            f"The bibliographic search{data_str} was conducted on the {colf} platform "
            f"using SciELO Search ({ver_str.split(';')[0].strip()}), "
            f"with the terms {termos_fmt}{trunc_str}, "
            f"in the {cbf} fields, "
            f"covering {cob_anos_str_en}. "
            f"A total of {total_b} records were retrieved"
            + (f", {dist_busca_str}" if dist_busca_str else "")
            + "."
        )

        p_estrategia = (
            "Metadata extraction in Portuguese (title, abstract, and keywords) was "
            "performed using the SciELO Scraper, employing the **api+html** strategy. "
            "In this approach, the system first queries the ArticleMeta API — a "
            "programming interface maintained by SciELO that provides structured "
            "metadata for indexed articles. When the API returns incomplete data or "
            "no data for a given article (which commonly occurs for Ahead of Print "
            "articles, i.e., articles published online before receiving a definitive "
            "issue number), the system automatically falls back to directly scraping "
            "the HTML of the article page on the SciELO portal. This combined strategy "
            "maximizes the successful extraction rate compared to using only the API "
            "or only HTML scraping."
        )

        p_extracao = (
            f"Extraction yielded {cob_str}"
            + (f" ({cob_por_ano_str})" if cob_por_ano_str else "")
            + f".{tempo_part}{taxa_part}{erros_part} "
            f"The automatic filtering step verified the simultaneous presence of all "
            f"terms in at least one required field ({ccrit_str}), "
            f"identifying {total_ok} articles ({pct_ok:.1f}%) as potentially relevant "
            f"for human curation"
            + (
                f" (annual distribution: "
                + "; ".join(
                    f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                    for a in anos
                ) + ")"
                if len(anos) > 1 else ""
            )
            + "."
        )

        metodologia = p_busca + "\n\n" + p_estrategia + "\n\n" + p_extracao

        if query_url:
            nota_tecnica = (
                "### Technical note — Search URL\n\n"
                "The query was executed at the following URL (may be used as a "
                "footnote or methodological reference):\n\n"
                f"```\n{query_url}\n```"
            )
        else:
            nota_tecnica = ""

        termos_analise_parts = []
        for t in termos:
            partes_t = []
            for c in campos_criterio:
                n   = tc_global.get(t, {}).get(c, 0)
                pct = n / total_ok * 100 if total_ok else 0
                label_c = {"titulo": "title", "resumo": "abstract",
                           "keywords": "keywords"}.get(c, c)
                partes_t.append(f"{n} ({pct:.1f}%) in the {label_c}")
            termos_analise_parts.append(
                f'The term "{t}" was identified in: ' + "; ".join(partes_t) + "."
            )
        termos_analise = " ".join(termos_analise_parts)

        cooc_parts = []
        for c in campos_criterio:
            n_c = cooc_global.get(c, 0)
            if n_c > 0:
                pct_c = n_c / total_ok * 100
                label_c = {"titulo": "title", "resumo": "abstract",
                           "keywords": "keywords"}.get(c, c)
                cooc_parts.append(f"{n_c} ({pct_c:.1f}%) in the {label_c}")
        cooc_str = (
            "Simultaneous co-occurrence of all terms was found in: "
            + "; ".join(cooc_parts) + ". "
        ) if cooc_parts else ""

        top3_str = "; ".join(f"{j} (n={n})" for j, n in top3)
        n_journals_total = len(totais["jornais"])

        resultados = (
            f"{total_ok} ({pct_ok:.1f}%) of the {total_s} extracted articles "
            f"met the automatic filtering criterion and were forwarded for human "
            f"review by the research group."
        )
        if len(anos) > 1:
            dist_ok_parts = [
                f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            ]
            resultados += f" Annual distribution: {'; '.join(dist_ok_parts)}."

        resultados += "\n\n" + termos_analise
        if cooc_str:
            resultados += " " + cooc_str.strip()

        if top3:
            resultados += (
                f"\n\nThe criterion articles were identified across "
                f"{n_journals_total} distinct journals. "
                f"The journals with the highest representation were: {top3_str}."
            )

        limitacoes = (
            "Automated searching with truncation may retrieve articles containing "
            "term stems in contexts unrelated to the main topic of this review, "
            "requiring human curation to validate relevance. "
            "The automatic filtering is based solely on the simultaneous presence "
            f"of terms in selected fields ({ccrit_str}), without semantic or "
            "contextual analysis. "
            "SciELO platform coverage is limited to journals indexed in this "
            "database, and does not include publications in other repositories "
            "(e.g., LILACS, PubMed, Scopus). "
            "Articles in Ahead of Print (AoP) status may not be indexed via the "
            "API and rely on HTML extraction, which may result in lower metadata "
            "stability. "
            "Co-occurrence analysis indicates the presence of terms in the same "
            "fields, but does not guarantee a direct semantic relationship between them."
        )

        n_anos = len(anos)

        def _fig_funil_en() -> str:
            short = (
                "The selection funnel presents three sequential stages of corpus "
                "reduction: retrieval via platform search, metadata extraction by "
                "scraping, and application of the automatic filtering criterion."
            )
            linhas_longa = []
            for a in anos:
                v = por_ano[a]
                tb = v["total_buscado"]
                ts = v["total_scrapeado"]
                tok = v["criterio_ok"]
                pok = v["criterio_ok_pct"]
                pras = ts / tb * 100 if tb else 0
                linhas_longa.append(
                    f"In {a}, {tb} records were retrieved. "
                    f"All {ts} records had metadata extracted ({pras:.1f}%), "
                    f"of which {tok} ({pok:.1f}%) met the filtering criterion."
                )
            if n_anos > 1:
                pok_total = total_ok / total_b * 100 if total_b else 0
                linhas_longa.append(
                    f"Over the full period ({cob_anos_str_en}), the retention rate "
                    f"from search to criterio_ok corpus was "
                    f"{pok_total:.1f}% ({total_ok}/{total_b})."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Short version (expanded caption)\n\n{short}\n\n"
                f"#### Long version (textual substitute)\n\n{long}"
            )

        def _fig_trend_en() -> str:
            if n_anos == 1:
                return (
                    "#### Note\n\n"
                    "Temporal analysis not applicable — only 1 year available in the corpus."
                )
            short = (
                "The chart presents the annual evolution of the number of criterio_ok "
                "articles and their proportion relative to the total extracted."
            )
            pcts = [por_ano[a]["criterio_ok_pct"] for a in anos]
            tendencia = "stable" if max(pcts) - min(pcts) < 3 else (
                "increasing" if pcts[-1] > pcts[0] else "decreasing"
            )
            series = "; ".join(
                f"{a}: {por_ano[a]['criterio_ok']}/{por_ano[a]['total_scrapeado']} "
                f"({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            )
            long = (
                f"The proportion of criterio_ok articles remained {tendencia} "
                f"throughout the analyzed period ({series}), "
                f"ranging from {min(pcts):.1f}% to {max(pcts):.1f}%."
            )
            return (
                f"#### Short version (expanded caption)\n\n{short}\n\n"
                f"#### Long version (textual substitute)\n\n{long}"
            )

        def _fig_heatmap_en() -> str:
            short = (
                f"The heat map displays the relative frequency of each term across "
                f"detected fields, calculated over the {total_ok} criterio_ok articles."
            )
            linhas_longa = []
            for t in termos:
                campo_max = max(campos, key=lambda c: tc_global.get(t, {}).get(c, 0))
                n_max = tc_global.get(t, {}).get(campo_max, 0)
                pct_max = n_max / total_ok * 100 if total_ok else 0
                label_max = {"titulo": "title", "resumo": "abstract",
                             "keywords": "keywords"}.get(campo_max, campo_max)
                outros = [
                    f"{tc_global.get(t,{}).get(c,0)} "
                    f"({tc_global.get(t,{}).get(c,0)/total_ok*100:.1f}%) in the "
                    + {"titulo": "title", "resumo": "abstract",
                       "keywords": "keywords"}.get(c, c)
                    for c in campos if c != campo_max
                ]
                linhas_longa.append(
                    f'Term "{t}" showed the highest occurrence in the {label_max} '
                    f"({n_max}; {pct_max:.1f}%)"
                    + (f", followed by {'; '.join(outros)}" if outros else "")
                    + "."
                )
            if cooc_global:
                campo_cooc = max(cooc_global, key=lambda c: cooc_global.get(c, 0))
                n_cooc = cooc_global[campo_cooc]
                pct_cooc = n_cooc / total_ok * 100 if total_ok else 0
                label_cooc = {"titulo": "title", "resumo": "abstract",
                               "keywords": "keywords"}.get(campo_cooc, campo_cooc)
                linhas_longa.append(
                    f"The field with the highest simultaneous co-occurrence of all "
                    f"terms was {label_cooc} ({n_cooc}; {pct_cooc:.1f}%)."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Short version (expanded caption)\n\n{short}\n\n"
                f"#### Long version (textual substitute)\n\n{long}"
            )

        def _fig_journals_en() -> str:
            n_journals = len(totais["jornais"])
            short = (
                "The chart presents the journals with the highest number of articles "
                "in the criterio_ok corpus, in descending order."
            )
            top3_detalhes = "; ".join(
                f"{j} (n={n}; {n/total_ok*100:.1f}%)" for j, n in top3
            )
            n_top3 = sum(n for _, n in top3)
            pct_top3 = n_top3 / total_ok * 100 if total_ok else 0
            long = (
                f"The {total_ok} criterio_ok articles were distributed across "
                f"{n_journals} distinct journals. "
                f"The three journals with the highest representation were: {top3_detalhes}. "
                f"Together, these three journals accounted for {pct_top3:.1f}% "
                f"({n_top3}/{total_ok}) of the criterio_ok corpus."
            )
            return (
                f"#### Short version (expanded caption)\n\n{short}\n\n"
                f"#### Long version (textual substitute)\n\n{long}"
            )

        def _fig_coverage_en() -> str:
            short = (
                "The chart displays, per year, the proportion of articles with each "
                "Portuguese-language metadata field populated (title, abstract, "
                "and keywords)."
            )
            linhas_longa = []
            for a in anos:
                v    = por_ano[a]
                ts_a = v["total_scrapeado"]
                cob  = v["cobertura_campos"]
                partes = []
                for c in ["titulo", "resumo", "keywords"]:
                    n_c = cob.get(c, 0)
                    pct_c = n_c / ts_a * 100 if ts_a else 0
                    label = {"titulo": "title", "resumo": "abstract",
                             "keywords": "keywords"}.get(c, c)
                    partes.append(f"{pct_c:.1f}% had {label} in Portuguese (n={n_c})")
                linhas_longa.append(f"In {a}: {'; '.join(partes)}.")
            if ok_parc_total:
                linhas_longa.append(
                    f"The partial extraction recorded ({ok_parc_total} article(s)) "
                    "did not significantly affect corpus completeness."
                )
            else:
                linhas_longa.append(
                    "No partial extractions were recorded; all articles presented "
                    "complete metadata coverage."
                )
            long = " ".join(linhas_longa)
            return (
                f"#### Short version (expanded caption)\n\n{short}\n\n"
                f"#### Long version (textual substitute)\n\n{long}"
            )

        figuras_section = (
            "The following sections describe each generated figure in two versions: "
            "a **short version**, suitable as an expanded caption in scientific "
            "publications, and a **long version**, which fully replaces the figure "
            "when the publication format does not allow images.\n"
        )
        fig_num = 1
        figuras_section += (
            f"\n### Figure {fig_num} — Selection funnel "
            f"([{arq_funnel}]({arq_funnel}))\n\n"
            + _fig_funil_en()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figure {fig_num} — Temporal trend "
            f"([{arq_trend}]({arq_trend}))\n\n"
            + _fig_trend_en()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figure {fig_num} — Term distribution by field "
            f"([{arq_heatmap}]({arq_heatmap}))\n\n"
            + _fig_heatmap_en()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figure {fig_num} — Journals with highest representation "
            f"([{arq_journals}]({arq_journals}))\n\n"
            + _fig_journals_en()
        )
        fig_num += 1
        figuras_section += (
            f"\n\n### Figure {fig_num} — Portuguese metadata coverage "
            f"([{arq_coverage}]({arq_coverage}))\n\n"
            + _fig_coverage_en()
        )

    # ── Seção de artefatos ────────────────────────────────────────────────────
    artefatos_section = _gerar_artefatos_section(lang)

    # ── Escrever arquivo ──────────────────────────────────────────────────────
    aviso_pt = (
        "> **Aviso:** Este documento e todos os artefatos gerados são **sugestões "
        "publicáveis** produzidas automaticamente a partir dos dados extraídos. "
        "Recomenda-se revisão crítica pelo pesquisador responsável antes da "
        "submissão ou publicação."
    )
    aviso_en = (
        "> **Notice:** This document and all generated artifacts are **publishable "
        "suggestions** automatically produced from the extracted data. Critical "
        "review by the responsible researcher is recommended prior to submission "
        "or publication."
    )
    aviso = aviso_pt if lang == "pt" else aviso_en

    sec_figuras = "## Descrição dos resultados por figura" if lang == "pt" \
        else "## Figure descriptions"
    sec_nota    = "## Nota técnica" if lang == "pt" else "## Technical note"

    dest = output / f"results_text{lang_suf}.md"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(
            f"<!-- Gerado por results_report.py v{__version__} "
            f"em {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n\n"
        )
        f.write(aviso + "\n\n")
        f.write(s("sec_metodologia", lang) + "\n\n")
        f.write(metodologia + "\n\n")
        if nota_tecnica:
            f.write(sec_nota + "\n\n")
            f.write(nota_tecnica + "\n\n")
        f.write(s("sec_resultados", lang) + "\n\n")
        f.write(resultados.strip() + "\n\n")
        f.write(s("sec_limitacoes", lang) + "\n\n")
        f.write(limitacoes + "\n\n")
        f.write(sec_figuras + "\n\n")
        f.write(figuras_section + "\n\n")
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


def _origem(args) -> dict:
    """Reconstrói o comando CLI que gerou este relatório, para rastreabilidade."""
    cmd = ["uv", "run", "python", "results_report.py"]
    if args.scrape_dir:
        cmd += ["--scrape-dir", str(args.scrape_dir)]
    else:
        if args.base:
            cmd += ["--base", str(args.base)]
        if args.years:
            cmd += ["--years"] + [str(y) for y in args.years]
        if args.mode != "api+html":
            cmd += ["--mode", args.mode]
    if args.output_dir:
        cmd += ["--output-dir", str(args.output_dir)]
    if args.lang != "pt":
        cmd += ["--lang", args.lang]
    if args.top_journals != 15:
        cmd += ["--top-journals", str(args.top_journals)]
    if getattr(args, "style", None):
        cmd += ["--style", args.style]
    if getattr(args, "colormap", None) and args.colormap != _COLORMAP_DEFAULT:
        cmd += ["--colormap", args.colormap]
    return {
        "comando": " ".join(cmd),
        "argv": sys.argv[1:],
        "cwd": str(Path.cwd()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Alias -? → --help
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    # --list-colormaps: antes do parser para resposta imediata
    if "--list-colormaps" in sys.argv:
        print(f"Colormaps disponíveis ({len(COLORMAPS_DISPONIVEIS)}):\n")
        for cm in COLORMAPS_DISPONIVEIS:
            marker = " ← default" if cm == _COLORMAP_DEFAULT else ""
            print(f"  {cm}{marker}")
        print(f"\nUso: --colormap <nome>   ex: --colormap plasma")
        sys.exit(0)

    # --list-styles: antes do parser para resposta imediata
    if "--list-styles" in sys.argv:
        estilos = sorted(plt.style.available)
        print(f"Estilos matplotlib disponíveis ({len(estilos)}):\n")
        # Exibe em colunas de 3
        col_w = max(len(e) for e in estilos) + 2
        cols  = 3
        for i in range(0, len(estilos), cols):
            print("  " + "".join(e.ljust(col_w) for e in estilos[i:i+cols]))
        print(f"\nUso: --style <nome>   ex: --style ggplot")
        sys.exit(0)

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
        "--style", default=None, metavar="NOME",
        help="Estilo matplotlib para os gráficos (ex: ggplot, seaborn-v0_8, bmh). "
             "Use --list-styles para ver todos os disponíveis.",
    )
    parser.add_argument(
        "--list-styles", action="store_true",
        help="Lista todos os estilos matplotlib disponíveis e sai.",
    )
    parser.add_argument(
        "--colormap", default=None, metavar="NOME",
        choices=COLORMAPS_DISPONIVEIS,
        help=f"Colormap sequencial para o heatmap: "
             f"{', '.join(COLORMAPS_DISPONIVEIS)} (default: {_COLORMAP_DEFAULT}). "
             "Use --list-colormaps para descrição visual.",
    )
    parser.add_argument(
        "--list-colormaps", action="store_true",
        help="Lista os colormaps disponíveis e sai.",
    )
    _aliases_str = ", ".join(sorted(k for k in ARTEFATO_ALIASES if not k.startswith("results_")))
    parser.add_argument(
        "--artifacts", nargs="+", metavar="ALIAS",
        help=f"Gera APENAS estes artefatos. Aliases: {_aliases_str}",
    )
    parser.add_argument(
        "--skip-artifacts", nargs="+", metavar="ALIAS",
        help="Pula estes artefatos (gera todos os demais).",
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

    # Aplicar estilo matplotlib
    estilo_ativo = args.style or "default"
    if args.style:
        if args.style not in plt.style.available:
            estilos_prox = [e for e in plt.style.available if args.style.lower() in e.lower()]
            sugestao = f"  Sugestões: {', '.join(estilos_prox[:5])}" if estilos_prox else ""
            print(f"❌  Estilo '{args.style}' não encontrado.{sugestao}", file=sys.stderr)
            print(f"    Use --list-styles para ver os disponíveis.", file=sys.stderr)
            sys.exit(1)
        plt.style.use(args.style)

    # Aplicar colormap
    colormap_ativo = getattr(args, "colormap", None) or _COLORMAP_DEFAULT
    if getattr(args, "colormap", None):
        if args.colormap not in COLORMAPS_DISPONIVEIS:
            print(f"❌  Colormap '{args.colormap}' inválido.", file=sys.stderr)
            print(f"    Disponíveis: {', '.join(COLORMAPS_DISPONIVEIS)}", file=sys.stderr)
            sys.exit(1)
    global _colormap_ativo
    _colormap_ativo = colormap_ativo

    # Sufixo de estilo para nomes de arquivo (só inclui quando não é default)
    # Caracteres problemáticos em nomes de arquivo são substituídos por _
    def _safe_name(nome: str) -> str:
        import re
        return re.sub(r"[^\w\-]", "_", nome)

    style_suf = f"_{_safe_name(estilo_ativo)}" if estilo_ativo != "default" else ""
    cmap_suf  = f"_{colormap_ativo}"           if colormap_ativo != _COLORMAP_DEFAULT else ""

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
    print(f"Estilo gráficos  : {estilo_ativo}")
    print(f"Colormap         : {colormap_ativo}")

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

    # Sufixo composto: _<style>_<colormap>_<lang>
    # style_suf e cmap_suf são vazios quando usam o valor default
    def _make_suf(lang: str) -> str:
        return f"{style_suf}{cmap_suf}_{lang}"

    artefatos = []
    for lang in langs_a_gerar:
        suf = _make_suf(lang)
        artefatos += [
            f"{s('arquivo_funnel',   lang)}{suf}.png",
            f"{s('arquivo_trend',    lang)}{suf}.png",
            f"{s('arquivo_heatmap',  lang)}{suf}.png",
            f"{s('arquivo_journals', lang)}{suf}.png",
            f"{s('arquivo_coverage', lang)}{suf}.png",
            f"{s('arquivo_venn',     lang)}{suf}.png",
            f"results_text{suf}.md",
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

    todas_rows = [r for rows in rows_por_ano.values() for r in rows]

    # Filtro de artefatos (--artifacts / --skip-artifacts)
    _ativos = _todos_ativos = _TODOS_NOMES.copy()
    if getattr(args, "artifacts", None):
        _ativos = _resolver_artefatos(args.artifacts)
    if getattr(args, "skip_artifacts", None):
        _ativos = _ativos - _resolver_artefatos(args.skip_artifacts)

    def _ativo(nome: str) -> bool:
        return ARTEFATO_ALIASES.get(nome, nome) in _ativos

    for lang in langs_a_gerar:
        suf = _make_suf(lang)
        if len(langs_a_gerar) > 1:
            print(f"  [{lang.upper()}]")
        if _ativo("funnel"):
            grafico_funnel(stats, output, lang, suf)
        if _ativo("trend"):
            grafico_trend(stats, output, lang, suf)
        if _ativo("heatmap"):
            grafico_heatmap(stats, output, lang, suf)
        if _ativo("journals"):
            grafico_journals(stats, output, args.top_journals, lang, suf)
        if _ativo("coverage"):
            grafico_coverage(stats, output, lang, suf)
        if _ativo("venn"):
            grafico_venn(todas_rows, termos, campos, stats, output, lang, suf)
        if _ativo("text"):
            gerar_texto(stats, output, lang, suf)

    if _ativo("table_summary"):
        salvar_table_summary(stats, output)
    if _ativo("table_terms"):
        salvar_table_terms(stats, output)
    if _ativo("table_journals"):
        salvar_table_journals(stats, output)
    stats["estilo_grafico"] = estilo_ativo
    stats["colormap"]       = colormap_ativo
    stats["origem"] = _origem(args)
    salvar_json(stats, output)

    print(f"\nPronto. Artefatos em: {output.resolve()}")


if __name__ == "__main__":
    main()
