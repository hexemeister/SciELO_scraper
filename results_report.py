"""
results_report.py — Artefatos científicos publication-ready do projeto e-Aval.

Propósito: gerar o arcabouço completo de resultados científicos a partir do CSV
produzido pelo terms_matcher.py. Não fala sobre o processo técnico — para isso
use process_charts.py.

Contexto: ferramenta do projeto "Estado da Arte da Avaliação" (e-Aval), grupo de
pesquisa do Mestrado Profissional em Avaliação da Fundação Cesgranrio. Os artigos
com criterio_ok=True serão encaminhados para curadoria humana antes de integrar
o banco de dados público (https://eavaleducacao1.websiteseguro.com/).

Artefatos gerados em runs/<ano>/<stem_scraping>_results/ (ou --output-dir):
    Gráficos:
        results_funnel.png          — funil: buscado → scrapeado → criterio_ok
        results_trend.png           — evolução temporal de criterio_ok por ano
        results_terms_heatmap.png   — heatmap termos × campos (% de ocorrência)
        results_journals.png        — top periódicos por n artigos criterio_ok
        results_coverage.png        — % de artigos com cada campo PT presente

    Tabelas (CSV):
        results_table_summary.csv   — funil por ano + totais
        results_table_terms.csv     — por termo × campo: n e % de ocorrência
        results_table_journals.csv  — periódicos com contagem e % (todos, sem limite)

    Texto (Markdown):
        results_text.md             — seções: Metodologia e Resultados

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

__version__ = "1.0"

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
        "pt": "Scrapeados\n(dados extraídos)",
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
        "pt": "Keywords",
        "en": "Keywords",
    },
    # Legenda cobertura
    "legenda_ano": {
        "pt": "Ano",
        "en": "Year",
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
    # Notas
    "nota_heatmap": {
        "pt": "Base: artigos com criterio_ok=True. Valores = % dos artigos em que o termo aparece no campo.",
        "en": "Base: articles with criterio_ok=True. Values = % of articles where the term appears in the field.",
    },
    "nota_funnel": {
        "pt": "criterio_ok: todos os termos presentes em pelo menos um campo required (padrão: título ou keywords).",
        "en": "criterio_ok: all terms present in at least one required field (default: title or keywords).",
    },
    # Arquivos de saída
    "arquivo_funnel":   {"pt": "results_funnel",         "en": "results_funnel"},
    "arquivo_trend":    {"pt": "results_trend",          "en": "results_trend"},
    "arquivo_heatmap":  {"pt": "results_terms_heatmap",  "en": "results_terms_heatmap"},
    "arquivo_journals": {"pt": "results_journals",       "en": "results_journals"},
    "arquivo_coverage": {"pt": "results_coverage",       "en": "results_coverage"},
    "arquivo_texto":    {"pt": "results_text",           "en": "results_text"},
}


def s(chave: str, lang: str) -> str:
    return STRINGS[chave].get(lang, STRINGS[chave]["pt"])


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
    # exclui arquivos de stats
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
    # Ordenar campos na ordem canônica
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

    # Por ano
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

        # Periódicos (base: criterio_ok=True)
        jornais: dict[str, int] = defaultdict(int)
        for r in rows_ok:
            j = r.get("Journal", r.get("Source", "")).strip()
            if j:
                jornais[j] += 1

        # Total buscado — do params.json ou fallback para len(rows)
        params = params_por_ano.get(ano, {})
        total_buscado = params.get("total_resultados", total)
        termos_busca  = params.get("termos_originais", termos)
        colecao       = params.get("colecao", "scl")
        truncamento   = params.get("truncamento", True)
        campos_busca  = params.get("campos", "ti+ab")

        por_ano[ano] = {
            "total_buscado":    total_buscado,
            "total_scrapeado":  total,
            "ok_completo":      ok_completo,
            "ok_parcial":       ok_parcial,
            "criterio_ok":      criterio_ok,
            "criterio_ok_pct":  criterio_ok / total * 100 if total else 0,
            "cobertura_campos": cobertura_campos,
            "termos_campos":    termos_campos,
            "jornais":          dict(jornais),
            "termos_busca":     termos_busca,
            "colecao":          colecao,
            "truncamento":      truncamento,
            "campos_busca":     campos_busca,
        }

    # Totais globais
    total_b = sum(v["total_buscado"]   for v in por_ano.values())
    total_s = sum(v["total_scrapeado"] for v in por_ano.values())
    total_c = sum(v["criterio_ok"]     for v in por_ano.values())
    total_r = sum(v["total_scrapeado"] for v in por_ano.values())

    jornais_global: dict[str, int] = defaultdict(int)
    termos_campos_global: dict[str, dict[str, int]] = {t: {c: 0 for c in campos} for t in termos}
    for v in por_ano.values():
        for j, n in v["jornais"].items():
            jornais_global[j] += n
        for t in termos:
            for c in campos:
                termos_campos_global[t][c] += v["termos_campos"].get(t, {}).get(c, 0)

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
        },
    }


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------

CORES_FUNNEL = ["#2980b9", "#27ae60", "#e67e22"]
CORES_CAMPOS = {"titulo": "#3498db", "resumo": "#2ecc71", "keywords": "#e67e22"}
CORES_ANOS   = ["#2980b9", "#27ae60", "#e67e22", "#8e44ad", "#c0392b",
                 "#16a085", "#d35400", "#2c3e50"]


def grafico_funnel(stats: dict, output: Path, lang: str = "pt"):
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

        # % relativas
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
    dest = output / f"{s('arquivo_funnel', lang)}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_trend(stats: dict, output: Path, lang: str = "pt"):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]

    vals_ok    = [por_ano[a]["criterio_ok"]     for a in anos]
    vals_total = [por_ano[a]["total_scrapeado"] for a in anos]
    pcts       = [v["criterio_ok_pct"]          for v in [por_ano[a] for a in anos]]

    fig, ax1 = plt.subplots(figsize=(max(7, 2 * len(anos)), 5))
    fig.suptitle(s("titulo_trend", lang), fontsize=13, fontweight="bold")

    x = np.arange(len(anos))
    w = 0.35

    ax1.bar(x - w/2, vals_total, w, label="total scrapeado", color="#bdc3c7", zorder=2)
    ax1.bar(x + w/2, vals_ok,    w, label="criterio_ok",     color="#27ae60", zorder=2)
    ax1.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax1.set_axisbelow(True)
    ax1.set_ylabel(s("eixo_n_artigos", lang), fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(a) for a in anos], fontsize=11)
    ax1.set_xlabel(s("eixo_ano", lang), fontsize=11)

    ax2 = ax1.twinx()
    ax2.plot(x, pcts, "o--", color="#e74c3c", linewidth=2, markersize=7, label="% criterio_ok")
    ax2.set_ylabel("% criterio_ok", fontsize=11, color="#e74c3c")
    ax2.tick_params(axis="y", labelcolor="#e74c3c")
    ax2.set_ylim(0, 110)

    # Anotar % em cada ponto
    for xi, pct in zip(x, pcts):
        ax2.text(xi, pct + 3, f"{pct:.1f}%", ha="center", fontsize=9,
                 color="#e74c3c", fontweight="bold")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    plt.tight_layout()
    dest = output / f"{s('arquivo_trend', lang)}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_heatmap(stats: dict, output: Path, lang: str = "pt"):
    termos  = stats["termos"]
    campos  = stats["campos"]
    totais  = stats["totais"]
    total_ok = totais["criterio_ok"]

    if not termos or not campos or total_ok == 0:
        print("  ⚠ Heatmap pulado — sem dados de termos/campos.")
        return

    tc = totais["termos_campos"]
    # Matriz: linhas=termos, colunas=campos
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
    dest = output / f"{s('arquivo_heatmap', lang)}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_journals(stats: dict, output: Path, top_n: int = 15, lang: str = "pt"):
    jornais = stats["totais"]["jornais"]
    if not jornais:
        print("  ⚠ Gráfico de periódicos pulado — sem dados.")
        return

    total_ok = stats["totais"]["criterio_ok"]
    top = sorted(jornais.items(), key=lambda x: x[1], reverse=True)[:top_n]
    nomes = [t[0] for t in top]
    vals  = [t[1] for t in top]

    # Truncar nomes longos
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
    dest = output / f"{s('arquivo_journals', lang)}.png"
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


def grafico_coverage(stats: dict, output: Path, lang: str = "pt"):
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

    fig, ax = plt.subplots(figsize=(max(7, 2 * len(anos)), 5))
    fig.suptitle(s("titulo_coverage", lang), fontsize=13, fontweight="bold")

    for i, campo in enumerate(campos_disponiveis):
        pcts = []
        for ano in anos:
            total = por_ano[ano]["total_scrapeado"]
            n_ok  = por_ano[ano]["cobertura_campos"].get(campo, 0)
            pcts.append(n_ok / total * 100 if total else 0)

        offset = (i - n_campos / 2 + 0.5) * width
        bars = ax.bar(x + offset, pcts, width,
                      label=campo_labels[campo],
                      color=CORES_CAMPOS[campo],
                      edgecolor="white", linewidth=0.5)
        for bar, pct in zip(bars, pcts):
            if pct > 3:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{pct:.1f}%", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([str(a) for a in anos], fontsize=11)
    ax.set_xlabel(s("eixo_ano", lang), fontsize=11)
    ax.set_ylabel(s("eixo_pct", lang), fontsize=11)
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(title=s("eixo_campo", lang), fontsize=10)

    plt.tight_layout()
    dest = output / f"{s('arquivo_coverage', lang)}.png"
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
        # Linha de totais
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

    # Calcular anos presentes por jornal
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
    if len(anos) == 1:
        return str(anos[0])
    if anos == list(range(anos[0], anos[-1] + 1)):
        return f"{anos[0]}–{anos[-1]}" if lang == "pt" else f"{anos[0]} to {anos[-1]}"
    return ", ".join(str(a) for a in anos)


def gerar_texto(stats: dict, output: Path, lang: str = "pt"):
    anos    = stats["anos"]
    por_ano = stats["por_ano"]
    totais  = stats["totais"]
    termos  = stats["termos"]

    # Pegar metadados da busca do primeiro ano disponível
    primeiro_ano = por_ano[anos[0]]
    termos_busca = primeiro_ano.get("termos_busca", termos)
    colecao      = primeiro_ano.get("colecao", "scl")
    truncamento  = primeiro_ano.get("truncamento", True)
    campos_busca = primeiro_ano.get("campos_busca", "ti+ab")

    anos_str = _anos_str(anos, lang)
    total_b  = totais["total_buscado"]
    total_s  = totais["total_scrapeado"]
    total_ok = totais["criterio_ok"]
    pct_ok   = totais["criterio_ok_pct"]

    # Top 3 periódicos
    top3 = sorted(totais["jornais"].items(), key=lambda x: x[1], reverse=True)[:3]
    top3_str = "; ".join(f"{j} (n={n})" for j, n in top3)

    # Termo mais frequente no título (base criterio_ok)
    if termos and "titulo" in stats["campos"]:
        termo_titulo_max = max(
            termos,
            key=lambda t: totais["termos_campos"].get(t, {}).get("titulo", 0)
        )
        n_titulo_max = totais["termos_campos"].get(termo_titulo_max, {}).get("titulo", 0)
        pct_titulo_max = _pct(n_titulo_max, total_ok)
    else:
        termo_titulo_max = ""
        pct_titulo_max = ""

    if lang == "pt":
        termos_busca_fmt = " e ".join(f'"{t}"' for t in termos_busca)
        trunc_str = " com truncamento automático (operador $)" if truncamento else ""
        campos_busca_fmt = {
            "ti+ab": "título e resumo",
            "ti":    "título",
            "ab":    "resumo",
        }.get(campos_busca, campos_busca)
        colecao_fmt = {"scl": "SciELO Brasil", "arg": "SciELO Argentina"}.get(colecao, colecao)

        metodologia = f"""\
