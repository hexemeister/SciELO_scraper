# SciELO Scraper — Contexto do Projeto

## Scripts principais

| Script | Função | Entrada | Saída |
|---|---|---|---|
| `scielo_search.py` | Busca artigos no SciELO Search | `--terms`, `--years`, `--collection` | `sc_<ts>.csv` + `sc_<ts>_params.json` |
| `scielo_scraper.py` | Extrai título/resumo/keywords PT | `sc_<ts>.csv` | `<stem>_s_<ts>_<modo>/` |
| `teste_pipeline.py` | Pipeline completo de teste | `--year` | `exemplos/<ano>/` |
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

## O que NÃO alterar sem contexto

- Lógica de extração HTML: funções `fetch_*`, `extract_*`, `is_article_page` em `scielo_scraper.py`
- Ordem de prioridade das fontes de extração
- Lógica de detecção AoP (`pid[14:17] == "005"`)
