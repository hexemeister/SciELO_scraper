#!/usr/bin/env python3
"""
teste_pipeline.py  v1.0
=======================
Executa o pipeline completo de teste: busca → extração (3 estratégias) →
análise de discrepância → cópia para diretório de exemplos.

UTILIZAÇÃO
----------
  python teste_pipeline.py --year ANO [opções]

OPÇÕES
------
  --year ANO         Ano a buscar (obrigatório). Ex: 2022
  --terms T1 T2 ...  Termos de busca (default: avalia educa)
  --collection COD   Coleção SciELO (default: scl)
  --output-dir DIR   Diretório de destino (default: exemplos/<ano>/)
  --skip-search      Reutilizar o CSV mais recente sc_* em vez de buscar
  --skip-scrape      Reutilizar runs existentes (só gera análise e copia)
  --dry-run          Mostra o que faria sem executar nada
  -h, --help, -?     Mostrar esta mensagem de ajuda e sair

EXEMPLOS
--------
  python teste_pipeline.py --year 2023
  python teste_pipeline.py --year 2022 --collection arg --output-dir exemplos/arg_2022
  python teste_pipeline.py --year 2023 --skip-search   # reutiliza CSV existente
"""

__version__ = "1.0"

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Forçar UTF-8 no stdout (Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Utilitários ───────────────────────────────────────────────────────────────

HERE = Path(__file__).parent

ESTRATEGIAS = [
    {"label": "padrão (api+html)", "slug": "api+html", "flags": []},
    {"label": "apenas-api",        "slug": "api",       "flags": ["--only-api"]},
    {"label": "apenas-html",       "slug": "html",      "flags": ["--only-html"]},
]


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = {"INFO": "[OK]", "WARN": "[AV]", "ERROR": "[ER]", "STEP": ">>>"}.get(level, "   ")
    try:
        print(f"{ts}  {prefix}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"{ts}  {prefix}  {msg.encode('ascii', errors='replace').decode()}", flush=True)


def run(cmd: list[str], dry_run: bool) -> int:
    log(f"$ {' '.join(str(c) for c in cmd)}", "STEP")
    if dry_run:
        return 0
    result = subprocess.run(cmd, cwd=HERE)
    return result.returncode


def humanize(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Análise de discrepância ───────────────────────────────────────────────────

def gerar_analise(runs: dict, year: int, total: int) -> str:
    """Gera o texto Markdown da análise de discrepância."""

    def pct(n):
        return f"{n/total*100:.1f}%" if total else "0%"

    # Carregar stats
    stats = {}
    for modo, path in runs.items():
        sfile = path / "stats.json"
        if sfile.exists():
            with open(sfile, encoding="utf-8") as f:
                stats[modo] = json.load(f)

    if not stats:
        return "⚠️  Nenhum stats.json encontrado — análise não gerada.\n"

    try:
        import pandas as pd
        dfs = {}
        for modo, path in runs.items():
            rfile = path / "resultado.csv"
            if rfile.exists():
                dfs[modo] = pd.read_csv(rfile).set_index("PID_limpo")
    except ImportError:
        dfs = {}

    # ── Tabela resumo ─────────────────────────────────────────────────────────
    linhas_tabela = []
    for modo, st in stats.items():
        ok_c  = st.get("ok_completo", 0)
        ok_p  = st.get("ok_parcial", 0)
        erro  = st.get("erro_extracao", 0)
        suc   = st.get("sucesso_total", ok_c + ok_p)
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

    # ── Análise de diferenças entre runs ─────────────────────────────────────
    secoes = []

    if len(dfs) == 3 and "padrão" in dfs and "apenas-api" in dfs and "apenas-html" in dfs:
        padrao_df = dfs["padrão"]
        api_df    = dfs["apenas-api"]
        html_df   = dfs["apenas-html"]

        padrao_ok  = set(padrao_df[padrao_df["status"] == "ok_completo"].index)
        api_ok     = set(api_df[api_df["status"] == "ok_completo"].index)
        html_ok    = set(html_df[html_df["status"] == "ok_completo"].index)

        fixed_by_html = padrao_ok - api_ok
        html_only_fail = set(html_df[html_df["status"] != "ok_completo"].index) - \
                         set(api_df[api_df["status"] != "ok_completo"].index)

        all_noncomplete = (
            set(padrao_df[padrao_df["status"] != "ok_completo"].index) |
            set(api_df[api_df["status"] != "ok_completo"].index) |
            set(html_df[html_df["status"] != "ok_completo"].index)
        )
        always_partial = set.intersection(
            set(padrao_df[padrao_df["status"] != "ok_completo"].index),
            set(api_df[api_df["status"] != "ok_completo"].index),
            set(html_df[html_df["status"] != "ok_completo"].index),
        )

        # AoP check
        def is_aop(pid): return str(pid)[14:17] == "005"

        # Secção: HTML corrigiu
        if fixed_by_html:
            rows = []
            for pid in sorted(fixed_by_html):
                api_row    = api_df.loc[pid]
                padrao_row = padrao_df.loc[pid]
                aop        = " (AoP)" if is_aop(pid) else ""
                rows.append(
                    f"| `{pid}`{aop} | {api_row['status']} | "
                    f"{padrao_row['status']} | {padrao_row['fonte_extracao']} |"
                )
            secoes.append(
                f"## 2. Artigos corrigidos pelo fallback HTML ({len(fixed_by_html)})\n\n"
                "| PID | Status (api) | Status (padrão) | Fonte no padrão |\n"
                "|---|---|---|---|\n"
                + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 2. Artigos corrigidos pelo fallback HTML\n\n"
                "Nenhum artigo foi corrigido pelo fallback HTML nesta execução."
            )

        # Secção: HTML-only falhou
        if html_only_fail:
            rows = []
            for pid in sorted(html_only_fail):
                html_row = html_df.loc[pid]
                api_row  = api_df.loc[pid]
                rows.append(
                    f"| `{pid}` | {api_row['status']} | {html_row['status']} | "
                    f"{html_row.get('fonte_extracao', '—')} |"
                )
            secoes.append(
                f"## 3. Artigos que o HTML-only falhou mas a API recuperou ({len(html_only_fail)})\n\n"
                "| PID | Status (api) | Status (html) | Fonte HTML |\n"
                "|---|---|---|---|\n"
                + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 3. Artigos que o HTML-only falhou mas a API recuperou\n\n"
                "Nenhum caso nesta execução."
            )

        # Secção: sempre parcial
        if always_partial:
            rows = []
            for pid in sorted(always_partial):
                titulo = str(padrao_df.loc[pid].get("Titulo_PT", ""))[:60] if pid in padrao_df.index else "—"
                rows.append(f"| `{pid}` | {titulo} |")
            secoes.append(
                f"## 4. Artigos persistentemente não-completos em todos os modos ({len(always_partial)})\n\n"
                "Estes artigos não atingiram `ok_completo` em nenhuma estratégia — "
                "a limitação é da fonte, não do scraper.\n\n"
                "| PID | Título (PT) |\n"
                "|---|---|\n"
                + "\n".join(rows)
            )
        else:
            secoes.append(
                "## 4. Artigos persistentemente não-completos\n\n"
                "Nenhum artigo ficou sem `ok_completo` em todas as estratégias."
            )

        # Secção: tempo
        tempos = []
        for modo, st in stats.items():
            tempos.append(
                f"| {modo} | {st.get('elapsed_humanizado','?')} "
                f"| {st.get('avg_per_article_s','?')} s |"
            )
        secoes.append(
            "## 5. Desempenho temporal\n\n"
            "| Modo | Tempo total | Média/artigo |\n"
            "|---|---|---|\n"
            + "\n".join(tempos)
        )

    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# Análise de Discrepância — {year}

**Corpus:** {total} artigos SciELO Brasil ({year}), termos: avalia$, educa$
**Gerado em:** {ts_now}

---

## 1. Resumo executivo

{tabela}

---

""" + "\n\n---\n\n".join(secoes) + "\n"


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
    ap.add_argument("--year", type=int, required=True, metavar="ANO",
        help="Ano a buscar (ex: 2022)")
    ap.add_argument("--terms", nargs="+", default=["avalia", "educa"], metavar="TERMO",
        help="Termos de busca (default: avalia educa)")
    ap.add_argument("--collection", default="scl", metavar="COD",
        help="Coleção SciELO (default: scl)")
    ap.add_argument("--output-dir", default=None, metavar="DIR",
        help="Diretório de destino (default: exemplos/<ano>/)")
    ap.add_argument("--skip-search", action="store_true",
        help="Reutilizar o CSV sc_* mais recente em vez de buscar")
    ap.add_argument("--skip-scrape", action="store_true",
        help="Reutilizar runs existentes (só gera análise e copia)")
    ap.add_argument("--dry-run", action="store_true",
        help="Mostra o que faria sem executar nada")
    ap.add_argument("--version", action="version", version=f"v{__version__}")
    args = ap.parse_args()

    dest = Path(args.output_dir) if args.output_dir else HERE / "exemplos" / str(args.year)
    python = sys.executable
    dry    = args.dry_run

    print()
    log(f"Pipeline de teste — ano {args.year}", "STEP")
    log(f"Termos  : {args.terms}")
    log(f"Coleção : {args.collection}")
    log(f"Destino : {dest}")
    if dry:
        log("Modo dry-run — nenhum comando será executado", "WARN")
    print()

    t_total = time.time()

    # ── 1. Busca ──────────────────────────────────────────────────────────────
    csv_path = None

    if args.skip_search or args.skip_scrape:
        candidates = sorted(HERE.glob("sc_*.csv"), reverse=True)
        if candidates:
            csv_path = candidates[0]
            log(f"Reutilizando CSV existente: {csv_path.name}")
        else:
            log("Nenhum CSV sc_* encontrado — executando busca mesmo assim", "WARN")

    if csv_path is None:
        log("── ETAPA 1/5: Busca ──────────────────────────────────────────", "STEP")
        cmd = [python, "scielo_search.py",
               "--terms", *args.terms,
               "--years", str(args.year),
               "--collection", args.collection]
        rc = run(cmd, dry)
        if rc != 0:
            log("Busca falhou — abortando", "ERROR")
            sys.exit(rc)

        if not dry:
            candidates = sorted(HERE.glob("sc_*.csv"), reverse=True)
            if not candidates:
                log("CSV de saída não encontrado após busca", "ERROR")
                sys.exit(1)
            csv_path = candidates[0]
            log(f"CSV gerado: {csv_path.name}")
        else:
            csv_path = HERE / f"sc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    print()

    # ── 2-4. Scraping (3 estratégias) ─────────────────────────────────────────
    run_dirs = {}

    for i, est in enumerate(ESTRATEGIAS, start=2):
        etapa = f"── ETAPA {i}/5: Scraping {est['label']} ──────────────────────────"
        log(etapa, "STEP")

        if args.skip_scrape:
            # Procura pasta existente com o slug desta estratégia
            stem = csv_path.stem
            candidates = sorted(
                HERE.glob(f"{stem}_s_*_{est['slug']}"),
                reverse=True,
            )
            if candidates:
                run_dirs[est["label"]] = candidates[0]
                log(f"Reutilizando: {candidates[0].name}")
                print()
                continue
            else:
                log(f"Pasta não encontrada para {est['slug']} — executando scraping", "WARN")

        cmd = [python, "scielo_scraper.py", str(csv_path)] + est["flags"]
        rc = run(cmd, dry)
        if rc != 0:
            log(f"Scraping {est['label']} falhou (código {rc}) — continuando", "WARN")

        if not dry:
            stem = csv_path.stem
            candidates = sorted(
                HERE.glob(f"{stem}_s_*_{est['slug']}"),
                reverse=True,
            )
            if candidates:
                run_dirs[est["label"]] = candidates[0]
                log(f"Pasta gerada: {candidates[0].name}")
            else:
                log(f"Pasta de resultado não encontrada para {est['slug']}", "WARN")
        else:
            run_dirs[est["label"]] = HERE / f"{csv_path.stem}_s_DRY_{est['slug']}"
        print()

    # ── 5. Análise de discrepância ────────────────────────────────────────────
    log("── ETAPA 5/5: Análise de discrepância ────────────────────────────", "STEP")

    # Mapeia label → modo canónico para a análise
    modo_map = {
        "padrão (api+html)": "padrão",
        "apenas-api":        "apenas-api",
        "apenas-html":       "apenas-html",
    }
    runs_analise = {modo_map.get(k, k): v for k, v in run_dirs.items()}

    total = 0
    if not dry and run_dirs:
        # Total a partir do stats.json do modo padrão (ou qualquer um disponível)
        for modo, path in run_dirs.items():
            sfile = path / "stats.json"
            if sfile.exists():
                with open(sfile, encoding="utf-8") as f:
                    total = json.load(f).get("total", 0)
                break

    analise_md = gerar_analise(runs_analise, args.year, total) if not dry else \
        f"# Análise de Discrepância — {args.year}\n\n(dry-run)\n"

    analise_path = HERE / f"ANALISE_DISCREPANCIA_{args.year}.md"
    if not dry:
        analise_path.write_text(analise_md, encoding="utf-8")
        log(f"Análise gerada: {analise_path.name}")

    # Imprimir no terminal
    print()
    print("─" * 62)
    print(analise_md)
    print("─" * 62)
    print()

    # ── 6. Copiar para destino ────────────────────────────────────────────────
    log(f"── Copiando para {dest} ───────────────────────────────────────", "STEP")

    if not dry:
        dest.mkdir(parents=True, exist_ok=True)

        # CSV de busca + params
        for f in [csv_path, csv_path.with_name(csv_path.stem + "_params.json")]:
            if f and f.exists():
                shutil.copy2(f, dest / f.name)
                log(f"  Copiado: {f.name}")

        # Pastas de scraping
        for modo, path in run_dirs.items():
            if path.exists():
                target = dest / path.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(path, target)
                log(f"  Copiado: {path.name}/")

        # Análise
        if analise_path.exists():
            shutil.copy2(analise_path, dest / analise_path.name)
            log(f"  Copiado: {analise_path.name}")
    else:
        log(f"  (dry-run) copiaria CSV, params.json, 3 pastas e análise para {dest}")

    # ── Resumo final ──────────────────────────────────────────────────────────
    elapsed = time.time() - t_total
    print()
    log("=" * 58, "STEP")
    log(f"Pipeline concluído em {humanize(elapsed)}")
    log(f"Resultados em: {dest}")
    log("=" * 58, "STEP")
    print()


if __name__ == "__main__":
    main()