A busca bibliográfica foi realizada na plataforma SciELO ({colecao_fmt}), \
utilizando os termos {termos_busca_fmt}{trunc_str}, \
nos campos de {campos_busca_fmt}, \
abrangendo os anos {anos_str}. \
Foram recuperados {total_b} registros. \
Os metadados em português (título, resumo e palavras-chave) foram extraídos \
por meio do script SciELO Scraper (estratégia api+html), \
resultando em {total_s} artigos com dados disponíveis para análise. \
A etapa de filtragem automática verificou a presença simultânea de todos os termos \
em pelo menos um dos campos requeridos (título ou palavras-chave), \
identificando {total_ok} artigos ({pct_ok:.1f}%) como potencialmente relevantes \
para curadoria humana."""

        resultados = f"""\
Dos {total_s} artigos recuperados e processados, \
{total_ok} ({pct_ok:.1f}%) atenderam ao critério de filtragem automática \
e foram encaminhados para verificação humana pelo grupo de pesquisa. \
"""
        if len(anos) > 1:
            por_ano_str = "; ".join(
                f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            )
            resultados += f"A distribuição por ano foi: {por_ano_str}. "

        if top3:
            resultados += f"Os periódicos com maior número de artigos foram: {top3_str}. "

        if termo_titulo_max:
            resultados += (
                f"O termo \"{termo_titulo_max}\" foi encontrado no título de "
                f"{n_titulo_max} artigos ({pct_titulo_max} do corpus filtrado)."
            )

    else:  # en
        termos_busca_fmt = " and ".join(f'"{t}"' for t in termos_busca)
        trunc_str = " with automatic truncation ($ operator)" if truncamento else ""
        campos_busca_fmt = {
            "ti+ab": "title and abstract",
            "ti":    "title",
            "ab":    "abstract",
        }.get(campos_busca, campos_busca)
        colecao_fmt = {"scl": "SciELO Brazil", "arg": "SciELO Argentina"}.get(colecao, colecao)

        metodologia = f"""\
