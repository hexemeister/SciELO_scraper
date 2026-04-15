#!/usr/bin/env python3
"""
run_pipeline.py  v1.4
=====================
Executa o pipeline completo de teste: busca → extração (3 estratégias) →
análise de discrepância → cópia para diretório de exemplos.

Verifica e instala dependências automaticamente antes de começar.

UTILIZAÇÃO
----------
  python run_pipeline.py --year ANO [opções]

OPÇÕES
------
  --year ANO [ANO ...]  Anos a buscar (ex: 2022 ou 2022 2023 ou 2020-2024)
  --terms T1 T2 ...     Termos de busca (default: avalia educa)
  --collection COD      Coleção SciELO (default: scl)
  --output-dir DIR      Diretório de destino (default: exemplos/<ano>/)
  --skip-search         Reutilizar o CSV mais recente sc_* em vez de buscar
  --per-year            Rodar pipeline separado por ano (um CSV e destino por ano)
  --skip-scrape         Reutilizar runs existentes (só gera análise e copia)
  --dry-run             Mostra o que faria sem executar nada
  --stats-report [DIR]  Gera relatório consolidado dos stats.json em DIR (default: exemplos/)
  -h, --help, -?        Mostrar esta mensagem de ajuda e sair

NOTAS
-----
  - O scraper é sempre chamado com --no-resume (cada estratégia começa do zero).
  - Após copiar para exemplos/<ano>/, os originais no diretório raiz são removidos.

EXEMPLOS
--------
  python run_pipeline.py --year 2023
  python run_pipeline.py --year 2022 2023 2024
  python run_pipeline.py --year 2020-2024
  python run_pipeline.py --year 2022 --collection arg --output-dir exemplos/arg_2022
  python run_pipeline.py --year 2023 --skip-search   # reutiliza CSV existente
  python run_pipeline.py --year 2023 --dry-run       # simula sem executar
  python run_pipeline.py --year 2022 2023 2024 --per-year  # um CSV por ano
  python run_pipeline.py --stats-report               # consolida exemplos/ e imprime
  python run_pipeline.py --stats-report exemplos/     # idem com pasta explícita
"""

