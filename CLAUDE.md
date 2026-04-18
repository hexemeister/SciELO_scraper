# SciELO Scraper — Contexto do Projeto

## Scripts principais

| Script | Função | Entrada | Saída |
|---|---|---|---|
| `scielo_search.py` | Busca artigos no SciELO Search | `--terms`, `--years`, `--collection` | `sc_<ts>.csv` + `sc_<ts>_params.json` |
| `scielo_scraper.py` | Extrai título/resumo/keywords PT | `sc_<ts>.csv` | `<stem>_s_<ts>_<modo>/` |
| `run_pipeline.py` | Pipeline completo (v2.0): busca → 3×scraping → análise → 3×match → gráficos → cópia | `--year` | `runs/<ano>/` |
| `create_charts.py` | Gera gráficos comparativos das execuções | `[--base]`, `[--stem]`, `--years`, `--output`, `--timestamp` | `chart_status[_<ts>].png`, `chart_sources[_<ts>].png`, `chart_time[_<ts>].png` |
| `terms_matcher.py` | Detecta termos por campo e gera CSV auditável | `--base`, `--years`, `--terms`, `--mode`, `--match-mode` | `terms_<ts>.csv` + `terms_<ts>.log` + `terms_<ts>_stats.json` |
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
- Pasta de runs: `runs/<ano>/`

## Comportamento do scielo_search.py

- **`--show-params [ARQ]`:** sem `ARQ`, lê o `_params.json` mais recente no diretório atual via glob; com `ARQ`, lê o arquivo indicado (relativo ou absoluto) — independente de `--terms`/`--years`
- **Truncamento:** `$` adicionado automaticamente ao final de cada termo (ex: `avalia` → `avalia$`); desativar com `--no-truncate`
- **`--list-collections`:** lista as 36 coleções SciELO e sai

## Comportamento do run_pipeline.py (v2.0)

**Etapas do pipeline** (9 no total por ano):
1. Busca (`scielo_search.py`)
2. Scraping api+html (`scielo_scraper.py`)
3. Scraping api (`scielo_scraper.py --only-api`)
4. Scraping html (`scielo_scraper.py --only-html`)
5. Análise de discrepância (compara as 3 estratégias)
6. Terms matcher para api+html (`terms_matcher.py --mode api+html`)
7. Terms matcher para api (`terms_matcher.py --mode api`)
8. Terms matcher para html (`terms_matcher.py --mode html`)
9. Gráficos comparativos (`create_charts.py --stem <sc_ts> --output runs/<ano>/`)
   - No `--per-year` com múltiplos anos: etapa extra ao final — `create_charts.py --base runs/ --output runs/` (chart agregado comparando todos os anos)

**Comportamento padrão** (zero flags adicionais):
- `--terms avalia educa` — termos de busca e detecção
- `--terms-fields titulo keywords` — campos verificados pelo matcher
- `--terms-match-mode all` — todos os termos devem estar presentes
- `--collection scl` — coleção SciELO Brasil
- Destino: `runs/<ano>/`

**Flags de controle:**
- **`--no-resume` implícito:** scraper sempre chamado com `--no-resume`; cada estratégia começa do zero
- **`--skip-search`:** reutiliza CSV `sc_*` mais recente
- **`--skip-scrape`:** reutiliza pastas existentes — não reexecuta o scraper
- **`--skip-analysis`:** pula análise de discrepância
- **`--skip-match`:** pula as 3 invocações do terms_matcher
- **`--skip-charts`:** pula geração de gráficos
- **`--dry-run`:** mostra os comandos sem executar, inclusive a limpeza que seria feita
- **`--stats-report [DIR]`:** gera relatório Markdown consolidado de todos os `stats.json` em `runs/` (ou `DIR`); funciona sem `--year` — modo standalone
- **`--per-year`:** executa o pipeline para cada ano, com barra de progresso global e ETA estimado por histórico

**Saída em `runs/<ano>/`:**
- `sc_<ts>.csv` + `sc_<ts>_params.json`
- 3 pastas de scraping (cada uma contém `resultado.csv`, `stats.json`, `terms_<ts>.*`)
- `ANALISE_DISCREPANCIA_<ano>.md`
- `chart_status.png`, `chart_sources.png`, `chart_time.png`
- `pipeline_stats.json` — resumo completo da execução (versão, termos, campos, etapas, stats por estratégia)

**Arquivamento automático (nunca apaga):** após copiar tudo para `runs/<ano>/`, o pipeline faz uma varredura de segurança no diretório raiz procurando qualquer arquivo/pasta do run atual (identificados pelo stem do CSV). Se encontrar algo:
- Se já existe em `runs/<ano>/` → remove o original do raiz (era cópia redundante)
- Se **não** existe em `runs/<ano>/` → **move** para `runs/<ano>/` e loga aviso (indica que a etapa não gerou no lugar certo)

Gráficos e terms são gerados diretamente em `runs/<ano>/` (sem passar pelo raiz), então a varredura de segurança normalmente não encontra nada.

**`create_charts.py --stem`:** o pipeline passa `--stem <sc_ts>` para busca determinística das pastas do run correto, evitando ambiguidade quando múltiplos runs coexistem no diretório (ex: durante `--per-year`).

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
uv pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli matplotlib
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
