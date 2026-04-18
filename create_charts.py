"""
create_charts.py — Gera gráficos comparativos das execuções do SciELO Scraper.

Uso:
    uv run python create_charts.py                           # pastas *_s_*/ mais recentes no dir atual
    uv run python create_charts.py --stem sc_20260418_123456 # busca pastas do stem específico (determinístico)
    uv run python create_charts.py --base runs               # varre runs/<ano>/ (multi-ano)
    uv run python create_charts.py --base runs --years 2022 2024
    uv run python create_charts.py --output graficos/        # pasta de saída personalizada
    uv run python create_charts.py --timestamp               # adiciona timestamp nos nomes dos PNGs
    uv run python create_charts.py --no-status               # pula gráfico de status
    uv run python create_charts.py --no-sources              # pula gráfico de fontes
    uv run python create_charts.py --no-time                 # pula gráfico de tempo
    uv run python create_charts.py --dry-run                 # mostra o que faria sem gravar nada
    uv run python create_charts.py -?                        # ajuda (equivalente a -h)

Gráficos gerados (salvo na pasta --output, default: diretório atual):
    chart_status[_<ts>].png   — distribuição de status por modo e ano
    chart_sources[_<ts>].png  — fontes de extração por modo e ano
    chart_time[_<ts>].png     — tempo total por modo e ano

Notas:
    --stem  garante busca determinística no modo padrão (sem --base): usa exatamente
            as pastas <stem>_s_*_<modo>/ em vez do CSV mais recente no diretório.
            Útil quando há múltiplos runs no mesmo diretório (ex: pipeline --per-year).
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
    # Mais recente pelo nome (timestamp embutido)
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
    "ok_completo":       "#c8c8c8",   # cinza claro — dominante, neutro
    "ok_parcial":        "#f39c12",   # laranja
    "nada_encontrado":   "#95a5a6",   # cinza médio
    "erro_extracao":     "#e74c3c",   # vermelho
    "erro_pid_invalido": "#8e44ad",   # roxo
}
STATUS_ORDEM = ["ok_completo", "ok_parcial", "nada_encontrado", "erro_extracao", "erro_pid_invalido"]
STATUS_LEGENDA = {
    "ok_completo":       "ok_completo",
    "ok_parcial":        "ok_parcial",
    "nada_encontrado":   "nada_encontrado",
    "erro_extracao":     "erro_extracao",
    "erro_pid_invalido": "erro_pid_invalido",
}

# Rótulos do eixo X para os modos (compartilhado por todos os gráficos)
MODO_LABEL = {
    "api+html": "api+html\n(padrão)",
    "api":      "apenas-api",
    "html":     "apenas-html",
}


def grafico_status(dados: dict, output: Path, filename: str = "grafico_status.png"):
    """dados: {ano: {modo: stats_dict}}"""
    anos = sorted(dados)
    modos = ["api+html", "api", "html"]
    ncols = len(anos)

    # Altura generosa para acomodar barras + tabela inset abaixo
    fig, axes = plt.subplots(1, ncols, figsize=(5.5 * ncols, 7), sharey=True)
    if ncols == 1:
        axes = [axes]
    fig.suptitle("Distribuição de status por modo de extração",
                 fontsize=15, fontweight="bold")

    for col, ano in enumerate(anos):
        ax = axes[col]
        ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
        ax.set_axisbelow(True)

        # ylim e posição dos rótulos pequenos
        Y_MAX   = 122   # limite superior — espaço para até 2 rótulos sem colisão
        Y_BARRA = 100   # topo das barras empilhadas (sempre ≈100%)
        GAP     = 8.0   # unidades Y de espaçamento entre rótulos empilhados

        for i, modo in enumerate(modos):
            if modo not in dados[ano]:
                continue
            s = dados[ano][modo]
            total = s["total"]
            bottom = 0.0
            for stat in STATUS_ORDEM:
                val = s.get(stat, 0)
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

            # Rótulos das categorias pequenas: empilhados verticalmente,
            # sempre centrados na metade do espaço livre entre Y_BARRA e Y_MAX
            pequenos = []
            for stat in STATUS_ORDEM:
                val = s.get(stat, 0)
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
            y_meio = (Y_BARRA + Y_MAX) / 2   # sempre o centro exato do espaço livre
            for k, (nome, pct, cor) in enumerate(pequenos):
                y_rot = y_meio + (k - (n_peq - 1) / 2) * GAP
                ax.text(i, y_rot, f"{nome}: {pct:.1f}%",
                        ha="center", va="center",
                        fontsize=8.5, color=cor, fontweight="bold", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                  ec=cor, lw=0.7, alpha=0.95))

        n_total = dados[ano].get(modos[0], {}).get("total", "?")
        ax.set_title(f"{ano}  (n={n_total})", fontsize=12, fontweight="bold", pad=10)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels([MODO_LABEL[m] for m in modos], fontsize=10)
        ax.set_ylim(0, Y_MAX)   # Y_MAX definido dentro do loop de modos acima
        ax.set_yticks(range(0, 101, 20))
        ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)], fontsize=10)
        if col == 0:
            ax.set_ylabel("% artigos", fontsize=11)

        # --- Tabela inset abaixo do eixo X (subplot dedicado via gridspec) ---
        linhas_tab = []
        for modo in modos:
            if modo not in dados[ano]:
                continue
            s = dados[ano][modo]
            total = s["total"]
            parcial = s.get("ok_parcial", 0)
            erro    = s.get("erro_extracao", 0)
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
            # bbox em coordenadas de axes: y negativo = abaixo do eixo X
            # gap de 0.20 cobre os xticklabels de duas linhas (modo\n(padrão))
            tab = ax.table(
                cellText=linhas_tab,
                colLabels=["modo", "ok_parcial", "erro_extracao"],
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

    # Legenda centralizada — só categorias que aparecem
    cats_presentes = {
        stat for ano in anos for modo in modos
        if modo in dados[ano]
        for stat in STATUS_ORDEM
        if dados[ano][modo].get(stat, 0) > 0
    }
    handles = [plt.Rectangle((0,0),1,1, color=CORES_STATUS[s], ec="#888888", lw=0.5)
               for s in STATUS_ORDEM if s in cats_presentes]
    labels  = [STATUS_LEGENDA[s] for s in STATUS_ORDEM if s in cats_presentes]
    fig.legend(handles, labels, loc="lower center", ncol=len(labels),
               bbox_to_anchor=(0.5, -0.01), fontsize=10, framealpha=0.95,
               edgecolor="#bbbbbb")

    fig.text(0.5, -0.06,
             "Valores em vermelho = < 1% do total  |  Tabela inset: n exatos por modo",
             ha="center", fontsize=9, color="#666666", style="italic")

    plt.tight_layout()
    fig.subplots_adjust(bottom=0.38)   # xticklabels (2 linhas) + tabela inset + legenda
    dest = output / filename
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Gráfico 2 — Fontes de extração (foco: modo api+html)
# ---------------------------------------------------------------------------

CORES_FONTE = {
    "ArticleMeta API":            "#c8c8c8",   # cinza — dominante, neutro
    "Fallback API+HTML":          "#e67e22",   # laranja — fallback misto
    "Fallback HTML":              "#9b59b6",   # roxo — fallback só-HTML
    "Falha de acesso (erro HTTP)": "#e74c3c",  # vermelho — sem resposta do servidor
}
FONTES_ORDEM = [
    "ArticleMeta API",
    "Fallback API+HTML",
    "Fallback HTML",
    "Falha de acesso (erro HTTP)",
]

# Chaves de stats.json["por_fonte_extracao"] → categoria do gráfico de fontes
_FONTE_PARA_CAT_FONTES = {
    "articlemeta_isis":  "ArticleMeta API",
    "api+html_fallback": "Fallback API+HTML",
    "html_fallback":     "Fallback HTML",
    "sem_fonte":         "Falha de acesso (erro HTTP)",
}


def _fontes_grafico(stats: dict) -> dict[str, tuple[int, float]]:
    """Retorna {categoria: (n, pct)} para o gráfico de fontes."""
    total = stats["total"]
    pfe   = stats.get("por_fonte_extracao", {})
    res: dict[str, tuple[int, float]] = {}
    for chave, val in pfe.items():
        cat = _FONTE_PARA_CAT_FONTES.get(chave, chave)
        n   = _n(val)
        pct = n / total * 100 if total else 0
        if cat in res:
            n0, p0 = res[cat]
            res[cat] = (n0 + n, p0 + pct)
        else:
            res[cat] = (n, pct)
    return res


def grafico_fontes(dados: dict, output: Path, filename: str = "grafico_fontes.png"):
    """
    Foco no modo api+html (padrão): barra 100% empilhada por ano.
    Cinza para ArticleMeta API (dominante); cores fortes para fallback e falha.
    Tabela inset abaixo com n exatos por ano.
    """
    anos  = sorted(dados)
    modo  = "api+html"
    n_anos = len(anos)

    fig, (ax_bar, ax_tab) = plt.subplots(
        2, 1,
        figsize=(max(8, 2.6 * n_anos), 9),
        gridspec_kw={"height_ratios": [3, 1]},
    )
    fig.suptitle("Fontes de extração — modo api+html (padrão)",
                 fontsize=15, fontweight="bold")

    # ── Painel superior: barras empilhadas ───────────────────────────────────
    ax_bar.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#dddddd", zorder=0)
    ax_bar.set_axisbelow(True)

    Y_MAX   = 120   # limite superior do eixo
    Y_BARRA = 100   # topo das barras (sempre ≈100%)
    # Posições fixas para anotações no espaço livre (de baixo para cima)
    Y_ANOT = [104, 111]

    # Nome curto para rótulos
    CAT_CURTO = {
        "ArticleMeta API":             "API",
        "Fallback API+HTML":           "Fallback API+HTML",
        "Fallback HTML":               "Fallback HTML",
        "Falha de acesso (erro HTTP)": "Falha de acesso",
    }

    for i, ano in enumerate(anos):
        if modo not in dados[ano]:
            continue
        s      = dados[ano][modo]
        fontes = _fontes_grafico(s)
        bottom = 0.0
        pequenos = []   # (nome, pct, cor, y_centro_fatia)

        for cat in FONTES_ORDEM:
            if cat not in fontes:
                continue
            n_cat, pct = fontes[cat]
            ax_bar.bar(i, pct, bottom=bottom, color=CORES_FONTE[cat],
                       edgecolor="white", linewidth=0.5, zorder=2)
            cor_txt = "#333333" if cat == "ArticleMeta API" else "white"
            if pct >= 3:
                ax_bar.text(i, bottom + pct / 2, f"{pct:.1f}%",
                            ha="center", va="center",
                            fontsize=11, color=cor_txt, fontweight="bold", zorder=3)
            elif pct > 0:
                pequenos.append((CAT_CURTO[cat], pct, CORES_FONTE[cat], bottom + pct / 2))
            bottom += pct

        # Rótulos no espaço livre — sem setas, empilhados verticalmente
        n_peq   = len(pequenos)
        y_meio  = (Y_BARRA + Y_MAX) / 2   # centro do espaço livre
        gap     = 5.5                      # unidades Y entre rótulos
        for k, (nome, pct, cor, _y_fatia) in enumerate(pequenos):
            y_txt = y_meio + (k - (n_peq - 1) / 2) * gap
            ax_bar.text(i, y_txt, f"{nome}: {pct:.1f}%",
                        ha="center", va="center",
                        fontsize=9, color=cor, fontweight="bold", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=cor, lw=0.7, alpha=0.95))

    ax_bar.set_xticks(range(n_anos))
    ax_bar.set_xticklabels(
        [f"{ano}\n(n = {dados[ano].get(modo, {}).get('total', '?')})" for ano in anos],
        fontsize=11,
    )
    ax_bar.set_ylabel("% artigos", fontsize=12)
    ax_bar.set_ylim(0, Y_MAX)
    ax_bar.set_yticks(range(0, 101, 20))
    ax_bar.set_yticklabels([f"{v}%" for v in range(0, 101, 20)], fontsize=10)

    # ── Painel inferior: tabela com n exatos ────────────────────────────────
    ax_tab.axis("off")

    col_labels = ["Ano", "n total", "ArticleMeta API", "Fallback API+HTML",
                  "Fallback HTML", "Falha de acesso"]
    linhas_tab = []
    for ano in anos:
        s = dados[ano].get(modo)
        if s is None:
            continue
        total  = s["total"]
        fontes = _fontes_grafico(s)

        def fmt(cat):
            if cat not in fontes:
                return "0"
            n_c, pct = fontes[cat]
            return f"{n_c} ({pct:.1f}%)"

        linhas_tab.append([
            str(ano),
            str(total),
            fmt("ArticleMeta API"),
            fmt("Fallback API+HTML"),
            fmt("Fallback HTML"),
            fmt("Falha de acesso (erro HTTP)"),
        ])

    if linhas_tab:
        tab = ax_tab.table(
            cellText=linhas_tab,
            colLabels=col_labels,
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
            # Destaque na coluna do ano
            if c == 0 and r > 0:
                cell.set_text_props(fontweight="bold")

    # ── Legenda e notas ─────────────────────────────────────────────────────
    cats_presentes = set()
    for ano in anos:
        s = dados[ano].get(modo)
        if s:
            cats_presentes.update(_fontes_grafico(s).keys())
    handles = [plt.Rectangle((0,0),1,1, color=CORES_FONTE[c], ec="#888888", lw=0.5)
               for c in FONTES_ORDEM if c in cats_presentes]
    labels  = [c for c in FONTES_ORDEM if c in cats_presentes]
    fig.legend(handles, labels, loc="lower center", ncol=len(labels),
               bbox_to_anchor=(0.5, -0.01), fontsize=10, framealpha=0.95,
               edgecolor="#bbbbbb")

    fig.text(
        0.5, -0.05,
        "Fallback = extração via HTML quando a API não retornou dados completos  "
        "|  Falha de acesso = erro HTTP (ex.: 404)  "
        "|  Valores em vermelho < 1%",
        ha="center", fontsize=9, color="#666666", style="italic",
    )

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


def grafico_tempo(dados: dict, output: Path, filename: str = "grafico_tempo.png"):
    """dados: {ano: {modo: stats_dict}}"""
    anos = sorted(dados)
    modos = ["api+html", "api", "html"]

    x = np.arange(len(anos))
    width = 0.25

    fig, ax = plt.subplots(figsize=(max(8, 2.5 * len(anos)), 6))
    fig.suptitle("Tempo total de extração por ano e modo", fontsize=13, fontweight="bold")

    for i, modo in enumerate(modos):
        tempos = []
        for ano in anos:
            if modo in dados[ano]:
                tempos.append(dados[ano][modo]["elapsed_seconds"] / 60)
            else:
                tempos.append(0)
        bars = ax.bar(x + i * width, tempos, width, label=modo, color=CORES_MODO[modo])
        for bar, val in zip(bars, tempos):
            if val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f"{val:.0f}m",
                    ha="center", va="bottom", fontsize=9,
                )

    rotulos = []
    for ano in anos:
        total = next(iter(dados[ano].values()))["total"]
        rotulos.append(f"{ano}\n(n={total})")

    ax.set_xticks(x + width)
    ax.set_xticklabels(rotulos)
    ax.set_ylabel("Tempo (minutos)")
    ax.set_xlabel("Ano")
    ax.set_ylim(0, max(
        dados[ano][modo]["elapsed_seconds"] / 60
        for ano in anos for modo in modos if modo in dados[ano]
    ) * 1.15)
    ax.legend(title="Modo")

    plt.tight_layout()
    dest = output / filename
    plt.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Suporte a -? como alias para -h/--help
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    from datetime import datetime

    parser = argparse.ArgumentParser(
        description="Gera gráficos comparativos das execuções do SciELO Scraper.",
        epilog="Exemplo: uv run python create_charts.py --years 2022 2024 2025",
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
    parser.add_argument("--timestamp",  action="store_true",
                        help="Adicionar timestamp nos nomes dos PNGs (ex: grafico_status_20260415_173008.png)")
    parser.add_argument("--no-status",  action="store_true", help="Pular gráfico de status")
    parser.add_argument("--no-sources", action="store_true", help="Pular gráfico de fontes")
    parser.add_argument("--no-time",    action="store_true", help="Pular gráfico de tempo")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Mostra o que faria sem gravar nenhum arquivo")
    args = parser.parse_args()

    ts_suffix = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}" if args.timestamp else ""

    def png_name(base_name: str) -> str:
        return f"{base_name}{ts_suffix}.png"

    cwd    = Path(".")
    output = Path(args.output)
    modos  = ["api+html", "api", "html"]
    modo_base = args.base is not None

    # Carregar stats de cada ano/modo
    stats_por_ano: dict = {}

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
            stats_por_ano[ano] = {}
            for modo in modos:
                pasta = descobrir_pasta_modo(ano_dir, modo)
                if pasta is None:
                    print(f"  Aviso: nenhuma pasta '{modo}' encontrada em {ano_dir} — modo ignorado.")
                    continue
                try:
                    stats_por_ano[ano][modo] = carregar_stats(pasta)
                except FileNotFoundError as e:
                    print(f"  Aviso: {e} — modo {modo}/{ano} ignorado.")
    else:
        # Modo padrão: pastas *_s_*/ no diretório atual
        # --stem garante busca determinística; sem --stem usa o CSV mais recente
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
        # Label do eixo: stem explícito ou stem do CSV mais recente
        if args.stem:
            label = args.stem
        else:
            csvs = sorted(cwd.glob("sc_*.csv"), reverse=True)
            label = csvs[0].stem if csvs else "run"
        stats_por_ano[label] = {}
        for modo, pasta in pastas_cwd.items():
            try:
                stats_por_ano[label][modo] = carregar_stats(pasta)
            except FileNotFoundError as e:
                print(f"  Aviso: {e} — modo {modo} ignorado.")

    if not stats_por_ano:
        print("Nenhum dado encontrado.", file=sys.stderr)
        sys.exit(1)

    graficos_a_gerar = []
    if not args.no_status:
        graficos_a_gerar.append(png_name("chart_status"))
    if not args.no_sources:
        graficos_a_gerar.append(png_name("chart_sources"))
    if not args.no_time:
        graficos_a_gerar.append(png_name("chart_time"))

    print(f"\nModo             : {'multi-ano (--base)' if modo_base else 'diretório atual (padrão)'}")
    print(f"Labels           : {sorted(stats_por_ano, key=str)}")
    print(f"Pasta de saída   : {output.resolve()}")
    print(f"Timestamp        : {'sim (' + ts_suffix.lstrip('_') + ')' if args.timestamp else 'não (nome fixo)'}")
    print(f"Gráficos a gerar : {', '.join(graficos_a_gerar) if graficos_a_gerar else '(nenhum)'}")

    if args.dry_run:
        print("\n[dry-run] Nenhum arquivo gravado.")
        return

    output.mkdir(parents=True, exist_ok=True)
    print()

    if not args.no_status:
        grafico_status(stats_por_ano, output, png_name("chart_status"))

    if not args.no_sources:
        grafico_fontes(stats_por_ano, output, png_name("chart_sources"))

    if not args.no_time:
        grafico_tempo(stats_por_ano, output, png_name("chart_time"))

    print("\nPronto.")


if __name__ == "__main__":
    main()
