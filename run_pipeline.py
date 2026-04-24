#!/usr/bin/env python3
"""
run_pipeline.py  v2.1
=====================
Executa o pipeline completo: busca → extração (3 estratégias) →
análise de discrepância → detecção de termos (terms_matcher) →
gráficos comparativos (process_charts) → relatório científico (results_report) →
cópia para runs/<ano>/.

Verifica e instala dependências automaticamente antes de começar.

UTILIZAÇÃO
----------
  python run_pipeline.py --year ANO [opções]

OPÇÕES
------
  --year ANO [ANO ...]      Anos a buscar (ex: 2022 ou 2022 2023 ou 2020-2024)
  --terms T1 T2 ...         Termos de busca e detecção (default: avalia educa)
  --collection COD          Coleção SciELO (default: scl)
  --output-dir DIR          Diretório de destino (default: runs/<ano>/)
  --terms-fields F [F ...]  Campos verificados pelo matcher (default: titulo keywords)
  --terms-match-mode M      Modo de combinação de termos: all|any (default: all)
  --skip-search             Reutilizar o CSV sc_* mais recente em vez de buscar
  --skip-scrape             Reutilizar runs existentes (só gera análise e copia)
  --skip-analysis           Pular análise de discrepância
  --skip-match              Pular etapa do terms_matcher
  --skip-charts             Pular geração de gráficos
  --skip-report             Pular geração do relatório científico (results_report.py)
  --per-year                Rodar pipeline separado por ano (um CSV e destino por ano)
  --dry-run                 Mostra o que faria sem executar nada
  --stats-report [DIR]      Gera relatório consolidado dos stats.json em DIR (default: runs/)
  -h, --help, -?            Mostrar esta mensagem de ajuda e sair

CAMPOS DISPONÍVEIS PARA --terms-fields
---------------------------------------
  titulo    → Titulo_PT
  resumo    → Resumo_PT
  keywords  → Palavras_Chave_PT

NOTAS
-----
  - O scraper é sempre chamado com --no-resume (cada estratégia começa do zero).
  - A análise de discrepância compara as 3 estratégias de scraping.
  - O terms_matcher roda sobre cada estratégia separadamente.
  - Os gráficos são gerados diretamente em runs/<ano>/ (sem copiar do raiz).
  - Após copiar para runs/<ano>/, os originais no diretório raiz são removidos.

EXEMPLOS
--------
  python run_pipeline.py --year 2023
  python run_pipeline.py --year 2022 2023 2024
  python run_pipeline.py --year 2020-2024
  python run_pipeline.py --year 2023 --terms-fields titulo keywords resumo
  python run_pipeline.py --year 2023 --terms-match-mode any
  python run_pipeline.py --year 2022 --collection arg --output-dir runs/arg_2022
  python run_pipeline.py --year 2023 --skip-search    # reutiliza CSV existente
  python run_pipeline.py --year 2023 --dry-run        # simula sem executar
  python run_pipeline.py --year 2022 2023 --per-year  # um CSV por ano
  python run_pipeline.py --stats-report               # consolida runs/ e imprime
  python run_pipeline.py --stats-report runs/         # idem com pasta explícita
"""