__version__ = "1.4"

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
    "requests":       "requests",
    "bs4":            "beautifulsoup4",
    "lxml":           "lxml",
    "pandas":         "pandas",
    "tqdm":           "tqdm",
    "brotli":         "brotli",
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

    Etapas por ano (--per-year): busca + 3 scrapings + análise = 5
    """

    ETAPAS_POR_ANO = 5  # busca + api+html + api + html + análise

    def __init__(self, anos: list[int], base: Path | None = None):
        self.anos        = anos
        self.n_anos      = len(anos)
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
        """ETA global estimado, baseado no ritmo atual de etapas."""
        decorrido = time.time() - self.t_inicio
        if self.etapa_atual == 0 or decorrido < 1:
            return "calculando..."
        taxa = self.etapa_atual / decorrido          # etapas/segundo
        restantes = etapas_restantes if etapas_restantes is not None \
                    else (self.total_etapas - self.etapa_atual)
        if restantes <= 0:
            return "quase pronto"
        segundos = restantes / taxa
        return humanize(int(segundos))

    def eta_scraping_str(self, modo: str, n_artigos: int) -> str:
        """ETA estimado para um scraping de n_artigos no modo dado."""
        taxa = self.taxa_media(modo)
        if taxa is None or n_artigos == 0:
            return "sem histórico"
        segundos = n_artigos / taxa
        return humanize(int(segundos))

    def barra(self) -> str:
        """Linha de progresso global para exibir no início de cada etapa."""
        pct = self.etapa_atual / self.total_etapas * 100 if self.total_etapas else 0
        decorrido = humanize(int(time.time() - self.t_inicio))
        eta = self.eta_str()
        return (
            f"[Global {self.etapa_atual}/{self.total_etapas} etapas"
            f"  {pct:.0f}%"
            f"  decorrido={decorrido}"
            f"  ETA≈{eta}]"
        )

    def barra_ano(self, ano: int, etapa_no_ano: int) -> str:
        """Linha de progresso dentro do ano atual."""
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

    # Acumuladores globais
    glob_total        = 0
    glob_ok_c         = 0
    glob_ok_p         = 0
    glob_nada         = 0
    glob_erro         = 0
    glob_elapsed: dict[str, float] = {"api+html": 0.0, "api": 0.0, "html": 0.0}
    glob_elapsed_total = 0.0   # soma dos 3 modos (tempo real de execução)

    for ano_dir in anos:
        ano = int(ano_dir.name)
        linhas.append(f"## Ano {ano}\n")
        linhas.append(
            "| Modo | Total | ok_completo | ok_parcial | nada_encontrado"
            " | erro_extracao | Tempo | Média/art |"
        )
        linhas.append("|---|---:|---:|---:|---:|---:|---:|---:|")

        ano_total = None  # usar total do primeiro modo encontrado

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

            # Acumula tempo por modo e total
            glob_elapsed[modo]  += elapsed
            glob_elapsed_total  += elapsed

            # Acumula status e total usando api+html como referência
            if modo == "api+html":
                ano_total  = total
                glob_ok_c += ok_c
                glob_ok_p += ok_p
                glob_nada += nada
                glob_erro += erro

        if ano_total is not None:
            glob_total += ano_total

        linhas.append("")  # linha em branco após tabela do ano

        # Sub-tabela de fontes (apenas api+html, que é o modo completo)
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
                        # Suporta {fonte: {n, pct}} e {fonte: int}
                        def _n(v): return v["n"] if isinstance(v, dict) else v
                        def _pct(v): return v.get("pct", "—") if isinstance(v, dict) else "—"
                        for fonte, val in sorted(por_fonte.items(), key=lambda x: -_n(x[1])):
                            linhas.append(f"| {fonte} | {_n(val)} | {_pct(val)} |")
                        linhas.append("")
                except Exception:
                    pass

    # ── Totais globais ─────────────────────────────────────────────────────────
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

    # Preferir uv se disponivel
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

    # Carregar stats e DataFrames numa única passagem por pasta
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

    # ── Tabela resumo ─────────────────────────────────────────────────────────
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

    # ── Secções de análise detalhada ──────────────────────────────────────────
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

        # Secção 2: HTML corrigiu
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

        # Secção 3: HTML-only falhou
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

        # Secção 4: sempre parcial
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

    # Secção 5: tempo
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
    """Imprime linha de progresso global + local antes de cada etapa."""
    if gp is None or gp.n_anos <= 1:
        return
    print(f"  {gp.barra_ano(ano, etapa_no_ano)}  {gp.barra()}", flush=True)


def _contar_artigos_csv(csv_path: Path) -> int:
    """Conta linhas de dados no CSV (subtrai cabeçalho). Retorna 0 se falhar."""
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


def run_pipeline(years: list[int], raw_years: list[str], terms: list[str],
                 collection: str, dest: Path, python: str,
                 skip_search: bool, skip_scrape: bool, dry: bool,
                 gp: "GlobalProgress | None" = None):
    """Executa search → 3×scrape → análise → cópia para dest."""

    ano_ref   = years[0]   # ano de referência para o progresso
    anos_label = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])

    # ── 1. Busca ──────────────────────────────────────────────────────────────
    csv_path = None
    etapa_local = 1

    if skip_search or skip_scrape:
        csv_path = latest("sc_*.csv")
        if csv_path:
            log(f"Reutilizando CSV existente: {csv_path.name}")
        else:
            log("Nenhum CSV sc_* encontrado — executando busca mesmo assim", "WARN")

    if csv_path is None:
        _log_progresso(gp, ano_ref, etapa_local)
        log("── ETAPA 1/5: Busca ──────────────────────────────────────────", "STEP")
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
            log(f"CSV gerado: {csv_path.name}")
        else:
            csv_path = HERE / f"sc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        # skip: a etapa de busca não executa, mas avança o contador
        if gp:
            gp.avancar()
    print()

    # Número de artigos (para estimativa de ETA do scraping)
    n_artigos = _contar_artigos_csv(csv_path) if not dry else 0

    # ── 2-4. Scraping (3 estratégias) ─────────────────────────────────────────
    run_dirs: dict[str, Path] = {}
    stem = csv_path.stem

    for i, est in enumerate(ESTRATEGIAS, start=2):
        etapa_local = i
        _log_progresso(gp, ano_ref, etapa_local)

        eta_scr = ""
        if gp and n_artigos:
            eta_scr = f"  (ETA scraping≈{gp.eta_scraping_str(est['slug'], n_artigos)})"

        log(f"── ETAPA {i}/5: Scraping {est['modo']}{eta_scr} ──────────────────", "STEP")

        if skip_scrape:
            found = latest(f"{stem}_s_*_{est['slug']}")
            if found:
                run_dirs[est["label"]] = found
                log(f"Reutilizando: {found.name}")
                if gp:
                    gp.avancar()
                print()
                continue
            log(f"Pasta não encontrada para {est['slug']} — executando scraping", "WARN")

        rc = run([python, "scielo_scraper.py", str(csv_path), "--no-resume"] + est["flags"], dry)
        if gp:
            gp.avancar()
        if rc != 0:
            log(f"Scraping {est['modo']} falhou (codigo {rc}) — continuando", "WARN")

        if not dry:
            found = latest(f"{stem}_s_*_{est['slug']}")
            if found:
                run_dirs[est["label"]] = found
                log(f"Pasta gerada: {found.name}")
            else:
                log(f"Pasta de resultado não encontrada para {est['slug']}", "WARN")
        else:
            run_dirs[est["label"]] = HERE / f"{stem}_s_DRY_{est['slug']}"
        print()

    # ── 5. Análise de discrepância ────────────────────────────────────────────
    etapa_local = 5
    _log_progresso(gp, ano_ref, etapa_local)
    log("── ETAPA 5/5: Analise de discrepancia ───────────────────────────", "STEP")

    analise_md = (
        gerar_analise(run_dirs, years, terms)
        if not dry
        else f"# Análise de Discrepância — {anos_label}\n\n(dry-run)\n"
    )
    if gp:
        gp.avancar()

    analise_path = HERE / f"ANALISE_DISCREPANCIA_{anos_label}.md"
    if not dry:
        analise_path.write_text(analise_md, encoding="utf-8")
        log(f"Analise gerada: {analise_path.name}")

    print()
    print("─" * 62)
    print(analise_md)
    print("─" * 62)
    print()

    # ── 6. Copiar para destino ────────────────────────────────────────────────
    log(f"── Copiando para {dest} ──────────────────────────────────────", "STEP")

    if not dry:
        dest.mkdir(parents=True, exist_ok=True)

        params = csv_path.with_name(csv_path.stem + "_params.json")
        for f in [csv_path, params]:
            if f.exists():
                shutil.copy2(f, dest / f.name)
                log(f"  Copiado: {f.name}")

        for est in ESTRATEGIAS:
            path = run_dirs.get(est["label"])
            if path and path.exists():
                target = dest / path.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(path, target)
                log(f"  Copiado: {path.name}/")

        shutil.copy2(analise_path, dest / analise_path.name)
        log(f"  Copiado: {analise_path.name}")

        # ── Limpar originais do diretório raiz ─────────────────────────────────
        log("Limpando originais do diretorio raiz...")
        for f in [csv_path, params]:
            if f.exists():
                f.unlink()
                log(f"  Removido: {f.name}")
        for est_item in ESTRATEGIAS:
            path = run_dirs.get(est_item["label"])
            if path and path.exists():
                shutil.rmtree(path)
                log(f"  Removido: {path.name}/")
        if analise_path.exists():
            analise_path.unlink()
            log(f"  Removido: {analise_path.name}")
    else:
        log(f"  (dry-run) copiaria CSV, params.json, 3 pastas e analise para {dest}")
        log(f"  (dry-run) removeria os originais do diretorio raiz")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=f"Pipeline de teste SciELO v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        add_help=False,
    )
    ap.add_argument("-h", "--help", "-?", action="help",
        help="Mostrar esta mensagem e sair")
    ap.add_argument("--year", nargs="*", metavar="ANO",
        help="Anos a buscar. Ex: 2022  ou  2022 2023  ou  2020-2024")
    ap.add_argument("--terms", nargs="+", default=["avalia", "educa"], metavar="TERMO",
        help="Termos de busca (default: avalia educa)")
    ap.add_argument("--collection", default="scl", metavar="COD",
        help="Colecao SciELO (default: scl)")
    ap.add_argument("--output-dir", default=None, metavar="DIR",
        help="Diretorio de destino (default: exemplos/<ano>/)")
    ap.add_argument("--per-year", action="store_true",
        help="Rodar pipeline separado por ano (um CSV e destino por ano)")
    ap.add_argument("--skip-search", action="store_true",
        help="Reutilizar o CSV sc_* mais recente em vez de buscar")
    ap.add_argument("--skip-scrape", action="store_true",
        help="Reutilizar runs existentes (só gera análise e copia)")
    ap.add_argument("--dry-run", action="store_true",
        help="Mostra o que faria sem executar nada")
    ap.add_argument(
        "--stats-report", nargs="?", const="exemplos", metavar="DIR",
        help="Gera relatório consolidado dos stats.json em DIR (default: exemplos/)",
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
    log(f"Pipeline de teste — {anos_label}", "STEP")
    log(f"Termos     : {args.terms}")
    log(f"Colecao    : {args.collection}")
    log(f"Por ano    : {'sim' if args.per_year else 'nao'}")
    if dry:
        log("Modo dry-run — nenhum comando sera executado", "WARN")
    print()

    log("── Verificando dependencias ──────────────────────────────────", "STEP")
    ensure_deps(dry)
    print()

    # Inicializar progresso global (só relevante em --per-year com múltiplos anos)
    base_exemplos = Path(args.output_dir) if args.output_dir else HERE / "exemplos"
    gp = GlobalProgress(years, base=base_exemplos) if args.per_year else None

    t_total = time.time()

    if args.per_year:
        # Um pipeline completo por ano
        log(f"Total: {len(years)} ano(s) × {GlobalProgress.ETAPAS_POR_ANO} etapas"
            f" = {len(years) * GlobalProgress.ETAPAS_POR_ANO} etapas", "INFO")
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
                else HERE / "exemplos" / str(year)
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
                dry=dry,
                gp=gp,
            )
    else:
        # Pipeline único com todos os anos juntos
        dest = (
            Path(args.output_dir)
            if args.output_dir
            else HERE / "exemplos" / anos_label
        )
        log(f"Destino    : {dest}")
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
            dry=dry,
            gp=None,   # sem progresso global no modo conjunto
        )

    elapsed = time.time() - t_total
    print()
    log("=" * 58, "STEP")
    log(f"Pipeline concluido em {humanize(elapsed)}")
    log("=" * 58, "STEP")
    print()


if __name__ == "__main__":
    main()
