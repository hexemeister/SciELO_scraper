"""
process_charts.py — Gráficos de diagnóstico técnico do processo de extração SciELO.

Propósito: visualizar COMO o scraping correu (taxas de sucesso, fontes de extração,
tempo). Não fala sobre os resultados científicos — para isso use results_report.py.

Uso:
    uv run python process_charts.py                            # pastas *_s_*/ mais recentes no dir atual
    uv run python process_charts.py --stem sc_20260418_123456  # busca pastas do stem específico (determinístico)
    uv run python process_charts.py --base runs                # varre runs/<ano>/ (multi-ano)
    uv run python process_charts.py --base runs --years 2022 2024
    uv run python process_charts.py --output graficos/         # pasta de saída personalizada
    uv run python process_charts.py --timestamp                # adiciona timestamp nos nomes dos PNGs
    uv run python process_charts.py --lang en                  # gráficos em inglês
    uv run python process_charts.py --lang all                 # gera em todos os idiomas disponíveis
    uv run python process_charts.py --no-status                # pula gráfico de status
    uv run python process_charts.py --no-sources               # pula gráfico de fontes
    uv run python process_charts.py --no-time                  # pula gráfico de tempo
    uv run python process_charts.py --dry-run                  # mostra o que faria sem gravar nada
    uv run python process_charts.py -?                         # ajuda (equivalente a -h)

Gráficos gerados (salvo na pasta --output, default: diretório atual):
    chart_status[_<lang>][_<ts>].png   — distribuição de status por modo e ano
    chart_sources[_<lang>][_<ts>].png  — fontes de extração por modo e ano
    chart_time[_<lang>][_<ts>].png     — tempo total por modo e ano

Notas:
    --stem  garante busca determinística no modo padrão (sem --base): usa exatamente
            as pastas <stem>_s_*_<modo>/ em vez do CSV mais recente no diretório.
            Útil quando há múltiplos runs no mesmo diretório (ex: pipeline --per-year).
    --lang  pt (default) | en | all. Com 'all', gera um PNG por idioma com sufixo _pt/_en.
            Novos idiomas podem ser adicionados ao dicionário STRINGS no código.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Garantir UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------

IDIOMAS_DISPONIVEIS = ["pt", "en"]

STRINGS: dict[str, dict[str, str]] = {
    # Títulos dos gráficos
    "titulo_status": {
        "pt": "Distribuição de status por modo de extração",
        "en": "Extraction status distribution by mode",
    },
    "titulo_fontes": {
        "pt": "Fontes de extração — modo api+html (padrão)",
        "en": "Extraction sources — api+html mode (default)",
    },
    "titulo_tempo": {
        "pt": "Tempo total de extração por ano e modo",
        "en": "Total extraction time by year and mode",
    },
    # Eixos
    "eixo_y_pct": {
        "pt": "% artigos",
        "en": "% articles",
    },
    "eixo_y_tempo": {
        "pt": "Tempo (minutos)",
        "en": "Time (minutes)",
    },
    "eixo_x_ano": {
        "pt": "Ano",
        "en": "Year",
    },
    "legenda_modo": {
        "pt": "Modo",
        "en": "Mode",
    },
    # Rótulos de modos
    "modo_apimaishtml": {
        "pt": "api+html\n(padrão)",
        "en": "api+html\n(default)",
    },
    "modo_api": {
        "pt": "apenas-api",
        "en": "api-only",
    },
    "modo_html": {
        "pt": "apenas-html",
        "en": "html-only",
    },
    # Fontes de extração
    "fonte_api": {
        "pt": "ArticleMeta API",
        "en": "ArticleMeta API",
    },
    "fonte_fallback_apimaishtml": {
        "pt": "Fallback API+HTML",
        "en": "Fallback API+HTML",
    },
    "fonte_fallback_html": {
        "pt": "Fallback HTML",
        "en": "Fallback HTML",
    },
    "fonte_falha": {
        "pt": "Falha de acesso (erro HTTP)",
        "en": "Access failure (HTTP error)",
    },
    # Cabeçalhos de tabela (chart_status)
    "tab_modo": {
        "pt": "modo",
        "en": "mode",
    },
    "tab_ok_parcial": {
        "pt": "ok_parcial",
        "en": "ok_partial",
    },
    "tab_erro": {
        "pt": "erro_extracao",
        "en": "extraction_error",
    },
    # Cabeçalhos de tabela (chart_sources)
    "tab_ano": {
        "pt": "Ano",
        "en": "Year",
    },
    "tab_n_total": {
        "pt": "n total",
        "en": "n total",
    },
    # Notas de rodapé
    "nota_status": {
        "pt": "Valores em vermelho = < 1% do total  |  Tabela inset: n exatos por modo",
        "en": "Values in red = < 1% of total  |  Inset table: exact n per mode",
    },
    "nota_fontes": {
        "pt": (
            "ArticleMeta API: todos os campos extraídos diretamente da API  |  "
            "Fallback API+HTML: API retornou dados parciais; campos faltantes complementados via HTML  |  "
            "Fallback HTML: API não retornou dados; artigo extraído inteiramente via HTML  |  "
            "Falha de acesso: erro HTTP (ex.: 404), sem dados"
        ),
        "en": (
            "ArticleMeta API: all fields extracted directly from the API  |  "
            "Fallback API+HTML: API returned partial data; missing fields retrieved via HTML  |  "
            "Fallback HTML: API returned nothing; article fully extracted via HTML  |  "
            "Access failure: HTTP error (e.g. 404), no data"
        ),
    },
    # Nomes de arquivo (sem extensão)
    "arquivo_status": {
        "pt": "chart_status",
        "en": "chart_status",
    },
    "arquivo_fontes": {
        "pt": "chart_sources",
        "en": "chart_sources",
    },
    "arquivo_tempo": {
        "pt": "chart_time",
        "en": "chart_time",
    },
}


def s(chave: str, lang: str) -> str:
    """Retorna a string localizada para a chave e idioma dados."""
    return STRINGS[chave].get(lang, STRINGS[chave]["pt"])


# ---------------------------------------------------------------------------
# Descoberta automática de pastas
# ---------------------------------------------------------------------------

MODO_SUFIXO = {
    "api+html": re.compile(r"_api\+html$"),
    "api":      re.compile(r"_api$"),
    "html":     re.compile(r"_html$"),
}


def descobrir_anos(base: Path) -> list[int]:
    """Retorna lista de anos (pastas numéricas) dentro de base/, ordenada."""
    anos = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name.isdigit():
            anos.append(int(p.name))
    return anos


def descobrir_pasta_modo(ano_dir: Path, modo: str) -> Path | None:
    """
    Procura a pasta de scraping mais recente para um dado modo dentro de ano_dir.
    Padrão: <stem>_s_<timestamp>_<modo>/
    """
    padrao = MODO_SUFIXO[modo]
    candidatas = [
        p for p in ano_dir.iterdir()
        if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
    ]
    if not candidatas:
        return None
    return sorted(candidatas)[-1]


def descobrir_pastas_cwd(cwd: Path, stem: str | None = None) -> dict[str, Path]:
    """
    Modo padrão (sem --base): descobre as pastas <stem>_s_*_<modo>/ no diretório atual.

    Se stem for fornecido (ex: "sc_20260418_123456"), filtra exatamente por esse stem.
    Caso contrário, usa o sc_*.csv mais recente como referência.
    Retorna {modo: pasta} com apenas os modos encontrados (com stats.json).
    """
    if stem is None:
        csvs = sorted(cwd.glob("sc_*.csv"), reverse=True)
        if not csvs:
            return {}
        stem = csvs[0].stem   # ex: sc_20260415_223214

    resultado: dict[str, Path] = {}
    for modo, padrao in MODO_SUFIXO.items():
        candidatas = [
            p for p in cwd.iterdir()
            if p.is_dir()
            and p.name.startswith(stem + "_s_")
            and padrao.search(p.name)
            and (p / "stats.json").exists()
        ]
        if candidatas:
            resultado[modo] = sorted(candidatas)[-1]
    return resultado


def _label_do_stem(stem: str, cwd: Path) -> str:
    """
    Resolve o label de exibição para o modo single-run (sem --base).

    Tenta ler <stem>_params.json para extrair os anos reais da busca.
    Fallback: anos únicos do resultado.csv via Publication year.
    Fallback final: o próprio stem.
    """
    # 1. params.json do searcher
    params_path = cwd / f"{stem}_params.json"
    if params_path.exists():
        try:
            with open(params_path, encoding="utf-8") as f:
                p = json.load(f)
            anos = p.get("anos", [])
            if anos:
                anos_sorted = sorted(anos)
                if len(anos_sorted) == 1:
                    return str(anos_sorted[0])
                return f"{anos_sorted[0]}–{anos_sorted[-1]}"
        except Exception:
            pass

    # 2. Publication year do resultado.csv em qualquer pasta do stem
    for modo_pasta in descobrir_pastas_cwd(cwd, stem).values():
        csv_path = modo_pasta / "resultado.csv"
        if csv_path.exists():
            try:
                import csv
                anos_set: set[str] = set()
                with open(csv_path, encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        yr = row.get("Publication year", "").strip()
                        if yr.isdigit():
                            anos_set.add(yr)
                if anos_set:
                    anos_sorted = sorted(anos_set)
                    if len(anos_sorted) == 1:
                        return anos_sorted[0]
                    return f"{anos_sorted[0]}–{anos_sorted[-1]}"
            except Exception:
                pass
        break

    # 3. Stem como fallback
    return stem


def carregar_stats(pasta: Path) -> dict:
    path = pasta / "stats.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Utilitários de leitura de stats.json
# ---------------------------------------------------------------------------

def _n(v) -> int:
    """Extrai contagem de um entry de por_fonte_extracao (int ou dict {"n":..., "pct":...})."""
    return v["n"] if isinstance(v, dict) else int(v)


# ---------------------------------------------------------------------------
# Gráfico 1 — Distribuição de status
# ---------------------------------------------------------------------------

CORES_STATUS = {
    "ok_completo":       "#c8c8c8",
    "ok_parcial":        "#f39c12",
    "nada_encontrado":   "#95a5a6",
    "erro_extracao":     "#e74c3c",
    "erro_pid_invalido": "#8e44ad",
}
STATUS_ORDEM = ["ok_completo", "ok_parcial", "nada_encontrado", "erro_extracao", "erro_pid_invalido"]


def grafico_status(dados: dict, output: Path, filename: str, lang: str = "pt"):
    """dados: {label: {modo: stats_dict}}"""
    labels = sorted(dados, key=str)
    modos  = ["api+html", "api", "html"]
    ncols  = len(labels)

    MODO_LABEL = {
        "api+html": s("modo_apimaishtml", lang),
        "api":      s("modo_api", lang),
        "html":     s("modo_html", lang),
    }

    fig, axes = plt.subplots(1, ncols, figsize=(5.5 * ncols, 7), sharey=True)
    if ncols == 1:
        axes = [axes]
    fig.suptitle(s("titulo_status", lang), fontsize=15, fontweight="bold")

    for col, label in enumerate(labels):
        ax = axes[col]
        ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
        ax.set_axisbelow(True)

        Y_MAX   = 122
        Y_BARRA = 100
        GAP     = 8.0

        for i, modo in enumerate(modos):
            if modo not in dados[label]:
                continue
            st = dados[label][modo]
            total  = st["total"]
            bottom = 0.0
            for stat in STATUS_ORDEM:
                val = st.get(stat, 0)
                pct = val / total * 100 if total else 0
                if pct == 0:
                    continue
                ax.bar(i, pct, bottom=bottom, color=CORES_STATUS[stat],
                       edgecolor="white", linewidth=0.5, zorder=2)
                cor_texto = "#333333" if stat == "ok_completo" else "white"
                if pct >= 3:
                    ax.text(i, bottom + pct / 2, f"{pct:.1f}%",
                            ha="center", va="center",
                            fontsize=10, color=cor_texto, fontweight="bold", zorder=3)
                bottom += pct

            pequenos = []
            for stat in STATUS_ORDEM:
                val = st.get(stat, 0)
                pct = val / total * 100 if total else 0
                if 0 < pct < 3:
                    nome_curto = {
                        "ok_parcial":        "parcial",
                        "nada_encontrado":   "nada",
                        "erro_extracao":     "erro",
                        "erro_pid_invalido": "pid_inv",
                    }.get(stat, stat)
                    pequenos.append((nome_curto, pct, CORES_STATUS[stat]))

            n_peq  = len(pequenos)
            y_meio = (Y_BARRA + Y_MAX) / 2
            for k, (nome, pct, cor) in enumerate(pequenos):
                y_rot = y_meio + (k - (n_peq - 1) / 2) * GAP
                ax.text(i, y_rot, f"{nome}: {pct:.1f}%",
                        ha="center", va="center",
                        fontsize=8.5, color=cor, fontweight="bold", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                  ec=cor, lw=0.7, alpha=0.95))

        n_total = dados[label].get(modos[0], {}).get("total", "?")
        ax.set_title(f"{label}  (n={n_total})", fontsize=12, fontweight="bold", pad=10)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels([MODO_LABEL[m] for m in modos], fontsize=10)
        ax.set_ylim(0, Y_MAX)
        ax.set_yticks(range(0, 101, 20))
        ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)], fontsize=10)
        if col == 0:
            ax.set_ylabel(s("eixo_y_pct", lang), fontsize=11)

        # Tabela inset
        linhas_tab = []
        for modo in modos:
            if modo not in dados[label]:
                continue
            st    = dados[label][modo]
            total = st["total"]
            parcial = st.get("ok_parcial", 0)
            erro    = st.get("erro_extracao", 0)
            def fmt(n, tot=total):
                if n == 0:
                    return "0"
                pct = n / tot * 100
                return f"{n} ({pct:.1f}%)"
            linhas_tab.append([MODO_LABEL[modo].replace("\n", " "), fmt(parcial), fmt(erro)])

        if linhas_tab:
            n_rows = len(linhas_tab)
            row_h  = 0.10
            tab_h  = row_h * (n_rows + 1)
            tab = ax.table(
                cellText=linhas_tab,
                colLabels=[s("tab_modo", lang), s("tab_ok_parcial", lang), s("tab_erro", lang)],
                loc="lower center",
                bbox=[0.0, -(tab_h + 0.22), 1.0, tab_h],
            )
            tab.auto_set_font_size(False)
            tab.set_fontsize(9.5)
            for (r, c), cell in tab.get_celld().items():
                cell.set_linewidth(0.5)
                cell.set_text_props(ha="center")
                if r == 0:
                    cell.set_facecolor("#d0d0d0")
                    cell.set_text_props(fontweight="bold", ha="center")
                elif r % 2 == 1:
                    cell.set_facecolor("#f5f5f5")
                else:
                    cell.set_facecolor("#ffffff")

    cats_presentes = {
        stat for label in labels for modo in modos
        if modo in dados[label]
        for stat in STATUS_ORDEM
        if dados[label][modo].get(stat, 0) > 0
    }
    handles = [plt.Rectangle((0,0),1,1, color=CORES_STATUS[st], ec="#888888", lw=0.5)
               for st in STATUS_ORDEM if st in cats_presentes]
    leg_labels = [st for st in STATUS_ORDEM if st in cats_presentes]
    fig.legend(handles, leg_labels, loc="lower center", ncol=len(leg_labels),
               bbox_to_anchor=(0.5, -0.01), fontsize=10, framealpha=0.95,
               edgecolor="#bbbbbb")

    fig.text(0.5, -0.06, s("nota_status", lang),
             ha="center", fontsize=9, color="#666666", style="italic")

    plt.tight_layout()
    fig.subplots_adjust(bottom=0.38)
    dest = output / filename
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Gráfico 2 — Fontes de extração (foco: modo api+html)
# ---------------------------------------------------------------------------

CORES_FONTE = {
    "api":            "#c8c8c8",
    "fallback_ah":    "#e67e22",
    "fallback_html":  "#9b59b6",
    "falha":          "#e74c3c",
}

# Chaves de stats.json["por_fonte_extracao"] → categoria interna
_FONTE_PARA_CAT = {
    "articlemeta_isis":  "api",
    "api+html_fallback": "fallback_ah",
    "html_fallback":     "fallback_html",
    "sem_fonte":         "falha",
}

FONTES_ORDEM_INTERNA = ["api", "fallback_ah", "fallback_html", "falha"]


def _fontes_grafico(stats: dict) -> dict[str, tuple[int, float]]:
    """Retorna {cat_interna: (n, pct)} para o gráfico de fontes."""
    total = stats["total"]
    pfe   = stats.get("por_fonte_extracao", {})
    res: dict[str, tuple[int, float]] = {}
    for chave, val in pfe.items():
        cat = _FONTE_PARA_CAT.get(chave, chave)
        n   = _n(val)
        pct = n / total * 100 if total else 0
        if cat in res:
            n0, p0 = res[cat]
            res[cat] = (n0 + n, p0 + pct)
        else:
            res[cat] = (n, pct)
    return res


def grafico_fontes(dados: dict, output: Path, filename: str, lang: str = "pt"):
    """
    Foco no modo api+html (padrão): barra 100% empilhada por label.
    """
    labels = sorted(dados, key=str)
    modo   = "api+html"
    n_labels = len(labels)

    # Labels localizados das categorias
    CAT_LABEL = {
        "api":           s("fonte_api", lang),
        "fallback_ah":   s("fonte_fallback_apimaishtml", lang),
        "fallback_html": s("fonte_fallback_html", lang),
        "falha":         s("fonte_falha", lang),
    }
    CAT_CURTO = {
        "api":           "API",
        "fallback_ah":   s("fonte_fallback_apimaishtml", lang),
        "fallback_html": s("fonte_fallback_html", lang),
        "falha":         "Falha" if lang == "pt" else "Failure",
    }
    CORES_FONTE_ORDEM = [CORES_FONTE[c] for c in FONTES_ORDEM_INTERNA]

    fig, (ax_bar, ax_tab) = plt.subplots(
        2, 1,
        figsize=(max(8, 2.6 * n_labels), 9),
        gridspec_kw={"height_ratios": [3, 1]},
    )
    fig.suptitle(s("titulo_fontes", lang), fontsize=15, fontweight="bold")

    ax_bar.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax_bar.set_axisbelow(True)

    Y_MAX   = 120
    Y_BARRA = 100

    for i, label in enumerate(labels):
        if modo not in dados[label]:
            continue
        st     = dados[label][modo]
        fontes = _fontes_grafico(st)
        bottom = 0.0
        pequenos = []

        for cat in FONTES_ORDEM_INTERNA:
            if cat not in fontes:
                continue
            n_cat, pct = fontes[cat]
            ax_bar.bar(i, pct, bottom=bottom, color=CORES_FONTE[cat],
                       edgecolor="white", linewidth=0.5, zorder=2)
            cor_txt = "#333333" if cat == "api" else "white"
            if pct >= 3:
                ax_bar.text(i, bottom + pct / 2, f"{pct:.1f}%",
                            ha="center", va="center",
                            fontsize=11, color=cor_txt, fontweight="bold", zorder=3)
            elif pct > 0:
                pequenos.append((CAT_CURTO[cat], pct, CORES_FONTE[cat], bottom + pct / 2))
            bottom += pct

        n_peq  = len(pequenos)
        y_meio = (Y_BARRA + Y_MAX) / 2
        gap    = 5.5
        for k, (nome, pct, cor, _) in enumerate(pequenos):
            y_txt = y_meio + (k - (n_peq - 1) / 2) * gap
            ax_bar.text(i, y_txt, f"{nome}: {pct:.1f}%",
                        ha="center", va="center",
                        fontsize=9, color=cor, fontweight="bold", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=cor, lw=0.7, alpha=0.95))

    ax_bar.set_xticks(range(n_labels))
    ax_bar.set_xticklabels(
        [f"{label}\n(n = {dados[label].get(modo, {}).get('total', '?')})" for label in labels],
        fontsize=11,
    )
    ax_bar.set_ylabel(s("eixo_y_pct", lang), fontsize=12)
    ax_bar.set_ylim(0, Y_MAX)
    ax_bar.set_yticks(range(0, 101, 20))
    ax_bar.set_yticklabels([f"{v}%" for v in range(0, 101, 20)], fontsize=10)

    # Tabela inferior
    ax_tab.axis("off")
    col_labels_tab = [
        s("tab_ano", lang),
        s("tab_n_total", lang),
        CAT_LABEL["api"],
        CAT_LABEL["fallback_ah"],
        CAT_LABEL["fallback_html"],
        CAT_LABEL["falha"],
    ]
    linhas_tab = []
    for label in labels:
        st = dados[label].get(modo)
        if st is None:
            continue
        total  = st["total"]
        fontes = _fontes_grafico(st)

        def fmt(cat):
            if cat not in fontes:
                return "0"
            n_c, pct = fontes[cat]
            return f"{n_c} ({pct:.1f}%)"

        linhas_tab.append([
            str(label),
            str(total),
            fmt("api"),
            fmt("fallback_ah"),
            fmt("fallback_html"),
            fmt("falha"),
        ])

    if linhas_tab:
        tab = ax_tab.table(
            cellText=linhas_tab,
            colLabels=col_labels_tab,
            loc="center",
            cellLoc="center",
        )
        tab.auto_set_font_size(False)
        tab.set_fontsize(10)
        tab.scale(1, 1.6)
        for (r, c), cell in tab.get_celld().items():
            cell.set_linewidth(0.5)
            if r == 0:
                cell.set_facecolor("#d0d0d0")
                cell.set_text_props(fontweight="bold")
            elif r % 2 == 1:
                cell.set_facecolor("#f5f5f5")
            else:
                cell.set_facecolor("#ffffff")
            if c == 0 and r > 0:
                cell.set_text_props(fontweight="bold")

    # Legenda
    cats_presentes: set[str] = set()
    for label in labels:
        st = dados[label].get(modo)
        if st:
            cats_presentes.update(_fontes_grafico(st).keys())
    handles = [plt.Rectangle((0,0),1,1, color=CORES_FONTE[c], ec="#888888", lw=0.5)
               for c in FONTES_ORDEM_INTERNA if c in cats_presentes]
    leg_labels = [CAT_LABEL[c] for c in FONTES_ORDEM_INTERNA if c in cats_presentes]
    fig.legend(handles, leg_labels, loc="lower center", ncol=len(leg_labels),
               bbox_to_anchor=(0.5, -0.01), fontsize=10, framealpha=0.95,
               edgecolor="#bbbbbb")

    fig.text(0.5, -0.05, s("nota_fontes", lang),
             ha="center", fontsize=8.5, color="#666666", style="italic", wrap=True)

    plt.tight_layout()
    dest = output / filename
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Gráfico 3 — Tempo total
# ---------------------------------------------------------------------------

CORES_MODO = {
    "api+html": "#2980b9",
    "api":      "#27ae60",
    "html":     "#e67e22",
}


def grafico_tempo(dados: dict, output: Path, filename: str, lang: str = "pt"):
    """dados: {label: {modo: stats_dict}}"""
    labels = sorted(dados, key=str)
    modos  = ["api+html", "api", "html"]

    MODO_LABEL_SIMPLES = {
        "api+html": "api+html",
        "api":      "api-only" if lang == "en" else "apenas-api",
        "html":     "html-only" if lang == "en" else "apenas-html",
    }

    x     = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(max(8, 2.5 * len(labels)), 6))
    fig.suptitle(s("titulo_tempo", lang), fontsize=13, fontweight="bold")

    for i, modo in enumerate(modos):
        tempos = []
        for label in labels:
            if modo in dados[label]:
                tempos.append(dados[label][modo]["elapsed_seconds"] / 60)
            else:
                tempos.append(0)
        bars = ax.bar(x + i * width, tempos, width,
                      label=MODO_LABEL_SIMPLES[modo], color=CORES_MODO[modo])
        for bar, val in zip(bars, tempos):
            if val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f"{val:.0f}m",
                    ha="center", va="bottom", fontsize=9,
                )

    rotulos = []
    for label in labels:
        total = next(iter(dados[label].values()))["total"]
        rotulos.append(f"{label}\n(n={total})")

    ax.set_xticks(x + width)
    ax.set_xticklabels(rotulos)
    ax.set_ylabel(s("eixo_y_tempo", lang))
    ax.set_xlabel(s("eixo_x_ano", lang))
    ax.set_ylim(0, max(
        dados[label][modo]["elapsed_seconds"] / 60
        for label in labels for modo in modos if modo in dados[label]
    ) * 1.15)
    ax.legend(title=s("legenda_modo", lang))

    plt.tight_layout()
    dest = output / filename
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    from datetime import datetime

    parser = argparse.ArgumentParser(
        description=(
            "Gera gráficos de diagnóstico técnico do processo de extração SciELO.\n"
            "Para artefatos científicos sobre os resultados, use results_report.py."
        ),
        epilog="Exemplo: uv run python process_charts.py --years 2022 2024 2025",
    )
    parser.add_argument(
        "--base", default=None, metavar="DIR",
        help="Pasta raiz com subpastas por ano (ex: runs). "
             "Sem --base: usa as pastas *_s_*/ mais recentes no diretório atual.",
    )
    parser.add_argument(
        "--years", nargs="+", type=int, metavar="YEAR",
        help="Anos a incluir — apenas com --base (ignorado no modo padrão)",
    )
    parser.add_argument(
        "--stem", default=None, metavar="STEM",
        help="Stem do CSV de busca (ex: sc_20260418_123456). "
             "Filtra exatamente as pastas desse run no modo padrão (sem --base). "
             "Ignorado quando --base é usado.",
    )
    parser.add_argument(
        "--output", default=".", metavar="DIR",
        help="Pasta de saída dos PNGs (default: diretório atual)",
    )
    parser.add_argument(
        "--lang", default="pt", choices=["pt", "en", "all"], metavar="LANG",
        help="Idioma dos gráficos: pt (default) | en | all (gera um PNG por idioma)",
    )
    parser.add_argument("--timestamp",  action="store_true",
                        help="Adicionar timestamp nos nomes dos PNGs")
    parser.add_argument("--no-status",  action="store_true", help="Pular gráfico de status")
    parser.add_argument("--no-sources", action="store_true", help="Pular gráfico de fontes")
    parser.add_argument("--no-time",    action="store_true", help="Pular gráfico de tempo")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Mostra o que faria sem gravar nenhum arquivo")
    args = parser.parse_args()

    ts_suffix = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}" if args.timestamp else ""

    langs_a_gerar = IDIOMAS_DISPONIVEIS if args.lang == "all" else [args.lang]

    def png_name(base_name: str, lang: str) -> str:
        lang_suffix = f"_{lang}" if args.lang == "all" else ""
        return f"{base_name}{lang_suffix}{ts_suffix}.png"

    cwd       = Path(".")
    output    = Path(args.output)
    modos     = ["api+html", "api", "html"]
    modo_base = args.base is not None

    stats_por_label: dict = {}

    if modo_base:
        base = Path(args.base)
        if not base.is_dir():
            print(f"Erro: pasta base '{base}' não encontrada.", file=sys.stderr)
            sys.exit(1)
        anos = args.years if args.years else descobrir_anos(base)
        if not anos:
            print(f"Nenhum ano encontrado em '{base}'.", file=sys.stderr)
            sys.exit(1)
        for ano in anos:
            ano_dir = base / str(ano)
            if not ano_dir.is_dir():
                print(f"  Aviso: pasta '{ano_dir}' não encontrada — ano {ano} ignorado.")
                continue
            stats_por_label[ano] = {}
            for modo in modos:
                pasta = descobrir_pasta_modo(ano_dir, modo)
                if pasta is None:
                    print(f"  Aviso: nenhuma pasta '{modo}' encontrada em {ano_dir} — modo ignorado.")
                    continue
                try:
                    stats_por_label[ano][modo] = carregar_stats(pasta)
                except FileNotFoundError as e:
                    print(f"  Aviso: {e} — modo {modo}/{ano} ignorado.")
    else:
        pastas_cwd = descobrir_pastas_cwd(cwd, stem=args.stem)
        if not pastas_cwd:
            msg = (
                f"❌  Nenhuma pasta '{args.stem}_s_*/' com stats.json encontrada.\n"
                f"   Verifique se o stem '{args.stem}' é correto."
                if args.stem else
                "❌  Nenhuma pasta *_s_*/ com stats.json encontrada no diretório atual.\n"
                "   Use --base para apontar para outra pasta ou --stem para especificar o run."
            )
            print(msg, file=sys.stderr)
            sys.exit(1)

        # Resolver label legível: anos do params.json ou Publication year
        stem_efetivo = args.stem
        if stem_efetivo is None:
            csvs = sorted(cwd.glob("sc_*.csv"), reverse=True)
            stem_efetivo = csvs[0].stem if csvs else "run"

        label = _label_do_stem(stem_efetivo, cwd)
        stats_por_label[label] = {}
        for modo, pasta in pastas_cwd.items():
            try:
                stats_por_label[label][modo] = carregar_stats(pasta)
            except FileNotFoundError as e:
                print(f"  Aviso: {e} — modo {modo} ignorado.")

    if not stats_por_label:
        print("Nenhum dado encontrado.", file=sys.stderr)
        sys.exit(1)

    graficos_a_gerar = []
    for lang in langs_a_gerar:
        if not args.no_status:
            graficos_a_gerar.append(png_name(s("arquivo_status", lang), lang))
        if not args.no_sources:
            graficos_a_gerar.append(png_name(s("arquivo_fontes", lang), lang))
        if not args.no_time:
            graficos_a_gerar.append(png_name(s("arquivo_tempo", lang), lang))

    print(f"\nModo             : {'multi-ano (--base)' if modo_base else 'diretório atual (padrão)'}")
    print(f"Labels           : {sorted(stats_por_label, key=str)}")
    print(f"Idioma(s)        : {', '.join(langs_a_gerar)}")
    print(f"Pasta de saída   : {output.resolve()}")
    print(f"Timestamp        : {'sim (' + ts_suffix.lstrip('_') + ')' if args.timestamp else 'não (nome fixo)'}")
    print(f"Gráficos a gerar : {', '.join(graficos_a_gerar) if graficos_a_gerar else '(nenhum)'}")

    if args.dry_run:
        print("\n[dry-run] Nenhum arquivo gravado.")
        return

    output.mkdir(parents=True, exist_ok=True)
    print()

    for lang in langs_a_gerar:
        if len(langs_a_gerar) > 1:
            print(f"  [{lang.upper()}]")
        if not args.no_status:
            grafico_status(stats_por_label, output, png_name(s("arquivo_status", lang), lang), lang)
        if not args.no_sources:
            grafico_fontes(stats_por_label, output, png_name(s("arquivo_fontes", lang), lang), lang)
        if not args.no_time:
            grafico_tempo(stats_por_label, output, png_name(s("arquivo_tempo", lang), lang), lang)

    print("\nPronto.")


if __name__ == "__main__":
    main()
