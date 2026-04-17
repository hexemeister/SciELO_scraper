# SciELO Scraper — Contexto do Projeto

## Scripts principais

| Script | Função | Entrada | Saída |
|---|---|---|---|
| `scielo_search.py` | Busca artigos no SciELO Search | `--terms`, `--years`, `--collection` | `sc_<ts>.csv` + `sc_<ts>_params.json` |
| `scielo_scraper.py` | Extrai título/resumo/keywords PT | `sc_<ts>.csv` | `<stem>_s_<ts>_<modo>/` |
| `run_pipeline.py` | Pipeline completo de teste (v1.4) | `--year` | `exemplos/<ano>/` |
| `create_charts.py` | Gera gráficos comparativos das execuções | `[--base]`, `--years`, `--output`, `--timestamp` | `chart_status[_<ts>].png`, `chart_sources[_<ts>].png`, `chart_time[_<ts>].png` |
| `terms_matcher.py` | Detecta termos por campo e gera CSV auditável | `--base`, `--years`, `--terms`, `--mode` | `terms_<ts>.csv` + `terms_<ts>.log` + `terms_<ts>_stats.json` |
| `_gerar_fluxograma.py` | Gera SVG do fluxograma de extração | — | `flowchart_extracao_pt_br.svg` |

## Convenções obrigatórias

- **Python:** sempre `uv run python` / `uv pip install` — nunca `pip` direto
- **Commits:** sempre com `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- **Idioma:** comunicação em PT-BR

## Padrões de nomenclatura

- CSV de busca: `sc_<timestamp>.csv`
- Params da busca: `sc_<timestamp>_params.json`
- Pasta de scraping: `<stem>_s_<timestamp>_<modo>/`
  - `<modo>`: `api+html` (padrão) | `api` | `html`
- Exemplos de runs: `exemplos/<ano>/`

## Comportamento do scielo_search.py

- **`--show-params [ARQ]`:** sem `ARQ`, lê o `_params.json` mais recente no diretório atual via glob; com `ARQ`, lê o arquivo indicado (relativo ou absoluto) — independente de `--terms`/`--years`
- **Truncamento:** `$` adicionado automaticamente ao final de cada termo (ex: `avalia` → `avalia$`); desativar com `--no-truncate`
- **`--list-collections`:** lista as 36 coleções SciELO e sai

## Comportamento do run_pipeline.py (v1.4)

- **Estratégias testadas:** padrão (`api+html`), apenas-api, apenas-html — sempre em sequência completa
- **`--no-resume` implícito:** o scraper é sempre chamado com `--no-resume`; cada estratégia começa do zero
- **Limpeza automática:** após copiar tudo para `exemplos/<ano>/`, os originais no diretório raiz são removidos (CSV, `_params.json`, 3 pastas de scraping, `ANALISE_DISCREPANCIA_*.md`)
- **`-?`:** equivalente a `-h` / `--help`
- **`--dry-run`:** mostra os comandos sem executar, inclusive a limpeza que seria feita
- **`--skip-scrape`:** reutiliza pastas existentes — não aplica `--no-resume` (skip não reexecuta o scraper)
- **`--stats-report [DIR]`:** gera relatório Markdown consolidado de todos os `stats.json` em `exemplos/` (ou `DIR`); funciona sem `--year` — modo standalone
- **`--per-year`:** executa o pipeline para cada ano encontrado em `exemplos/`, com barra de progresso global e ETA estimado por histórico de execuções anteriores

## Comportamento do scraper (scielo_scraper.py v2.4)

- **Fonte primária:** ArticleMeta REST API (ISIS-JSON)
- **Fallback:** HTML scraping multi-estratégia (meta tags → body → link PT → og:url)
- **`--resume`:** reutiliza a pasta existente mais recente (não cria nova), log anexado com separador `══ RETOMADA ══`, tempo acumulado nos stats
- **`--checkpoint N`:** salva CSV a cada N artigos (default: 25; 1=cada artigo; 0=só no final)
- **Artigos AoP:** PID com `005` nas posições 14-16 — não indexados na API, só disponíveis via HTML

## Status de extração

| Status | Significado |
|---|---|
| `ok_completo` | Título + resumo + keywords extraídos |
| `ok_parcial` | Pelo menos um campo extraído |
| `nada_encontrado` | Página acessada, sem dados |
| `erro_extracao` | Falha de acesso (ex: 404) |
| `erro_pid_invalido` | PID fora do padrão |

## Dependências

```bash
uv pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli
```

> `brotli` é obrigatório — o CDN do SciELO usa compressão Brotli.

## Skills disponíveis (.claude/skills/)

### Customizadas (projeto)
| Skill | Quando usar |
|---|---|
| `scielo-analysis` | Analisar `resultado.csv` e `stats.json`, comparar modos, gerar gráficos |
| `scielo-communication` | Redigir metodologia, resultados, análise de discrepância |
| `scielo-methodology` | Decidir termos de busca, modo de extração, interpretar cobertura |

### K-Dense (genéricas)
`statistical-analysis`, `exploratory-data-analysis`, `matplotlib`, `seaborn`, `scientific-writing`, `literature-review`, `hypothesis-generation`

## Repositório

- GitHub: https://github.com/hexemeister/SciELO_scraper
- Branch principal: `master`

## Fluxo de sessão recomendado

**Iniciar sessão:**
```bash
cd C:\Users\hexem\dev\python\SciELO_scraper
claude          # nova sessão (CLAUDE.md carregado automaticamente)
# ou
claude /resume  # retomar sessão anterior com histórico completo
```

**Durante a sessão:**
- Uma tarefa por sessão — scraper, busca, pipeline, docs — não misturar
- Commitar ao terminar cada tarefa antes de encerrar

**Encerrar sessão:**
```
/compact   → compacta o histórico (resumo incluso na próxima sessão)
```

**Lembrete ao Claude:** ao final de qualquer tarefa concluída, sugerir `/compact` antes de encerrar.

## O que NÃO alterar sem contexto

- Lógica de extração HTML: funções `fetch_*`, `extract_*`, `is_article_page` em `scielo_scraper.py`
- Ordem de prioridade das fontes de extração
- Lógica de detecção AoP (`pid[14:17] == "005"`)