The bibliographic search was conducted on the {colecao_fmt} platform, \
using the terms {termos_busca_fmt}{trunc_str}, \
in the {campos_busca_fmt} fields, \
covering the years {anos_str}. \
A total of {total_b} records were retrieved. \
Portuguese-language metadata (title, abstract, and keywords) were extracted \
using the SciELO Scraper script (api+html strategy), \
yielding {total_s} articles with data available for analysis. \
The automatic filtering step verified the simultaneous presence of all terms \
in at least one required field (title or keywords), \
identifying {total_ok} articles ({pct_ok:.1f}%) as potentially relevant \
for human curation."""

        resultados = f"""\
Of the {total_s} articles retrieved and processed, \
{total_ok} ({pct_ok:.1f}%) met the automatic filtering criterion \
and were forwarded for human review by the research group. \
"""
        if len(anos) > 1:
            por_ano_str = "; ".join(
                f"{a}: n={por_ano[a]['criterio_ok']} ({por_ano[a]['criterio_ok_pct']:.1f}%)"
                for a in anos
            )
            resultados += f"Annual distribution: {por_ano_str}. "

        if top3:
            resultados += f"Journals with the most articles were: {top3_str}. "

        if termo_titulo_max:
            resultados += (
                f'The term "{termo_titulo_max}" was found in the title of '
                f"{n_titulo_max} articles ({pct_titulo_max} of the filtered corpus)."
            )

    lang_suffix = f"_{lang}" if lang != "pt" else ""
    dest = output / f"results_text{lang_suffix}.md"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(f"<!-- Gerado por results_report.py v{__version__} em {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n\n")
        f.write(s("sec_metodologia", lang) + "\n\n")
        f.write(metodologia + "\n\n")
        f.write(s("sec_resultados", lang) + "\n\n")
        f.write(resultados + "\n")
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
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

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
             "Ignora --base/--years/--mode e lê o terms_*.csv desta pasta. "
             "Útil quando chamado pelo pipeline antes da cópia para runs/<ano>/.",
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
    args = parser.parse_args()

    langs_a_gerar = IDIOMAS_DISPONIVEIS if args.lang == "all" else [args.lang]

    # Carregar dados por ano
    rows_por_ano:     dict[int, list[dict]] = {}
    params_por_ano:   dict[int, dict]       = {}
    stats_json_por_ano: dict[int, dict]     = {}
    stem_por_ano:     dict[int, str]        = {}

    if args.scrape_dir:
        # Modo direto: pasta de scraping passada explicitamente (uso pelo pipeline)
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
        # Determinar ano a partir dos dados ou do params.json no diretório pai
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
            # fallback: Publication year do CSV
            anos_set: set[int] = set()
            for r in rows:
                yr = r.get("Publication year", "").strip()
                if yr.isdigit():
                    anos_set.add(int(yr))
            anos_dados = sorted(anos_set) if anos_set else [0]
        # Agrupa tudo num ano "virtual" = primeiro ano encontrado
        ano_key = anos_dados[0] if len(anos_dados) == 1 else anos_dados[0]
        rows_por_ano[ano_key]       = rows
        params_por_ano[ano_key]     = params_data
        try:
            stats_json_por_ano[ano_key] = carregar_stats_json(pasta)
        except FileNotFoundError:
            stats_json_por_ano[ano_key] = {}
        stem_por_ano[ano_key] = pasta.name
        # Se múltiplos anos no mesmo CSV, cria entradas separadas por ano
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

    # Detectar termos e campos das colunas do CSV
    todas_rows = [r for rows in rows_por_ano.values() for r in rows]
    termos, campos = detectar_termos_e_campos(todas_rows)

    print(f"\nAnos carregados  : {sorted(rows_por_ano)}")
    print(f"Modo             : {args.mode}")
    print(f"Termos detectados: {termos}")
    print(f"Campos detectados: {campos}")
    print(f"Idioma(s)        : {', '.join(langs_a_gerar)}")

    # Calcular stats
    stats = calcular_stats(rows_por_ano, termos, campos, params_por_ano, stats_json_por_ano)

    # Determinar pasta de saída
    if args.output_dir:
        output = Path(args.output_dir)
    elif args.scrape_dir:
        # Modo --scrape-dir sem --output-dir: cria results_<stem>/ ao lado da pasta de scraping
        pasta_sd = Path(args.scrape_dir)
        output = pasta_sd.parent / f"results_{pasta_sd.name}"
    else:
        # Modo --base: cria results_<stem>/ dentro do ano mais recente
        ultimo_ano = sorted(rows_por_ano)[-1]
        stem = stem_por_ano[ultimo_ano]
        output = base / str(ultimo_ano) / f"results_{stem}"

    print(f"Pasta de saída   : {output.resolve()}")

    artefatos = []
    for lang in langs_a_gerar:
        lang_suf = f"_{lang}" if args.lang == "all" else ""
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
        if len(langs_a_gerar) > 1:
            print(f"  [{lang.upper()}]")
        grafico_funnel(stats, output, lang)
        grafico_trend(stats, output, lang)
        grafico_heatmap(stats, output, lang)
        grafico_journals(stats, output, args.top_journals, lang)
        grafico_coverage(stats, output, lang)
        gerar_texto(stats, output, lang)

    salvar_table_summary(stats, output)
    salvar_table_terms(stats, output)
    salvar_table_journals(stats, output)
    salvar_json(stats, output)

    print(f"\nPronto. Artefatos em: {output.resolve()}")


if __name__ == "__main__":
    main()
