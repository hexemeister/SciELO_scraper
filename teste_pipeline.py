#!/usr/bin/env python3
"""
teste_pipeline.py  v1.3
=======================
Executa o pipeline completo de teste: busca → extração (3 estratégias) →
análise de discrepância → cópia para diretório de exemplos.

Verifica e instala dependências automaticamente antes de começar.

UTILIZAÇÃO
----------
  python teste_pipeline.py --year ANO [opções]

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
  -h, --help, -?        Mostrar esta mensagem de ajuda e sair

NOTAS
-----
  - O scraper é sempre chamado com --no-resume (cada estratégia começa do zero).
  - Após copiar para exemplos/<ano>/, os originais no diretório raiz são removidos.

EXEMPLOS
--------
  python teste_pipeline.py --year 2023
  python teste_pipeline.py --year 2022 2023 2024
  python teste_pipeline.py --year 2020-2024
  python teste_pipeline.py --year 2022 --collection arg --output-dir exemplos/arg_2022
  python teste_pipeline.py --year 2023 --skip-search   # reutiliza CSV existente
  python teste_pipeline.py --year 2023 --dry-run       # simula sem executar
  python teste_pipeline.py --year 2022 2023 2024 --per-year  # um CSV por ano
"""

__version__ = "1.3"

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

STATUS_KEYS = ("ok_completo", "ok_parcial", "erro_extracao")

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

def run_pipeline(years: list[int], raw_years: list[str], terms: list[str],
                 collection: str, dest: Path, python: str,
                 skip_search: bool, skip_scrape: bool, dry: bool):
    """Executa search → 3×scrape → análise → cópia para dest."""

    anos_label = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])

    # ── 1. Busca ──────────────────────────────────────────────────────────────
    csv_path = None

    if skip_search or skip_scrape:
        csv_path = latest("sc_*.csv")
        if csv_path:
            log(f"Reutilizando CSV existente: {csv_path.name}")
        else:
            log("Nenhum CSV sc_* encontrado — executando busca mesmo assim", "WARN")

    if csv_path is None:
        log("── ETAPA 1/5: Busca ──────────────────────────────────────────", "STEP")
        rc = run(
            [python, "scielo_search.py",
             "--terms", *terms,
             "--collection", collection,
             "--years", *raw_years],
            dry,
        )
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
    print()

    # ── 2-4. Scraping (3 estratégias) ─────────────────────────────────────────
    run_dirs: dict[str, Path] = {}
    stem = csv_path.stem

    for i, est in enumerate(ESTRATEGIAS, start=2):
        log(f"── ETAPA {i}/5: Scraping {est['modo']} ─────────────────────────────", "STEP")

        if skip_scrape:
            found = latest(f"{stem}_s_*_{est['slug']}")
            if found:
                run_dirs[est["label"]] = found
                log(f"Reutilizando: {found.name}")
                print()
                continue
            log(f"Pasta não encontrada para {est['slug']} — executando scraping", "WARN")

        rc = run([python, "scielo_scraper.py", str(csv_path), "--no-resume"] + est["flags"], dry)
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
    log("── ETAPA 5/5: Analise de discrepancia ───────────────────────────", "STEP")

    analise_md = (
        gerar_analise(run_dirs, years, terms)
        if not dry
        else f"# Análise de Discrepância — {anos_label}\n\n(dry-run)\n"
    )

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
    ap.add_argument("--year", nargs="+", required=True, metavar="ANO",
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
    ap.add_argument("--version", action="version", version=f"v{__version__}")
    args = ap.parse_args()

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

    t_total = time.time()

    if args.per_year:
        # Um pipeline completo por ano
        for year in years:
            dest = (
                Path(args.output_dir) / str(year)
                if args.output_dir
                else HERE / "exemplos" / str(year)
            )
            log(f"{'='*62}", "STEP")
            log(f"  ANO: {year}  →  {dest}", "STEP")
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
        )

    elapsed = time.time() - t_total
    print()
    log("=" * 58, "STEP")
    log(f"Pipeline concluido em {humanize(elapsed)}")
    log("=" * 58, "STEP")
    print()


if __name__ == "__main__":
    main()