__version__ = "2.2"

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Forçar UTF-8 no stdout (Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Constantes ────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent

DEPS = {
    "requests":         "requests",
    "bs4":              "beautifulsoup4",
    "lxml":             "lxml",
    "pandas":           "pandas",
    "tqdm":             "tqdm",
    "brotli":           "brotli",
    "matplotlib":       "matplotlib",
    # results_report.py (Venn/UpSet)
    "matplotlib_venn":  "matplotlib-venn",
    "upsetplot":        "upsetplot",
    # scielo_wordcloud.py
    "wordcloud":        "wordcloud",
    "nltk":             "nltk",
    "PIL":              "pillow",
    # prisma_workflow.py
    "reportlab":        "reportlab",
}

ESTRATEGIAS = [
    {"label": "padrao",     "modo": "padrão",     "slug": "api+html", "flags": []},
    {"label": "apenas-api", "modo": "apenas-api", "slug": "api",      "flags": ["--only-api"]},
    {"label": "apenas-html","modo": "apenas-html","slug": "html",     "flags": ["--only-html"]},
]

STATUS_KEYS = ("ok_completo", "ok_parcial", "nada_encontrado", "erro_extracao", "erro_pid_invalido")

MODO_SUFIXO = {
    "api+html": re.compile(r"_api\+html$"),
    "api":      re.compile(r"_api$"),
    "html":     re.compile(r"_html$"),
}

CAMPOS_DISPONIVEIS = ["titulo", "resumo", "keywords"]

# Etapas do pipeline (para GlobalProgress e pipeline_stats)
# busca(1) + 3×scraping(3) + análise(1) + 3×match(3) + charts(1) + report(1) = 10
ETAPAS_POR_ANO = 10

# ── Utilitários ───────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = {"INFO": "[OK]", "WARN": "[AV]", "ERROR": "[ER]", "STEP": ">>>"}.get(level, "   ")
    try:
        print(f"{ts}  {prefix}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"{ts}  {prefix}  {msg.encode('ascii', errors='replace').decode()}", flush=True)


def run(cmd: list, dry_run: bool) -> int:
    log(f"$ {' '.join(str(c) for c in cmd)}", "STEP")
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=HERE).returncode


def humanize(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def latest(pattern: str) -> Path | None:
    """Retorna o Path mais recente que bate com o glob, ou None."""
    candidates = list(HERE.glob(pattern))
    return max(candidates, key=lambda p: p.name) if candidates else None


def parse_years(raw: list[str]) -> list[int]:
    years: set[int] = set()
    for item in raw:
        m = re.match(r"^(\d{4})-(\d{4})$", item.strip())
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            years.update(range(min(a, b), max(a, b) + 1))
        elif re.match(r"^\d{4}$", item.strip()):
            years.add(int(item.strip()))
        else:
            raise ValueError(f"Ano invalido: '{item}'. Use YYYY ou YYYY-YYYY.")
    return sorted(years)


# ── Progresso global ──────────────────────────────────────────────────────────

class GlobalProgress:
    """
    Rastreia progresso global do pipeline multi-ano.

    Etapas por ano (--per-year):
      busca(1) + 3×scraping(3) + análise(1) + 3×match(3) + charts(1) = 9
    """

    ETAPAS_POR_ANO = ETAPAS_POR_ANO

    def __init__(self, anos: list[int], base: Path | None = None):
        self.anos         = anos
        self.n_anos       = len(anos)
        self.total_etapas = self.n_anos * self.ETAPAS_POR_ANO
        self.etapa_atual  = 0
        self.t_inicio     = time.time()

        # Taxa histórica: artigos/segundo, por modo (para estimativa de ETA)
        self._taxas: dict[str, list[float]] = {"api+html": [], "api": [], "html": []}
        if base and base.is_dir():
            self._carregar_taxas_historicas(base)

    def _carregar_taxas_historicas(self, base: Path):
        """Lê stats.json existentes para calcular taxa média artigos/segundo."""
        for ano_dir in sorted(base.iterdir()):
            if not (ano_dir.is_dir() and ano_dir.name.isdigit()):
                continue
            for modo, padrao in MODO_SUFIXO.items():
                candidatas = [
                    p for p in ano_dir.iterdir()
                    if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
                ]
                if not candidatas:
                    continue
                pasta = sorted(candidatas)[-1]
                sfile = pasta / "stats.json"
                if not sfile.exists():
                    continue
                try:
                    with open(sfile, encoding="utf-8") as f:
                        st = json.load(f)
                    total   = st.get("total", 0)
                    elapsed = st.get("elapsed_seconds", 0)
                    if total > 0 and elapsed > 0:
                        self._taxas[modo].append(total / elapsed)
                except Exception:
                    pass

    def taxa_media(self, modo: str) -> float | None:
        """Artigos/segundo médio para o modo, ou None se não há histórico."""
        vals = self._taxas.get(modo, [])
        return sum(vals) / len(vals) if vals else None

    def avancar(self):
        self.etapa_atual += 1

    def eta_str(self, etapas_restantes: int | None = None) -> str:
        decorrido = time.time() - self.t_inicio
        if self.etapa_atual == 0 or decorrido < 1:
            return "calculando..."
        taxa = self.etapa_atual / decorrido
        restantes = etapas_restantes if etapas_restantes is not None \
                    else (self.total_etapas - self.etapa_atual)
        if restantes <= 0:
            return "quase pronto"
        return humanize(int(restantes / taxa))

    def eta_scraping_str(self, modo: str, n_artigos: int) -> str:
        taxa = self.taxa_media(modo)
        if taxa is None or n_artigos == 0:
            return "sem histórico"
        return humanize(int(n_artigos / taxa))

    def barra(self) -> str:
        pct = self.etapa_atual / self.total_etapas * 100 if self.total_etapas else 0
        decorrido = humanize(int(time.time() - self.t_inicio))
        return (
            f"[Global {self.etapa_atual}/{self.total_etapas} etapas"
            f"  {pct:.0f}%"
            f"  decorrido={decorrido}"
            f"  ETA≈{self.eta_str()}]"
        )

    def barra_ano(self, ano: int, etapa_no_ano: int) -> str:
        idx_ano = self.anos.index(ano) + 1
        return (
            f"[Ano {idx_ano}/{self.n_anos} ({ano})"
            f"  etapa {etapa_no_ano}/{self.ETAPAS_POR_ANO}]"
        )


# ── Stats report ──────────────────────────────────────────────────────────────

def _descobrir_pasta_modo(ano_dir: Path, modo: str) -> Path | None:
    """Pasta de scraping mais recente para modo dentro de ano_dir."""
    padrao = MODO_SUFIXO[modo]
    candidatas = [
        p for p in ano_dir.iterdir()
        if p.is_dir() and padrao.search(p.name) and "_s_" in p.name
    ]
    return sorted(candidatas)[-1] if candidatas else None


def gerar_stats_report(base: Path) -> str:
    """
    Varre base/<ano>/<pasta_modo>/stats.json e gera relatório consolidado.
    Retorna texto Markdown pronto para imprimir.
    """
    modos = ["api+html", "api", "html"]
    anos = sorted(
        [p for p in base.iterdir() if p.is_dir() and p.name.isdigit()],
        key=lambda p: int(p.name),
    )
    if not anos:
        return f"Nenhuma pasta de ano encontrada em '{base}'.\n"

    linhas: list[str] = []
    linhas.append(f"# Relatório de Stats — {base.resolve()}")
    linhas.append(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    glob_total        = 0
    glob_ok_c         = 0
    glob_ok_p         = 0
    glob_nada         = 0
    glob_erro         = 0
    glob_elapsed: dict[str, float] = {"api+html": 0.0, "api": 0.0, "html": 0.0}
    glob_elapsed_total = 0.0

    for ano_dir in anos:
        ano = int(ano_dir.name)
        linhas.append(f"## Ano {ano}\n")
        linhas.append(
            "| Modo | Total | ok_completo | ok_parcial | nada_encontrado"
            " | erro_extracao | Tempo | Média/art |"
        )
        linhas.append("|---|---:|---:|---:|---:|---:|---:|---:|")

        ano_total = None

        for modo in modos:
            pasta = _descobrir_pasta_modo(ano_dir, modo)
            if pasta is None:
                linhas.append(f"| **{modo}** | — | — | — | — | — | — | — |")
                continue
            sfile = pasta / "stats.json"
            if not sfile.exists():
                linhas.append(f"| **{modo}** | sem stats.json | | | | | | |")
                continue
            try:
                with open(sfile, encoding="utf-8") as f:
                    st = json.load(f)
            except Exception as e:
                linhas.append(f"| **{modo}** | erro: {e} | | | | | | |")
                continue

            total   = st.get("total", 0)
            ok_c    = st.get("ok_completo", 0)
            ok_p    = st.get("ok_parcial", 0)
            nada    = st.get("nada_encontrado", 0)
            erro    = st.get("erro_extracao", 0)
            elapsed = st.get("elapsed_seconds", 0.0)
            tempo   = st.get("elapsed_humanizado", humanize(elapsed))
            avg     = st.get("avg_per_article_s")
            avg_str = f"{avg:.1f}s" if avg is not None else (
                f"{elapsed/total:.1f}s" if total else "—"
            )

            def p(n): return f"{n} ({n/total*100:.1f}%)" if total else str(n)

            linhas.append(
                f"| **{modo}** | {total} | {p(ok_c)} | {p(ok_p)}"
                f" | {p(nada)} | {p(erro)} | {tempo} | {avg_str} |"
            )

            glob_elapsed[modo]  += elapsed
            glob_elapsed_total  += elapsed

            if modo == "api+html":
                ano_total  = total
                glob_ok_c += ok_c
                glob_ok_p += ok_p
                glob_nada += nada
                glob_erro += erro

        if ano_total is not None:
            glob_total += ano_total

        linhas.append("")

        pasta_padrao = _descobrir_pasta_modo(ano_dir, "api+html")
        if pasta_padrao:
            sfile = pasta_padrao / "stats.json"
            if sfile.exists():
                try:
                    with open(sfile, encoding="utf-8") as f:
                        st = json.load(f)
                    por_fonte = st.get("por_fonte_extracao")
                    if por_fonte:
                        linhas.append("**Fontes de extração (api+html):**\n")
                        linhas.append("| Fonte | n | % |")
                        linhas.append("|---|---:|---:|")
                        def _n(v): return v["n"] if isinstance(v, dict) else v
                        def _pct(v): return v.get("pct", "—") if isinstance(v, dict) else "—"
                        for fonte, val in sorted(por_fonte.items(), key=lambda x: -_n(x[1])):
                            linhas.append(f"| {fonte} | {_n(val)} | {_pct(val)} |")
                        linhas.append("")
                except Exception:
                    pass

    linhas.append("---\n")
    linhas.append("## Totais globais\n")
    linhas.append("| Métrica | Valor |")
    linhas.append("|---|---:|")
    linhas.append(f"| Anos cobertos | {len(anos)} ({', '.join(d.name for d in anos)}) |")
    linhas.append(f"| Total de artigos | {glob_total} |")
    if glob_total:
        linhas.append(f"| ok_completo (api+html) | {glob_ok_c} ({glob_ok_c/glob_total*100:.1f}%) |")
        linhas.append(f"| ok_parcial (api+html) | {glob_ok_p} ({glob_ok_p/glob_total*100:.1f}%) |")
        linhas.append(f"| nada_encontrado (api+html) | {glob_nada} ({glob_nada/glob_total*100:.1f}%) |")
        linhas.append(f"| erro_extracao (api+html) | {glob_erro} ({glob_erro/glob_total*100:.1f}%) |")
    linhas.append(f"| Tempo total execução (3 modos × {len(anos)} anos) | {humanize(int(glob_elapsed_total))} |")
    linhas.append(f"| Tempo scraping api+html | {humanize(int(glob_elapsed['api+html']))} |")
    linhas.append(f"| Tempo scraping api | {humanize(int(glob_elapsed['api']))} |")
    linhas.append(f"| Tempo scraping html | {humanize(int(glob_elapsed['html']))} |")
    if glob_total and glob_elapsed["api+html"]:
        linhas.append(f"| Média/artigo (api+html) | {glob_elapsed['api+html']/glob_total:.1f}s |")
    linhas.append("")

    return "\n".join(linhas)


# ── Dependências ──────────────────────────────────────────────────────────────

def ensure_deps(dry_run: bool):
    """Verifica e instala dependências ausentes via uv pip install."""
    missing = []
    for mod, pkg in DEPS.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if not missing:
        log("Dependencias verificadas — todas presentes.")
        return

    log(f"Dependencias ausentes: {', '.join(missing)}", "WARN")
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + missing

    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "pip", "install", "--quiet"] + missing

    log(f"Instalando: {' '.join(missing)}")
    rc = run(cmd, dry_run)
    if rc != 0:
        log("Falha ao instalar dependencias — abortando.", "ERROR")
        sys.exit(rc)
    log("Dependencias instaladas com sucesso.")


# ── Análise de discrepância ───────────────────────────────────────────────────

def gerar_analise(run_dirs: dict, years: list[int], terms: list[str]) -> str:
    """Gera o texto Markdown da análise de discrepância."""

    all_stats: dict[str, dict] = {}
    all_dfs:   dict[str, object] = {}
    total = 0

    try:
        import pandas as pd
        has_pd = True
    except ImportError:
        has_pd = False

    for est in ESTRATEGIAS:
        modo  = est["modo"]
        path  = run_dirs.get(est["label"])
        if not path:
            continue
        sfile = path / "stats.json"
        if sfile.exists():
            with open(sfile, encoding="utf-8") as f:
                st = json.load(f)
            all_stats[modo] = st
            if not total:
                total = st.get("total", 0)
        if has_pd:
            rfile = path / "resultado.csv"
            if rfile.exists():
                all_dfs[modo] = pd.read_csv(rfile).set_index("PID_limpo")

    if not all_stats:
        return "Nenhum stats.json encontrado — análise não gerada.\n"

    def pct(n: int) -> str:
        return f"{n/total*100:.1f}%" if total else "0%"

    linhas_tabela = []
    for est in ESTRATEGIAS:
        modo = est["modo"]
        st   = all_stats.get(modo)
        if not st:
            continue
        ok_c = st.get("ok_completo", 0)
        ok_p = st.get("ok_parcial",  0)
        erro = st.get("erro_extracao", 0)
        suc  = st.get("sucesso_total", ok_c + ok_p)
        tempo = st.get("elapsed_humanizado", "?")
        linhas_tabela.append(
            f"| **{modo}** | {ok_c} ({pct(ok_c)}) | {ok_p} ({pct(ok_p)}) "
            f"| {erro} ({pct(erro)}) | {suc} ({pct(suc)}) | {tempo} |"
        )

    tabela = (
        "| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(linhas_tabela)
    )

    secoes: list[str] = []
    anos_str = "-".join(str(y) for y in [years[0], years[-1]]) if len(years) > 1 else str(years[0])

    padrao_df = all_dfs.get("padrão")
    api_df    = all_dfs.get("apenas-api")
    html_df   = all_dfs.get("apenas-html")

    if has_pd and padrao_df is not None and api_df is not None and html_df is not None:

        def noncomplete(df): return set(df[df["status"] != "ok_completo"].index)
        def complete(df):    return set(df[df["status"] == "ok_completo"].index)
        def is_aop(pid):     return str(pid)[14:17] == "005"

        fixed_by_html  = complete(padrao_df) - complete(api_df)
        html_only_fail = noncomplete(html_df) - noncomplete(api_df)
        always_partial = noncomplete(padrao_df) & noncomplete(api_df) & noncomplete(html_df)

        if fixed_by_html:
            rows = [
                f"| `{pid}`{'  (AoP)' if is_aop(pid) else ''} | {api_df.loc[pid]['status']} | "
                f"{padrao_df.loc[pid]['status']} | {padrao_df.loc[pid]['fonte_extracao']} |"
                for pid in sorted(fixed_by_html)
            ]
            secoes.append(
                f"## 2. Artigos corrigidos pelo fallback HTML ({len(fixed_by_html)})\n\n"
                "| PID | Status (api) | Status (padrao) | Fonte no padrao |\n"
                "|---|---|---|---|\n" + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 2. Artigos corrigidos pelo fallback HTML\n\n"
                "Nenhum artigo foi corrigido pelo fallback HTML nesta execução."
            )

        if html_only_fail:
            rows = [
                f"| `{pid}` | {api_df.loc[pid]['status']} | {html_df.loc[pid]['status']} | "
                f"{html_df.loc[pid].get('fonte_extracao', '—')} |"
                for pid in sorted(html_only_fail)
            ]
            secoes.append(
                f"## 3. Artigos que o HTML-only falhou mas a API recuperou ({len(html_only_fail)})\n\n"
                "| PID | Status (api) | Status (html) | Fonte HTML |\n"
                "|---|---|---|\n" + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 3. Artigos que o HTML-only falhou mas a API recuperou\n\n"
                "Nenhum caso nesta execução."
            )

        if always_partial:
            rows = [
                f"| `{pid}` | {str(padrao_df.loc[pid].get('Titulo_PT', ''))[:60]} |"
                for pid in sorted(always_partial)
            ]
            secoes.append(
                f"## 4. Artigos persistentemente incompletos ({len(always_partial)})\n\n"
                "Estes artigos não atingiram `ok_completo` em nenhuma estratégia — "
                "a limitação é da fonte, não do scraper.\n\n"
                "| PID | Título (PT) |\n"
                "|---|---|\n" + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 4. Artigos persistentemente incompletos\n\n"
                "Nenhum artigo ficou sem `ok_completo` em todas as estratégias."
            )

    linhas_tempo = [
        f"| {est['modo']} | {all_stats[est['modo']].get('elapsed_humanizado','?')} "
        f"| {all_stats[est['modo']].get('avg_per_article_s','?')} s |"
        for est in ESTRATEGIAS if est["modo"] in all_stats
    ]
    secoes.append(
        "## 5. Desempenho temporal\n\n"
        "| Modo | Tempo total | Média/artigo |\n"
        "|---|---|---|\n" + "\n".join(linhas_tempo)
    )

    termos_str = ", ".join(f"{t}$" for t in terms)
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return (
        f"# Análise de Discrepância — {anos_str}\n\n"
        f"**Corpus:** {total} artigos SciELO Brasil ({anos_str}), termos: {termos_str}\n"
        f"**Gerado em:** {ts_now}\n\n"
        "---\n\n"
        "## 1. Resumo executivo\n\n"
        f"{tabela}\n\n"
        "---\n\n"
        + "\n\n---\n\n".join(secoes)
        + "\n"
    )


# ── Pipeline de um único ano/conjunto ────────────────────────────────────────

def _log_progresso(gp: "GlobalProgress | None", ano: int, etapa_no_ano: int):
    if gp is None or gp.n_anos <= 1:
        return
    print(f"  {gp.barra_ano(ano, etapa_no_ano)}  {gp.barra()}", flush=True)


def _contar_artigos_csv(csv_path: Path) -> int:
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


def _pasta_preferida(run_dirs: dict) -> Path | None:
    """
    Retorna a pasta de scraping disponível de maior prioridade.
    Ordem: api+html > html > api.
    """
    for slug in ("api+html", "html", "api"):
        for est in ESTRATEGIAS:
            if est["slug"] == slug:
                p = run_dirs.get(est["label"])
                if p and p.exists():
                    return p
    return None


def run_pipeline(years: list[int], raw_years: list[str], terms: list[str],
                 collection: str, dest: Path, python: str,
                 skip_search: bool, skip_scrape: bool, skip_analysis: bool,
                 skip_match: bool, skip_charts: bool, skip_report: bool, dry: bool,
                 terms_fields: list[str], terms_match_mode: str,
                 gp: "GlobalProgress | None" = None):
    """Executa search → 3×scrape → análise → 3×match → charts → report → cópia para dest."""

    ano_ref   = years[0]
    anos_label = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
    etapa_local = 0
    etapa_total = ETAPAS_POR_ANO

    def _header(n: int, label: str, extra: str = ""):
        nonlocal etapa_local
        etapa_local = n
        _log_progresso(gp, ano_ref, n)
        sufixo = f"  ({extra})" if extra else ""
        log(f"── ETAPA {n}/{etapa_total}: {label}{sufixo} {'─'*(42-len(label)-len(sufixo))}", "STEP")

    # ── 1. Busca ──────────────────────────────────────────────────────────────
    csv_path = None

    if skip_search or skip_scrape:
        csv_path = latest("sc_*.csv")
        if csv_path:
            log(f"Reutilizando CSV existente: {csv_path.name}")
        else:
            log("Nenhum CSV sc_* encontrado — executando busca mesmo assim", "WARN")

    if csv_path is None:
        _header(1, "Busca")
        log(f"  Termos     : {', '.join(terms)}")
        log(f"  Colecao    : {collection}")
        log(f"  Anos       : {', '.join(raw_years)}")
        rc = run(
            [python, "scielo_search.py",
             "--terms", *terms,
             "--collection", collection,
             "--years", *raw_years],
            dry,
        )
        if gp:
            gp.avancar()
        if rc != 0:
            log("Busca falhou — abortando", "ERROR")
            sys.exit(rc)

        if not dry:
            csv_path = latest("sc_*.csv")
            if not csv_path:
                log("CSV de saída não encontrado após busca", "ERROR")
                sys.exit(1)
            log(f"  Busca concluida: {csv_path.name}")
        else:
            csv_path = HERE / f"sc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        if gp:
            gp.avancar()
    print()

    n_artigos = _contar_artigos_csv(csv_path) if not dry else 0
    if n_artigos:
        log(f"  Artigos no CSV: {n_artigos}")

    # ── 2-4. Scraping (3 estratégias) ─────────────────────────────────────────
    run_dirs: dict[str, Path] = {}
    stem = csv_path.stem

    for i, est in enumerate(ESTRATEGIAS, start=2):
        eta_scr = ""
        if gp and n_artigos:
            eta_scr = f"ETA≈{gp.eta_scraping_str(est['slug'], n_artigos)}"

        _header(i, f"Scraping {est['modo']}", eta_scr)
        log(f"  Estrategia : {est['modo']} ({est['slug']})")
        log(f"  CSV        : {csv_path.name}")

        if skip_scrape:
            found = latest(f"{stem}_s_*_{est['slug']}")
            if found:
                run_dirs[est["label"]] = found
                log(f"  Reutilizando: {found.name}")
                if gp:
                    gp.avancar()
                print()
                continue
            log(f"  Pasta nao encontrada para {est['slug']} — executando scraping", "WARN")

        rc = run([python, "scielo_scraper.py", str(csv_path), "--no-resume"] + est["flags"], dry)
        if gp:
            gp.avancar()
        if rc != 0:
            log(f"  Scraping {est['modo']} falhou (codigo {rc}) — continuando", "WARN")

        if not dry:
            found = latest(f"{stem}_s_*_{est['slug']}")
            if found:
                run_dirs[est["label"]] = found
                # Resumo de resultados
                sfile = found / "stats.json"
                if sfile.exists():
                    try:
                        with open(sfile, encoding="utf-8") as f:
                            st = json.load(f)
                        total_art = st.get("total", 0)
                        ok_c = st.get("ok_completo", 0)
                        ok_p = st.get("ok_parcial", 0)
                        tempo = st.get("elapsed_humanizado", "?")
                        log(f"  Scraping concluido: {found.name}")
                        log(f"    Total={total_art}  ok_completo={ok_c}  ok_parcial={ok_p}  tempo={tempo}")
                    except Exception:
                        log(f"  Pasta gerada: {found.name}")
            else:
                log(f"  Pasta de resultado nao encontrada para {est['slug']}", "WARN")
        else:
            run_dirs[est["label"]] = HERE / f"{stem}_s_DRY_{est['slug']}"
        print()

    # ── 5. Análise de discrepância ────────────────────────────────────────────
    analise_path = HERE / f"ANALISE_DISCREPANCIA_{anos_label}.md"

    if not skip_analysis:
        _header(5, "Analise de discrepancia")
        log(f"  Comparando {len(run_dirs)} estrategia(s): {', '.join(run_dirs.keys())}")

        analise_md = (
            gerar_analise(run_dirs, years, terms)
            if not dry
            else f"# Análise de Discrepância — {anos_label}\n\n(dry-run)\n"
        )
        if gp:
            gp.avancar()

        if not dry:
            analise_path.write_text(analise_md, encoding="utf-8")
            log(f"  Analise gerada: {analise_path.name}")

        print()
        print("─" * 62)
        print(analise_md)
        print("─" * 62)
        print()
    else:
        log("  Etapa 5/9: Analise de discrepancia — PULADA (--skip-analysis)", "WARN")
        if gp:
            gp.avancar()
        print()

    # ── 6-8. Terms matcher (uma invocação por estratégia) ─────────────────────
    terms_results: dict[str, Path] = {}   # slug → pasta com os arquivos terms_*

    if not skip_match:
        campos_str = ", ".join(terms_fields)
        termos_str = ", ".join(f"{t}$" for t in terms)

        for j, est in enumerate(ESTRATEGIAS, start=6):
            pasta = run_dirs.get(est["label"])

            _header(j, f"Terms matcher ({est['slug']})")
            log(f"  Termos     : {termos_str}")
            log(f"  Campos     : {campos_str}")
            log(f"  Modo       : {terms_match_mode} (todos os termos presentes em pelo menos um campo)"
                if terms_match_mode == "all"
                else f"  Modo       : {terms_match_mode} (qualquer termo presente em qualquer campo)")
            log(f"  Estrategia : {est['modo']} ({est['slug']})")

            if pasta is None or (not dry and not pasta.exists()):
                log(f"  Pasta nao disponivel para {est['slug']} — pulando", "WARN")
                if gp:
                    gp.avancar()
                print()
                continue

            resultado_csv = pasta / "resultado.csv"
            if not dry and not resultado_csv.exists():
                log(f"  resultado.csv nao encontrado em {pasta.name} — pulando", "WARN")
                if gp:
                    gp.avancar()
                print()
                continue

            log(f"  Entrada    : {pasta.name}/resultado.csv")
            log(f"  Saida      : {pasta.name}/terms_<ts>.[csv|log|_stats.json]")

            rc = run(
                [python, "terms_matcher.py",
                 "--terms",           *terms,
                 "--required-fields", *terms_fields,
                 "--match-mode",      terms_match_mode,
                 "--mode",            est["slug"],
                 "--output-dir",      str(pasta)],
                dry,
            )
            if gp:
                gp.avancar()
            if rc != 0:
                log(f"  Terms matcher ({est['slug']}) falhou (codigo {rc}) — continuando", "WARN")
            elif not dry:
                # Resumo: ler o terms_*_stats.json mais recente na pasta
                stats_files = sorted(pasta.glob("terms_*_stats.json"), reverse=True)
                if stats_files:
                    try:
                        with open(stats_files[0], encoding="utf-8") as f:
                            ts = json.load(f)
                        detectados = ts.get("detectados", ts.get("n_criterio_ok", "?"))
                        total_art  = ts.get("total_linhas", ts.get("total", "?"))
                        log(f"  Matcher concluido: {detectados}/{total_art} artigos detectados")
                    except Exception:
                        log(f"  Matcher concluido.")
                terms_results[est["slug"]] = pasta
            print()
    else:
        log(f"  Etapas 6-8/9: Terms matcher — PULADAS (--skip-match)", "WARN")
        for _ in range(3):
            if gp:
                gp.avancar()
        print()

    # ── 9. Gráficos ───────────────────────────────────────────────────────────
    if not skip_charts:
        _header(9, "Graficos comparativos")
        log(f"  Stem       : {stem}")
        log(f"  Saida      : {dest}/")
        log(f"  Graficos   : chart_status.png, chart_sources.png, chart_time.png")

        # Garante que dest existe antes de gerar os gráficos
        if not dry:
            dest.mkdir(parents=True, exist_ok=True)

        rc = run(
            [python, "process_charts.py",
             "--stem",   stem,
             "--output", str(dest)],
            dry,
        )
        if gp:
            gp.avancar()
        if rc != 0:
            log("  Geracao de graficos falhou — continuando", "WARN")
        elif not dry:
            charts = list(dest.glob("chart_*.png"))
            if charts:
                log(f"  {len(charts)} grafico(s) gerado(s) em {dest.name}/")
    else:
        log(f"  Etapa 9/{ETAPAS_POR_ANO}: Graficos — PULADA (--skip-charts)", "WARN")
        if gp:
            gp.avancar()
    print()

    # ── 10. Relatório científico ──────────────────────────────────────────────
    # As pastas de scraping ainda estão no raiz (cópia para dest ocorre depois).
    # Passamos --stem para que results_report encontre o terms_*.csv correto.
    if not skip_report:
        est_principal = ESTRATEGIAS[0]  # api+html
        slug_principal = est_principal["slug"]
        pasta_principal = run_dirs.get(est_principal["label"])
        report_output = dest / f"results_{stem}_{slug_principal}"

        _header(10, "Relatorio cientifico (results_report)")
        log(f"  Modo       : {slug_principal} (estrategia principal)")
        log(f"  Pasta CSV  : {pasta_principal}")
        log(f"  Saida      : {report_output}/")

        if not dry:
            dest.mkdir(parents=True, exist_ok=True)
            report_output.mkdir(parents=True, exist_ok=True)

        if pasta_principal and pasta_principal.exists():
            terms_csvs = sorted(pasta_principal.glob("terms_*.csv"), reverse=True)
            terms_csv = terms_csvs[0] if terms_csvs else None
        else:
            terms_csv = None

        if terms_csv is None and not dry:
            log("  Nenhum terms_*.csv encontrado — etapa pulada", "WARN")
            if gp:
                gp.avancar()
        else:
            # Usa --scrape-dir para apontar direto para a pasta de scraping
            # (as pastas ainda estão no raiz neste momento, antes da cópia)
            scrape_dir_arg = str(pasta_principal) if pasta_principal else "."
            rc = run(
                [python, "results_report.py",
                 "--scrape-dir", scrape_dir_arg,
                 "--output-dir", str(report_output)],
                dry,
            )
            if gp:
                gp.avancar()
            if rc != 0:
                log("  Relatorio cientifico falhou — continuando", "WARN")
            elif not dry:
                if report_output.exists():
                    n = len(list(report_output.iterdir()))
                    log(f"  {n} artefato(s) gerado(s) em {report_output.name}/")
    else:
        log(f"  Etapa 10/{ETAPAS_POR_ANO}: Relatorio cientifico — PULADA (--skip-report)", "WARN")
        if gp:
            gp.avancar()
    print()

    # ── Cópia para destino + limpeza ──────────────────────────────────────────
    log(f"── Copiando para {dest} ──────────────────────────────────────", "STEP")

    if not dry:
        dest.mkdir(parents=True, exist_ok=True)

        # CSV de busca e params
        params = csv_path.with_name(csv_path.stem + "_params.json")
        for f in [csv_path, params]:
            if f.exists():
                shutil.copy2(f, dest / f.name)
                log(f"  Copiado: {f.name}")

        # Pastas de scraping (com todo o conteúdo, incluindo terms_*)
        for est in ESTRATEGIAS:
            path = run_dirs.get(est["label"])
            if path and path.exists():
                target = dest / path.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(path, target)
                log(f"  Copiado: {path.name}/")

        # Análise de discrepância
        if not skip_analysis and analise_path.exists():
            shutil.copy2(analise_path, dest / analise_path.name)
            log(f"  Copiado: {analise_path.name}")

        # Gravar pipeline_stats.json em dest
        _gravar_pipeline_stats(
            dest=dest,
            anos_label=anos_label,
            years=years,
            terms=terms,
            collection=collection,
            terms_fields=terms_fields,
            terms_match_mode=terms_match_mode,
            skip_search=skip_search,
            skip_scrape=skip_scrape,
            skip_analysis=skip_analysis,
            skip_match=skip_match,
            skip_charts=skip_charts,
            skip_report=skip_report,
            run_dirs=run_dirs,
            origem=_origem(args),
        )

        # Arquivar originais do diretório raiz (move → nunca apaga)
        log("Arquivando originais do diretorio raiz...")
        _arquivar_originais(
            dest=dest,
            stem=stem,
            csv_path=csv_path,
            params=params,
            run_dirs=run_dirs,
            analise_path=analise_path if not skip_analysis else None,
        )
    else:
        log(f"  (dry-run) copiaria CSV, params.json, 3 pastas e analise para {dest}")
        log(f"  (dry-run) gravaria pipeline_stats.json em {dest}")
        log(f"  (dry-run) arquivaria (moveria) originais do diretorio raiz para {dest}")


def _arquivar_originais(dest: Path, stem: str, csv_path: Path, params: Path,
                        run_dirs: dict, analise_path: Path | None):
    """
    Move para dest qualquer arquivo/pasta do run atual que ainda esteja no raiz.
    Nunca apaga — todo produto de cada etapa é importante.
    Loga aviso para cada item movido (indica que foi gerado fora do lugar esperado).
    """
    movidos = 0

    def _mover(src: Path, label: str):
        nonlocal movidos
        if not src.exists():
            return
        target = dest / src.name
        if target.exists():
            # Já copiado anteriormente — só remove o original
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
            log(f"  Removido (ja estava em dest): {label}")
        else:
            # Não estava em dest — move e avisa
            if src.is_dir():
                shutil.move(str(src), str(target))
            else:
                shutil.move(str(src), str(target))
            log(f"  Arquivado (movido para dest): {label}", "WARN")
        movidos += 1

    # CSV de busca e params
    _mover(csv_path, csv_path.name)
    _mover(params,   params.name)

    # Pastas de scraping
    for est in ESTRATEGIAS:
        path = run_dirs.get(est["label"])
        if path:
            _mover(path, path.name + "/")

    # Análise de discrepância
    if analise_path:
        _mover(analise_path, analise_path.name)

    # Varredura de segurança: qualquer outro arquivo/pasta do stem que sobrou
    for item in HERE.iterdir():
        if item == dest:
            continue
        if item.name.startswith(stem) and item != dest:
            _mover(item, item.name + ("/" if item.is_dir() else ""))

    if movidos == 0:
        log("  Diretorio raiz limpo — nenhum arquivo residual encontrado.")
    else:
        log(f"  {movidos} item(ns) arquivado(s) em {dest.name}/")


def _origem(args) -> dict:
    """Reconstrói o comando CLI que gerou este JSON para rastreabilidade."""
    import sys
    cmd = ["uv", "run", "python", "run_pipeline.py"]
    if args.year:
        cmd += ["--year"] + [str(y) for y in args.year]
    if args.terms != ["avalia", "educa"]:
        cmd += ["--terms"] + args.terms
    if args.collection != "scl":
        cmd += ["--collection", args.collection]
    if getattr(args, "output_dir", None):
        cmd += ["--output-dir", str(args.output_dir)]
    if args.terms_fields != ["titulo", "keywords"]:
        cmd += ["--terms-fields"] + args.terms_fields
    if args.terms_match_mode != "all":
        cmd += ["--terms-match-mode", args.terms_match_mode]
    if getattr(args, "per_year", False):
        cmd.append("--per-year")
    for flag in ("skip_search", "skip_scrape", "skip_analysis",
                 "skip_match", "skip_charts", "skip_report"):
        if getattr(args, flag, False):
            cmd.append(f"--{flag.replace('_', '-')}")
    return {
        "comando": " ".join(cmd),
        "argv":    sys.argv[1:],
        "cwd":     str(Path(".").resolve()),
    }


def _gravar_pipeline_stats(dest: Path, anos_label: str, years: list[int],
                            terms: list[str], collection: str,
                            terms_fields: list[str], terms_match_mode: str,
                            skip_search: bool, skip_scrape: bool,
                            skip_analysis: bool, skip_match: bool,
                            skip_charts: bool, skip_report: bool,
                            run_dirs: dict, origem: dict | None = None):
    """Grava pipeline_stats.json em dest com resumo completo da execução."""
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    etapas_executadas = []
    etapas_puladas    = []

    if not skip_search:
        etapas_executadas.append("busca")
    else:
        etapas_puladas.append("busca")

    for est in ESTRATEGIAS:
        slug = est["slug"]
        if not skip_scrape or run_dirs.get(est["label"]):
            etapas_executadas.append(f"scraping_{slug}")
        else:
            etapas_puladas.append(f"scraping_{slug}")

    if not skip_analysis:
        etapas_executadas.append("analise_discrepancia")
    else:
        etapas_puladas.append("analise_discrepancia")

    if not skip_match:
        for est in ESTRATEGIAS:
            etapas_executadas.append(f"match_{est['slug']}")
    else:
        for est in ESTRATEGIAS:
            etapas_puladas.append(f"match_{est['slug']}")

    if not skip_charts:
        etapas_executadas.append("charts")
    else:
        etapas_puladas.append("charts")

    if not skip_report:
        etapas_executadas.append("results_report")
    else:
        etapas_puladas.append("results_report")

    # Resumo de stats por estratégia
    estrategias_stats = {}
    for est in ESTRATEGIAS:
        path = run_dirs.get(est["label"])
        if path and path.exists():
            sfile = path / "stats.json"
            entry: dict = {"pasta": path.name}
            if sfile.exists():
                try:
                    with open(sfile, encoding="utf-8") as f:
                        st = json.load(f)
                    entry["total"]               = st.get("total", 0)
                    entry["ok_completo"]         = st.get("ok_completo", 0)
                    entry["ok_parcial"]          = st.get("ok_parcial", 0)
                    entry["elapsed_humanizado"]  = st.get("elapsed_humanizado", "?")
                except Exception:
                    pass
            estrategias_stats[est["slug"]] = entry

    stats = {
        "pipeline_version":   __version__,
        "gerado_em":          ts_now,
        "anos":               anos_label,
        "years":              years,
        "collection":         collection,
        "terms":              terms,
        "terms_fields":       terms_fields,
        "terms_match_mode":   terms_match_mode,
        "etapas_executadas":  etapas_executadas,
        "etapas_puladas":     etapas_puladas,
        "estrategias":        estrategias_stats,
        "origem":             origem or {},
    }

    out = dest / "pipeline_stats.json"
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        log(f"  pipeline_stats.json gravado em {dest.name}/")
    except Exception as e:
        log(f"  Falha ao gravar pipeline_stats.json: {e}", "WARN")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=f"Pipeline SciELO v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        add_help=False,
    )
    ap.add_argument("-h", "--help", "-?", action="help",
        help="Mostrar esta mensagem e sair")
    ap.add_argument("--year", nargs="*", metavar="ANO",
        help="Anos a buscar. Ex: 2022  ou  2022 2023  ou  2020-2024")
    ap.add_argument("--terms", nargs="+", default=["avalia", "educa"], metavar="TERMO",
        help="Termos de busca e detecção (default: avalia educa)")
    ap.add_argument("--collection", default="scl", metavar="COD",
        help="Colecao SciELO (default: scl)")
    ap.add_argument("--output-dir", default=None, metavar="DIR",
        help="Diretorio de destino (default: runs/<ano>/)")
    ap.add_argument("--terms-fields", nargs="+",
        default=["titulo", "keywords"],
        choices=CAMPOS_DISPONIVEIS, metavar="CAMPO",
        help="Campos para detecção de termos: titulo resumo keywords (default: titulo keywords)")
    ap.add_argument("--terms-match-mode", default="all", choices=["all", "any"],
        metavar="MODO",
        help="Modo de combinação: all=todos os termos presentes, any=qualquer termo (default: all)")
    ap.add_argument("--per-year", action="store_true",
        help="Rodar pipeline separado por ano (um CSV e destino por ano)")
    ap.add_argument("--skip-search", action="store_true",
        help="Reutilizar o CSV sc_* mais recente em vez de buscar")
    ap.add_argument("--skip-scrape", action="store_true",
        help="Reutilizar runs existentes (só gera análise e copia)")
    ap.add_argument("--skip-analysis", action="store_true",
        help="Pular análise de discrepância entre estratégias")
    ap.add_argument("--skip-match", action="store_true",
        help="Pular etapa de detecção de termos (terms_matcher)")
    ap.add_argument("--skip-charts", action="store_true",
        help="Pular geração de gráficos comparativos")
    ap.add_argument("--skip-report", action="store_true",
        help="Pular geração do relatório científico (results_report.py)")
    ap.add_argument("--dry-run", action="store_true",
        help="Mostra o que faria sem executar nada")
    ap.add_argument(
        "--stats-report", nargs="?", const="runs", metavar="DIR",
        help="Gera relatório consolidado dos stats.json em DIR (default: runs/)",
    )
    ap.add_argument("--version", action="version", version=f"v{__version__}")
    args = ap.parse_args()

    # ── Modo --stats-report (não executa pipeline) ────────────────────────────
    if args.stats_report is not None:
        base = Path(args.stats_report)
        if not base.is_dir():
            print(f"Erro: pasta '{base}' não encontrada.", file=sys.stderr)
            sys.exit(1)
        relatorio = gerar_stats_report(base)
        print(relatorio)
        sys.exit(0)

    # ── Modo pipeline — --year é obrigatório ─────────────────────────────────
    if not args.year:
        ap.error("--year é obrigatório (a menos que use --stats-report)")

    try:
        years = parse_years(args.year)
    except ValueError as e:
        ap.error(str(e))

    python = sys.executable
    dry    = args.dry_run

    anos_label = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])

    print()
    log(f"Pipeline SciELO v{__version__} — {anos_label}", "STEP")
    log(f"Termos          : {', '.join(args.terms)}")
    log(f"Colecao         : {args.collection}")
    log(f"Campos (matcher): {', '.join(args.terms_fields)}")
    log(f"Modo matcher    : {args.terms_match_mode}"
        + (" (todos os termos devem estar presentes)" if args.terms_match_mode == "all"
           else " (qualquer termo detectado é suficiente)"))
    log(f"Por ano         : {'sim' if args.per_year else 'nao'}")
    etapas_skip = [e for e, v in [
        ("busca",    args.skip_search),
        ("scrape",   args.skip_scrape),
        ("analysis", args.skip_analysis),
        ("match",    args.skip_match),
        ("charts",   args.skip_charts),
        ("report",   args.skip_report),
    ] if v]
    if etapas_skip:
        log(f"Etapas puladas  : {', '.join(etapas_skip)}", "WARN")
    if dry:
        log("Modo dry-run — nenhum comando sera executado", "WARN")
    print()

    log("── Verificando dependencias ──────────────────────────────────", "STEP")
    ensure_deps(dry)
    print()

    base_runs = Path(args.output_dir) if args.output_dir else HERE / "runs"
    gp = GlobalProgress(years, base=base_runs) if args.per_year else None

    t_total = time.time()

    if args.per_year:
        log(f"Total: {len(years)} ano(s) × {ETAPAS_POR_ANO} etapas"
            f" = {len(years) * ETAPAS_POR_ANO} etapas", "INFO")
        if gp and any(gp._taxas.values()):
            for modo, vals in gp._taxas.items():
                if vals:
                    log(f"  Taxa hist. {modo}: {sum(vals)/len(vals):.2f} art/s"
                        f" (de {len(vals)} run(s))")
        print()

        for year in years:
            dest = (
                Path(args.output_dir) / str(year)
                if args.output_dir
                else HERE / "runs" / str(year)
            )
            idx_ano = years.index(year) + 1
            log(f"{'='*62}", "STEP")
            log(f"  ANO {idx_ano}/{len(years)}: {year}  →  {dest}", "STEP")
            if gp:
                log(f"  {gp.barra()}", "STEP")
            log(f"{'='*62}", "STEP")
            print()
            run_pipeline(
                years=[year],
                raw_years=[str(year)],
                terms=args.terms,
                collection=args.collection,
                dest=dest,
                python=python,
                skip_search=args.skip_search,
                skip_scrape=args.skip_scrape,
                skip_analysis=args.skip_analysis,
                skip_match=args.skip_match,
                skip_charts=args.skip_charts,
                skip_report=args.skip_report,
                dry=dry,
                terms_fields=args.terms_fields,
                terms_match_mode=args.terms_match_mode,
                gp=gp,
            )

        # ── Chart agregado multi-ano ───────────────────────────────────────────
        if not args.skip_charts and len(years) > 1:
            print()
            log("=" * 62, "STEP")
            log("Chart agregado multi-ano (todos os anos comparados)", "STEP")
            log("=" * 62, "STEP")
            log(f"  Fonte    : {base_runs}/")
            log(f"  Saida    : {base_runs}/")
            log(f"  Graficos : chart_status.png, chart_sources.png, chart_time.png")
            if not dry:
                base_runs.mkdir(parents=True, exist_ok=True)
            rc = run(
                [python, "process_charts.py",
                 "--base",   str(base_runs),
                 "--output", str(base_runs)],
                dry,
            )
            if rc != 0:
                log("  Chart agregado falhou — continuando", "WARN")
            elif not dry:
                charts = list(base_runs.glob("chart_*.png"))
                if charts:
                    log(f"  {len(charts)} grafico(s) agregado(s) gerado(s) em {base_runs.name}/")
            print()
    else:
        dest = (
            Path(args.output_dir)
            if args.output_dir
            else HERE / "runs" / anos_label
        )
        log(f"Destino         : {dest}")
        print()
        run_pipeline(
            years=years,
            raw_years=args.year,
            terms=args.terms,
            collection=args.collection,
            dest=dest,
            python=python,
            skip_search=args.skip_search,
            skip_scrape=args.skip_scrape,
            skip_analysis=args.skip_analysis,
            skip_match=args.skip_match,
            skip_charts=args.skip_charts,
            skip_report=args.skip_report,
            dry=dry,
            terms_fields=args.terms_fields,
            terms_match_mode=args.terms_match_mode,
            gp=None,
        )

    elapsed = time.time() - t_total
    print()
    log("=" * 58, "STEP")
    log(f"Pipeline concluido em {humanize(elapsed)}")
    log("=" * 58, "STEP")
    print()


if __name__ == "__main__":
    main()
