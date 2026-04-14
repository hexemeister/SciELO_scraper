# SciELO Scraper

Extrai **título**, **resumo** e **palavras-chave em português** de artigos SciELO a partir de um CSV com PIDs (identificadores SciELO).

## Como funciona

O script usa duas fontes de dados por ordem de prioridade:

1. **ArticleMeta REST API** (`articlemeta.scielo.org`) — extração direta e estruturada via ISIS-JSON. Rápida e confiável para a maioria dos artigos.
2. **Fallback HTML** (`scielo.br`) — ativado automaticamente quando a API não retorna dados completos. Estratégia multi-etapa:
   - Acessa a URL legacy e segue redirects automáticos para a URL canônica
   - Extrai meta tags (`citation_*`, `og:*`) e corpo HTML (`h1.article-title`, `div[data-anchor=Resumo]`)
   - Se a língua da página não for PT, segue o link "Texto (Português)"
   - Para artigos Ahead of Print (AoP), tenta a `og:url` da página

Quando a API retorna dados parciais (ex: só resumo), o fallback HTML é ativado para preencher os campos restantes.

## Requisitos

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) (recomendado) ou pip

## Instalação

```bash
# Com uv (recomendado)
uv pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli

# Com pip
pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli
```

> **Atenção:** o pacote `brotli` é obrigatório. O CDN do SciELO serve páginas com compressão Brotli (`Content-Encoding: br`); sem ele o body chega corrompido e o scraping falha silenciosamente.

## Uso básico

```bash
python scielo_scraper.py lista.csv
```

## Opções

| Opção | Default | Descrição |
|---|---|---|
| `--output-dir DIR` | `<csv>_s_<timestamp>_<modo>/` | Pasta de saída |
| `--delay SEG` | `1.5` | Delay mínimo entre requests |
| `--jitter SEG` | `0.5` | Variação aleatória máxima do delay |
| `--retries N` | `3` | Tentativas em erro transitório |
| `--timeout SEG` | `20` | Timeout HTTP em segundos |
| `--workers N` | `1` | Threads paralelas (máx: 4) |
| `--resume` | — | Retomar execução anterior |
| `--no-resume` | — | Ignorar resultados anteriores |
| `--only-api` | — | Usar apenas ArticleMeta API |
| `--only-html` | — | Usar apenas scraping HTML |
| `--stats-report` | — | Imprimir relatório de uma execução anterior |
| `--list-collections` | — | Listar coleções SciELO disponíveis |
| `--log-level LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `--collection COD` | `scl` | Coleção SciELO (ex: `scl`=Brasil, `arg`=Argentina) |
| `--checkpoint N` | `25` | Salvar CSV a cada N artigos (0=só no final, 1=cada artigo) |
| `--version` | — | Mostrar versão |
| `-h`, `--help`, `-?` | — | Mostrar ajuda |

## scielo_search.py — Busca de artigos

Script para pesquisar artigos no SciELO Search e baixar os resultados como CSV, pronto para alimentar o `scielo_scraper.py`.

### Uso básico

```bash
python scielo_search.py --terms avalia educa --years 2022-2025
```

Gera dois arquivos no diretório atual:

- `sc_<timestamp>.csv` — lista de artigos com PIDs e metadados
- `sc_<timestamp>_params.json` — parâmetros completos da busca usados

### Opções

| Opção | Descrição |
|---|---|
| `--terms TERMO...` | Termos de busca (um ou mais) |
| `--years ANO` ou `ANO-ANO` | Ano ou intervalo de anos de publicação |
| `--collection COD` | Coleção SciELO (default: `scl` = Brasil) |
| `--fields CAMPO...` | Campos onde pesquisar os termos |
| `--no-truncate` | Desativar truncamento automático de termos |
| `--show-params [ARQ]` | Exibir parâmetros da última busca (ou de `ARQ` explícito) e sair |
| `--output ARQUIVO` | Nome do arquivo de saída (default: `sc_<timestamp>.csv`) |
| `-h`, `--help`, `-?` | Mostrar ajuda |

> O CSV gerado contém uma coluna `ID` com os PIDs SciELO e é diretamente compatível com o `scielo_scraper.py`.

## Formato do CSV de entrada

O CSV deve ter uma coluna `ID` com os PIDs SciELO:

```
ID,Title,Author(s),...
S1982-88372022000300013,Título do artigo,...
S1984-92302022000400750,Outro artigo,...
```

O PID deve seguir o padrão `[A-Z]\d{4}-\d{3}[\dA-Z]\d{13}` (ex: `S1982-88372022000300013`). Sufixos como `-scl` ou `-oai` são removidos automaticamente.

## Arquivos gerados

Cada execução cria uma pasta `<nome_csv>_s_<timestamp>_<modo>/` com:

| Arquivo | Descrição |
|---|---|
| `resultado.csv` | CSV com os dados extraídos |
| `scraper.log` | Log completo da execução |
| `stats.json` | Estatísticas em JSON |

### Colunas do resultado.csv

Mantém todas as colunas do CSV de entrada e adiciona:

| Coluna | Descrição |
|---|---|
| `PID_limpo` | PID normalizado |
| `URL_PT` | URL da versão em português |
| `Titulo_PT` | Título em português |
| `Resumo_PT` | Resumo em português |
| `Palavras_Chave_PT` | Palavras-chave em português (separadas por `;`) |
| `status` | `ok_completo` / `ok_parcial` / `nada_encontrado` / `erro_extracao` / `erro_pid_invalido` |
| `fonte_extracao` | Fonte(s) usada(s) para cada campo |
| `url_acedida` | URL(s) acessada(s) durante o scraping |

## Comparativo de estratégias

Resultados em quatro anos de coleta (SciELO Brasil, termos: *avalia$*, *educa$*):

| Ano | n | Estratégia | ok_completo | ok_parcial | erro | Tempo |
|---|---|---|---|---|---|---|
| 2022 | 564 | `--only-api` | 98.6% | 1.1% | 0.4% | ~26 min |
| 2022 | 564 | `--only-html` | 99.5% | 0.2% | 0.4% | ~37 min |
| 2022 | 564 | padrão (api+html) | **99.8%** | 0.2% | **0.0%** | **~27 min** |
| 2023 | 468 | `--only-api` | 98.9% | 1.1% | 0.0% | ~21 min |
| 2023 | 468 | `--only-html` | 99.1% | 0.6% | 0.2% | ~39 min |
| 2023 | 468 | padrão (api+html) | **99.4%** | 0.6% | **0.0%** | **~22 min** |
| 2024 | 553 | `--only-api` | 98.9% | 0.9% | 0.2% | ~25 min |
| 2024 | 553 | `--only-html` | 99.3% | 0.2% | 0.5% | ~35 min |
| 2024 | 553 | padrão (api+html) | **99.6%** | 0.2% | **0.2%** | **~26 min** |
| 2025 | 603 | `--only-api` | 99.2% | 0.8% | 0.0% | ~28 min |
| 2025 | 603 | `--only-html` | 99.0% | 0.5% | 0.5% | ~43 min |
| 2025 | 603 | padrão (api+html) | **99.8%** | 0.2% | **0.0%** | **~28 min** |

A estratégia padrão é consistentemente a mais eficiente: usa a ArticleMeta API para ~99% dos artigos e aciona o HTML apenas como fallback, mantendo cobertura máxima com tempo equivalente ao modo apenas-api.

## Coleções disponíveis

```bash
python scielo_scraper.py --list-collections
```

Exibe as 36 coleções SciELO com código, domínio e quantidade de artigos. Use `--collection COD` para selecionar (default: `scl` = Brasil).

## Dependências

| Pacote | Uso |
|---|---|
| `requests` | HTTP |
| `beautifulsoup4` + `lxml` | Parsing HTML |
| `pandas` | Leitura/escrita CSV |
| `tqdm` | Barra de progresso |
| `wakepy` | Impede sleep do sistema durante execução longa |
| `brotli` | Descompressão Brotli (obrigatório para o CDN do SciELO) |

## Workflow típico

```bash
# 1. Buscar artigos
uv run python scielo_search.py --terms avalia educa --years 2022-2025
# → gera sc_20260411_143022.csv + sc_20260411_143022_params.json

