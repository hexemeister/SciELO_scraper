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
| `--output-dir DIR` | `<csv>_new_<timestamp>/` | Pasta de saída |
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
| `--version` | — | Mostrar versão |

## Formato do CSV de entrada

O CSV deve ter uma coluna `ID` com os PIDs SciELO:

```
ID,Title,Author(s),...
S1982-88372022000300013,Título do artigo,...
S1984-92302022000400750,Outro artigo,...
```

O PID deve seguir o padrão `[A-Z]\d{4}-\d{3}[\dA-Z]\d{13}` (ex: `S1982-88372022000300013`). Sufixos como `-scl` ou `-oai` são removidos automaticamente.

## Arquivos gerados

Cada execução cria uma pasta `<nome_csv>_new_<timestamp>/` com:

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

Resultado em 564 artigos do SciELO Brasil (2022):

| Estratégia | ok_completo | ok_parcial | erro | Tempo |
|---|---|---|---|---|
| `--only-api` | 93.8% | 1.1% | 5.1% | ~26 min |
| `--only-html` | 99.5% | 0.2% | 0.4% | ~36 min |
| padrão (api+html) | **99.6%** | 0.2% | **0.2%** | **~26 min** |

A estratégia padrão é a mais eficiente: usa a API para ~94% dos artigos (rápido) e aciona o HTML apenas quando necessário.

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
