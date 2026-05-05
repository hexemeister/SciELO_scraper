# SciELO Scraper

Extrai **título**, **resumo** e **palavras-chave em português** de artigos SciELO a partir de um CSV com PIDs (identificadores SciELO).

Desenvolvido para o projeto **e-Aval** — *Estado da Arte da Avaliação* — do grupo de pesquisa do [Mestrado Profissional em Avaliação da Fundação Cesgranrio](https://eavaleducacao1.websiteseguro.com/). O banco de dados público recebe os artigos curados após o processo de filtragem e verificação humana realizado com este conjunto de ferramentas.

- 🌐 Banco de dados: https://eavaleducacao1.websiteseguro.com/
- 💻 Repositório do banco de dados: https://github.com/hexemeister/eaval
- 📧 Contato: eaval.bd@gmail.com

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

| Opção                | Default                       | Descrição                                                  |
| -------------------- | ----------------------------- | ---------------------------------------------------------- |
| `--output-dir DIR`   | `<csv>_s_<timestamp>_<modo>/` | Pasta de saída                                             |
| `--delay SEG`        | `1.5`                         | Delay mínimo entre requests                                |
| `--jitter SEG`       | `0.5`                         | Variação aleatória máxima do delay                         |
| `--retries N`        | `3`                           | Tentativas em erro transitório                             |
| `--timeout SEG`      | `20`                          | Timeout HTTP em segundos                                   |
| `--workers N`        | `1`                           | Threads paralelas (máx: 4)                                 |
| `--resume`           | —                             | Retomar execução anterior                                  |
| `--no-resume`        | —                             | Ignorar resultados anteriores                              |
| `--only-api`         | —                             | Usar apenas ArticleMeta API                                |
| `--only-html`        | —                             | Usar apenas scraping HTML                                  |
| `--stats-report`     | —                             | Imprimir relatório de uma execução anterior                |
| `--list-collections` | —                             | Listar coleções SciELO disponíveis                         |
| `--log-level LEVEL`  | `INFO`                        | `DEBUG` / `INFO` / `WARNING` / `ERROR`                     |
| `--collection COD`   | `scl`                         | Coleção SciELO (ex: `scl`=Brasil, `arg`=Argentina)         |
| `--checkpoint N`     | `25`                          | Salvar CSV a cada N artigos (0=só no final, 1=cada artigo) |
| `--version`          | —                             | Mostrar versão                                             |
| `-h`, `--help`, `-?` | —                             | Mostrar ajuda                                              |

## scielo_search.py — Busca de artigos

Script para pesquisar artigos no SciELO Search e baixar os resultados como CSV, pronto para alimentar o `scielo_scraper.py`.

### Uso básico

```bash
python scielo_search.py --terms avalia educa --years 2022-2025
```

Gera dois arquivos no diretório atual:

- `sc_<timestamp>.csv` — lista de artigos com PIDs e metadados
- `sc_<timestamp>_params.json` — parâmetros completos da busca, incluindo `versao_searcher` (a partir de v1.3)

### Opções

| Opção                      | Descrição                                                        |
| -------------------------- | ---------------------------------------------------------------- |
| `--terms TERMO...`         | Termos de busca (um ou mais)                                     |
| `--years ANO` ou `ANO-ANO` | Ano ou intervalo de anos de publicação                           |
| `--collection COD`         | Coleção SciELO (default: `scl` = Brasil)                         |
| `--fields CAMPO...`        | Campos onde pesquisar os termos                                  |
| `--no-truncate`            | Desativar truncamento automático de termos                       |
| `--show-params [ARQ]`      | Exibir parâmetros da última busca (ou de `ARQ` explícito) e sair |
| `--output ARQUIVO`         | Nome do arquivo de saída (default: `sc_<timestamp>.csv`)         |
| `-h`, `--help`, `-?`       | Mostrar ajuda                                                    |

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

| Arquivo         | Descrição                  |
| --------------- | -------------------------- |
| `resultado.csv` | CSV com os dados extraídos |
| `scraper.log`   | Log completo da execução   |
| `stats.json`    | Estatísticas em JSON       |

### Colunas do resultado.csv

Mantém todas as colunas do CSV de entrada e adiciona:

| Coluna              | Descrição                                                                                |
| ------------------- | ---------------------------------------------------------------------------------------- |
| `PID_limpo`         | PID normalizado                                                                          |
| `URL_PT`            | URL da versão em português                                                               |
| `Titulo_PT`         | Título em português                                                                      |
| `Resumo_PT`         | Resumo em português                                                                      |
| `Palavras_Chave_PT` | Palavras-chave em português (separadas por `;`)                                          |
| `status`            | `ok_completo` / `ok_parcial` / `nada_encontrado` / `erro_extracao` / `erro_pid_invalido` |
| `fonte_extracao`    | Fonte(s) usada(s) para cada campo                                                        |
| `url_acedida`       | URL(s) acessada(s) durante o scraping                                                    |

## Comparativo de estratégias

Resultados em cinco anos de coleta (SciELO Brasil, termos: *avalia$*, *educa$*):

| Ano  | n   | Estratégia        | ok_completo | ok_parcial | erro     | Tempo       |
| ---- | --- | ----------------- | ----------- | ---------- | -------- | ----------- |
| 2021 | 561 | `--only-api`      | 99.1%       | 0.9%       | 0.0%     | ~25 min     |
| 2021 | 561 | `--only-html`     | 96.8%       | 0.2%       | 3.0%     | ~33 min     |
| 2021 | 561 | padrão (api+html) | **99.5%**   | 0.5%       | **0.0%** | **~28 min** |
| 2022 | 564 | `--only-api`      | 98.6%       | 1.1%       | 0.4%     | ~25 min     |
| 2022 | 564 | `--only-html`     | 98.9%       | 0.2%       | 0.9%     | ~50 min     |
| 2022 | 564 | padrão (api+html) | **99.8%**   | 0.2%       | **0.0%** | **~26 min** |
| 2023 | 468 | `--only-api`      | 98.9%       | 1.1%       | 0.0%     | ~24 min     |
| 2023 | 468 | `--only-html`     | 98.3%       | 0.6%       | 1.1%     | ~57 min     |
| 2023 | 468 | padrão (api+html) | **99.4%**   | 0.6%       | **0.0%** | **~24 min** |
| 2024 | 553 | `--only-api`      | 98.9%       | 0.9%       | 0.2%     | ~27 min     |
| 2024 | 553 | `--only-html`     | 98.2%       | 0.2%       | 1.6%     | ~71 min     |
| 2024 | 553 | padrão (api+html) | **99.6%**   | 0.2%       | **0.2%** | **~27 min** |
| 2025 | 603 | `--only-api`      | 99.2%       | 0.8%       | 0.0%     | ~28 min     |
| 2025 | 603 | `--only-html`     | 98.2%       | 0.5%       | 1.3%     | ~57 min     |
| 2025 | 603 | padrão (api+html) | **99.7%**   | 0.3%       | **0.0%** | **~32 min** |

A estratégia padrão é consistentemente a mais eficiente: usa a ArticleMeta API para ~99% dos artigos e aciona o HTML apenas como fallback, mantendo cobertura máxima com tempo equivalente ao modo apenas-api — e significativamente inferior ao modo apenas-html (que levou até 71 min em 2024).

## Coleções disponíveis

```bash
python scielo_scraper.py --list-collections
```

Exibe as 36 coleções SciELO com código, domínio e quantidade de artigos. Use `--collection COD` para selecionar (default: `scl` = Brasil).

## Dependências

| Pacote                    | Uso                                                     |
| ------------------------- | ------------------------------------------------------- |
| `requests`                | HTTP                                                    |
| `beautifulsoup4` + `lxml` | Parsing HTML                                            |
| `pandas`                  | Leitura/escrita CSV                                     |
| `tqdm`                    | Barra de progresso                                      |
| `wakepy`                  | Impede sleep do sistema durante execução longa          |
| `brotli`                  | Descompressão Brotli (obrigatório para o CDN do SciELO) |
| `matplotlib`              | Gráficos (`process_charts.py`, `results_report.py`)     |
| `matplotlib-venn`         | Diagramas de Venn (`results_report.py`)                 |
| `upsetplot`               | UpSet plots para ≥4 termos (`results_report.py`)        |
| `wordcloud`               | Nuvem de palavras (`scielo_wordcloud.py`)               |
| `nltk`                    | Stopwords multilíngues (`scielo_wordcloud.py`)          |
| `pillow`                  | Máscara/shape da wordcloud (`scielo_wordcloud.py`)      |
| `reportlab`               | Geração de PDF preenchível (`prisma_workflow.py`)       |

## Workflow típico

```bash
# 1. Buscar artigos
uv run python scielo_search.py --terms avalia educa --years 2022-2025
# → gera sc_20260411_143022.csv + sc_20260411_143022_params.json

# 2. Extrair metadados
uv run python scielo_scraper.py sc_20260411_143022.csv
# → gera sc_20260411_143022_s_20260411_150312_api+html/

# 3. (Opcional) Gerar gráficos comparativos de processo entre anos
uv run python process_charts.py
# → gera chart_status.png, chart_sources.png, chart_time.png

# 4. (Opcional) Detectar termos por campo e gerar CSV auditável
uv run python terms_matcher.py --years 2022 2023 2024 2025
# → gera terms_<ts>.csv com colunas booleanas por termo×campo + criterio_ok
```

## run_pipeline.py — Pipeline completo

Executa o fluxo completo em um único comando: busca → 3×scraping → análise de discrepância → detecção de termos → gráficos → relatório científico → nuvem de palavras → diagrama PRISMA → arquivamento em `runs/<ano>/`.

```bash
uv run python run_pipeline.py --year 2024                        # pipeline completo para 2024
uv run python run_pipeline.py --year 2021 2022 2023 2024 2025    # múltiplos anos (um destino)
uv run python run_pipeline.py --per-year --year 2021-2025        # um destino por ano
uv run python run_pipeline.py --year 2024 --dry-run              # simula sem executar
uv run python run_pipeline.py --year 2024 --skip-search          # reutiliza CSV existente
uv run python run_pipeline.py --year 2024 --skip-scrape          # reutiliza scraping existente
uv run python run_pipeline.py --year 2024 --skip-wordcloud --skip-prisma  # pula etapas finais
uv run python run_pipeline.py --year 2024 --prisma-lang pt       # PRISMA só em PT (default: pt+en)
uv run python run_pipeline.py --stats-report                     # relatório consolidado de runs/
uv run python run_pipeline.py --versions                         # versão de todos os scripts
uv run python run_pipeline.py --reset-working-tree --dry-run     # preview do que seria removido
uv run python run_pipeline.py --reset-working-tree               # reset completo (pede confirmação)
```

Gera em `runs/<ano>/`: CSV de busca, 3 pastas de scraping, análise de discrepância, gráficos de processo, relatório científico, wordclouds, PDFs PRISMA (pt + en), `pipeline_<ts>.log` e `pipeline_stats.json`.

## process_charts.py — Diagnóstico técnico do processo

Gera três gráficos PNG de diagnóstico técnico (como o scraping correu) a partir das pastas `runs/<ano>/`:

- **`chart_status.png`** — distribuição de status (`ok_completo`, `ok_parcial`, `erro_extracao`) por modo e ano
- **`chart_sources.png`** — fontes de extração no modo `api+html` por ano, com tabela de n exatos
- **`chart_time.png`** — tempo total de scraping por modo e ano
- **`chart_stats.json`** — metadados da execução (versão do script, timestamp, labels, idiomas, arquivos gerados)

```bash
uv run python process_charts.py                       # lê runs/ no diretório atual
uv run python process_charts.py --years 2022 2024     # apenas esses anos
uv run python process_charts.py --output graficos/    # pasta de saída personalizada
uv run python process_charts.py --lang en             # gráficos em inglês
uv run python process_charts.py --lang all            # gera em todos os idiomas
uv run python process_charts.py --version             # mostrar versão
uv run python process_charts.py -?                    # ajuda
```

## results_report.py — Artefatos científicos

Gera o arcabouço completo de artefatos científicos publication-ready a partir do `terms_*.csv` produzido pelo `terms_matcher.py`. Para o projeto e-Aval (Estado da Arte da Avaliação):

```bash
uv run python results_report.py                       # api+html, PT, todos os anos em runs/
uv run python results_report.py --years 2022 2024     # anos específicos
uv run python results_report.py --lang en             # artefatos em inglês
uv run python results_report.py --lang all            # todos os idiomas (PT + EN)
uv run python results_report.py --style grayscale     # estilo dos gráficos (default: default)
uv run python results_report.py --list-styles         # listar estilos matplotlib disponíveis
uv run python results_report.py --colormap plasma     # colormap do heatmap (default: viridis)
uv run python results_report.py --list-colormaps      # listar colormaps disponíveis
uv run python results_report.py -?                    # ajuda
```

Artefatos gerados em `results_<stem>/`: gráficos (funil, tendência, heatmap de termos, periódicos, cobertura de campos, diagrama Venn/UpSet), tabelas CSV, texto Markdown publication-ready (`results_text_pt.md` / `results_text_en.md`) com Metodologia enriquecida, Nota técnica com URL da busca, e descrição textual de cada figura — e JSON de metadados.

## scielo_wordcloud.py — Nuvem de palavras

Gera nuvens de palavras a partir do `resultado.csv` do scraping. Suporta filtragem por corpus, stopwords por idioma via NLTK, stopwords de domínio acadêmico e máscara/shape personalizada.

```bash
uv run python scielo_wordcloud.py sc_ts_s_ts_api+html/resultado.csv   # title + keywords, corpus criterio_ok
uv run python scielo_wordcloud.py resultado.csv --field abstract        # apenas resumos
uv run python scielo_wordcloud.py resultado.csv --corpus all            # todos os artigos extraídos
uv run python scielo_wordcloud.py resultado.csv --lang en               # stopwords em inglês
uv run python scielo_wordcloud.py resultado.csv --stopwords extras.txt  # stopwords adicionais
uv run python scielo_wordcloud.py resultado.csv --mask forma.png        # shape personalizada
uv run python scielo_wordcloud.py resultado.csv --colormap plasma        # colormap
uv run python scielo_wordcloud.py resultado.csv --max-words 100         # limitar palavras
uv run python scielo_wordcloud.py resultado.csv --output-dir graficos/  # pasta de saída
uv run python scielo_wordcloud.py resultado.csv --dry-run               # sem gerar arquivos
uv run python scielo_wordcloud.py --list-langs                          # listar idiomas NLTK
uv run python scielo_wordcloud.py --list-colormaps                      # listar colormaps
uv run python scielo_wordcloud.py -?                                    # ajuda
```

Gera `wordcloud_{campo}_{lang}_{ts}.png` por campo e `wordcloud_stats_{ts}.json` com metadados.

## prisma_workflow.py — Diagrama PRISMA 2020

Gera um PDF A4 preenchível com o diagrama de fluxo PRISMA 2020. Os campos da fase de Identificação são auto-preenchidos a partir do `results_report.json` (gerado pelo `results_report.py`). Os campos das fases de Triagem e Inclusão ficam como campos editáveis AcroForm para preenchimento humano após curadoria.

```bash
# Geração básica (campos humanos ficam em branco para preencher no PDF)
uv run python prisma_workflow.py runs/2025/results_*/results_report.json

# Com campos humanos passados pela linha de comando
uv run python prisma_workflow.py results_report.json --included 80 --excluded-screening 523

# Modo interativo (terminal pergunta os valores)
uv run python prisma_workflow.py results_report.json -i

# Campos humanos de um arquivo JSON ou CSV
uv run python prisma_workflow.py results_report.json --human-data human_fields.json

# Em inglês
uv run python prisma_workflow.py results_report.json --lang en

# Pasta de saída específica
uv run python prisma_workflow.py results_report.json --output-dir pdfs/

# Simular sem gerar PDF
uv run python prisma_workflow.py results_report.json --dry-run

# Exportar template JSON do layout (para customização do diagrama)
uv run python prisma_workflow.py --export-template
uv run python prisma_workflow.py --export-template meu_layout.json
```

Gera `prisma_<stem>_<lang>_<ts>.pdf` — PDF abrível em qualquer leitor de PDF; campos editáveis preenchíveis diretamente no Acrobat Reader, Foxit, Edge, etc.

> **Layout embutido:** o script é auto-suficiente — o layout PRISMA 2020 está embutido internamente. O arquivo `assets/PRISMAdiagram.json` é **opcional**: se presente, sobrepõe o layout padrão. Use `--export-template` para exportar o template e customizá-lo.

> **Nota PRISMA:** o pipeline cobre apenas a fase de Identificação. As fases de Triagem e Inclusão requerem curadoria humana após o processamento automático.

## terms_matcher.py — Detecção de termos por campo

Consolida os `resultado.csv` de um ou mais anos e detecta termos de busca em cada campo PT, gerando colunas booleanas auditáveis em planilha eletrônica:

| Coluna                                                   | Descrição                                                      |
| -------------------------------------------------------- | -------------------------------------------------------------- |
| `n_palavras_titulo`                                      | Nº de palavras no Titulo_PT                                    |
| `n_palavras_resumo`                                      | Nº de palavras no Resumo_PT                                    |
| `n_keywords_pt`                                          | Nº de keywords separadas por ";"                               |
| `<termo>_titulo` / `<termo>_resumo` / `<termo>_keywords` | Bool: termo encontrado no campo                                |
| `criterio_ok`                                            | Bool: todos os termos em pelo menos um dos `--required-fields` |

> ⚠ **Atenção:** T termos × 3 campos = 3T colunas booleanas. Padrão (2 termos): 6 colunas.
> As colunas booleanas cobrem os 3 campos (titulo, resumo, keywords); o `criterio_ok` avalia apenas os `--required-fields` (padrão: titulo e keywords).

```bash
uv run python terms_matcher.py                             # todos os anos, termos padrão
uv run python terms_matcher.py --years 2022 2024           # apenas esses anos
uv run python terms_matcher.py --terms avalia educa        # termos personalizados
uv run python terms_matcher.py --required-fields titulo resumo keywords  # todos os campos
uv run python terms_matcher.py --stats-report              # relatório do último run
uv run python terms_matcher.py -?                          # ajuda
```

Gera também `terms_<ts>.log` e `terms_<ts>_stats.json` com estatísticas por ano e globais.

## Dicionário de dados e termos

### Termos e conceitos

| Termo              | Definição                                                                                                                                                                                                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PID**            | Identificador único SciELO. Formato: `S` + ISSN (com hífen) + ano (4 dígitos) + volume/fascículo (3 dígitos) + sequência (5 dígitos). Ex: `S1982-88372022000300013`. Total: 23 caracteres.                                                                                         |
| **ISSN**           | International Standard Serial Number — identificador de periódico. Embutido no PID nas posições 1–9 (ex: `1982-8837`).                                                                                                                                                             |
| **AoP**            | Ahead of Print — artigo publicado online antes de receber volume/fascículo definitivo. Identificado por `005` nas posições 14–16 do PID. Não indexado na ArticleMeta API; extraído apenas via HTML.                                                                                |
| **Coleção**        | Conjunto de periódicos de um país ou região na plataforma SciELO. Identificada por código de 3 letras (ex: `scl` = Brasil, `arg` = Argentina).                                                                                                                                     |
| **ISIS-JSON**      | Formato de resposta da ArticleMeta API, derivado do formato de banco de dados CDS/ISIS usado pelo SciELO internamente.                                                                                                                                                             |
| **Truncamento**    | Adição de `$` ao final de um termo de busca, para casar com variações morfológicas. Ex: `avalia$` casa com "avalia", "avaliação", "avaliativo", "avaliações". Ativo por padrão no `scielo_search.py` e removido automaticamente no `terms_matcher.py` para detecção por substring. |
| **criterio_ok**    | Coluna booleana do `terms_matcher.py`: `True` se todos os termos buscados forem encontrados em pelo menos um dos campos `--required-fields` (padrão: titulo ou keywords).                                                                                                          |
| **campo required** | Campo(s) considerados no cálculo de `criterio_ok`. Por padrão: `titulo` e `keywords` (basta que cada termo apareça em pelo menos um deles).                                                                                                                                        |

### Colunas do resultado.csv (scraper)

| Coluna              | Tipo | Origem      | Descrição                                             |
| ------------------- | ---- | ----------- | ----------------------------------------------------- |
| `ID`                | str  | CSV entrada | PID bruto conforme fornecido                          |
| `Title`             | str  | CSV entrada | Título conforme indexado no SciELO Search             |
| `Author(s)`         | str  | CSV entrada | Autores                                               |
| `Source`            | str  | CSV entrada | Fonte/periódico                                       |
| `Journal`           | str  | CSV entrada | Periódico                                             |
| `Language(s)`       | str  | CSV entrada | Idioma(s) do artigo                                   |
| `Publication year`  | int  | CSV entrada | Ano de publicação                                     |
| `PID_limpo`         | str  | scraper     | PID normalizado (sufixos removidos, validado)         |
| `URL_PT`            | str  | scraper     | URL da versão em português consultada                 |
| `Titulo_PT`         | str  | scraper     | Título em português extraído                          |
| `Resumo_PT`         | str  | scraper     | Resumo em português extraído                          |
| `Palavras_Chave_PT` | str  | scraper     | Palavras-chave em português, separadas por `;`        |
| `status`            | str  | scraper     | Status da extração (ver tabela abaixo)                |
| `fonte_extracao`    | str  | scraper     | Fonte(s) usadas por campo (ex: `articlemeta_isis[T]`) |
| `url_acedida`       | str  | scraper     | URL(s) acessadas durante o scraping                   |

### Colunas adicionadas pelo terms_matcher.py

| Coluna              | Tipo | Descrição                                                          |
| ------------------- | ---- | ------------------------------------------------------------------ |
| `n_palavras_titulo` | int  | Nº de palavras em Titulo_PT                                        |
| `n_palavras_resumo` | int  | Nº de palavras em Resumo_PT                                        |
| `n_keywords_pt`     | int  | Nº de keywords em Palavras_Chave_PT (separador `;`)                |
| `<termo>_titulo`    | bool | Termo detectado em Titulo_PT (case-insensitive, substring)         |
| `<termo>_resumo`    | bool | Termo detectado em Resumo_PT (case-insensitive, substring)         |
| `<termo>_keywords`  | bool | Termo detectado em Palavras_Chave_PT (case-insensitive, substring) |
| `criterio_ok`       | bool | Todos os termos presentes em ≥1 campo required                     |

### Status de extração

| Status              | Significado                                 |
| ------------------- | ------------------------------------------- |
| `ok_completo`       | Título + resumo + palavras-chave extraídos  |
| `ok_parcial`        | Pelo menos um campo extraído, mas não todos |
| `nada_encontrado`   | Página acessada, nenhum dado encontrado     |
| `erro_extracao`     | Falha de acesso (ex: HTTP 404, timeout)     |
| `erro_pid_invalido` | PID fora do padrão esperado                 |

### Fontes de extração (`fonte_extracao`)

| Valor                                       | Significado                            |
| ------------------------------------------- | -------------------------------------- |
| `articlemeta_isis[T]`                       | Título via ArticleMeta API (ISIS-JSON) |
| `articlemeta_isis[R]`                       | Resumo via ArticleMeta API             |
| `articlemeta_isis[K]`                       | Palavras-chave via ArticleMeta API     |
| `Titulo_PT←pag1_meta_tags`                  | Título via meta tags da URL legacy     |
| `Titulo_PT←pag1_html_body`                  | Título via corpo HTML da URL legacy    |
| `Resumo_PT←pag_pt_meta_tags`                | Resumo via meta tags da versão PT      |
| `Palavras_Chave_PT←pag_aop_ogurl_meta_tags` | Keywords via og:url (AoP)              |