# 2. Extrair metadados
uv run python scielo_scraper.py sc_20260411_143022.csv
# → gera sc_20260411_143022_s_20260411_150312_api+html/

# 3. (Opcional) Gerar gráficos comparativos entre anos
uv run python gerar_graficos.py
# → gera grafico_status.png, grafico_fontes.png, grafico_tempo.png

# 4. (Opcional) Criar CSV enriquecido para análise
uv run python enriquecedor_csv.py --years 2022 2023 2024 2025
# → gera enriquecido_<ts>.csv com colunas derivadas (ISSN, is_aop, n_keywords, etc.)
```

## gerar_graficos.py — Gráficos comparativos

Gera três gráficos PNG a partir das pastas `exemplos/<ano>/` produzidas pelo `teste_pipeline.py`:

- **`grafico_status.png`** — distribuição de status (`ok_completo`, `ok_parcial`, `erro_extracao`) por modo e ano
- **`grafico_fontes.png`** — fontes de extração no modo `api+html` por ano, com tabela de n exatos
- **`grafico_tempo.png`** — tempo total de scraping por modo e ano

```bash
uv run python gerar_graficos.py                      # lê exemplos/ no diretório atual
uv run python gerar_graficos.py --years 2022 2024    # apenas esses anos
uv run python gerar_graficos.py --output graficos/   # pasta de saída personalizada
uv run python gerar_graficos.py -?                   # ajuda
```

## enriquecedor_csv.py — CSV enriquecido para análise

Consolida os `resultado.csv` de um ou mais anos em um único arquivo CSV, adicionando colunas derivadas sem fazer nenhuma requisição à internet:

| Coluna nova | Descrição |
|---|---|
| `ano_coleta` | Ano da pasta de exemplos |
| `modo_extracao` | Modo usado na extração |
| `tem_titulo_pt` / `tem_resumo_pt` / `tem_keywords_pt` | Presença de cada campo em PT |
| `n_keywords_pt` | Nº de keywords (separadas por ";") |
| `n_palavras_resumo` | Nº de palavras no resumo PT |
| `fonte_simplificada` | Categoria legível da fonte de extração |
| `termo_detectado` | Termos encontrados no título/resumo PT |
| `is_aop` | Artigo ahead-of-print |
| `ISSN` | ISSN extraído do PID (XXXX-YYYY) |
| `ano_publicacao_num` | Ano de publicação como int |

```bash
uv run python enriquecedor_csv.py                          # todos os anos, termos padrão
uv run python enriquecedor_csv.py --years 2022 2024        # apenas esses anos
uv run python enriquecedor_csv.py --terms avalia educa     # termos personalizados
uv run python enriquecedor_csv.py --output analise.csv     # nome de saída
uv run python enriquecedor_csv.py -?                       # ajuda
```

Gera também `enriquecedor_<ts>.log` e `enriquecedor_<ts>_stats.json` com estatísticas por ano e globais.
