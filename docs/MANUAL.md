# Manual do Usuário — SciELO Scraper v2.5

> **Projeto e-Aval — Estado da Arte da Avaliação**
> Grupo de pesquisa do Mestrado Profissional em Avaliação da Fundação Cesgranrio.
> Este conjunto de ferramentas apoia o processo anual de coleta, extração, filtragem e análise
> da produção científica em avaliação educacional indexada no SciELO Brasil.
> 
> - 🌐 Banco de dados público: https://eavaleducacao1.websiteseguro.com/
> - 💻 Repositório do banco de dados: https://github.com/hexemeister/eaval

## Sumário

- [Guia rápido de comandos](#guia-rápido-de-comandos)
- [0. Buscando artigos com scielo_search.py](#0-buscando-artigos-com-scielo_searchpy)
- [1. Instalação](#1-instalação)
- [2. Preparando o CSV de entrada](#2-preparando-o-csv-de-entrada)
- [3. Rodando o script](#3-rodando-o-script)
- [4. Entendendo os resultados](#4-entendendo-os-resultados)
- [5. Retomando uma execução interrompida](#5-retomando-uma-execução-interrompida)
- [6. Estratégias de extração](#6-estratégias-de-extração)
- [7. Outras coleções SciELO](#7-outras-coleções-scielo)
- [8. Ajustando velocidade e comportamento](#8-ajustando-velocidade-e-comportamento)
- [9. Verificando estatísticas de uma execução anterior](#9-verificando-estatísticas-de-uma-execução-anterior)
- [10. Gráficos de diagnóstico com process_charts.py](#10-gráficos-de-diagnóstico-com-process_chartspy)
- [11. Relatório consolidado com run_pipeline.py --stats-report](#11-relatório-consolidado-com-run_pipelinepy---stats-report)
- [12. Detecção de termos com terms_matcher.py](#12-detecção-de-termos-com-terms_matcherpy)
- [13. Artefatos científicos com results_report.py](#13-artefatos-científicos-com-results_reportpy)
- [14. Nuvem de palavras com scielo_wordcloud.py](#14-nuvem-de-palavras-com-scielo_wordcloudpy)
- [15. Diagrama PRISMA 2020 com prisma_workflow.py](#15-diagrama-prisma-2020-com-prisma_workflowpy)
- [16. Problemas comuns](#16-problemas-comuns)
- [17. Dicionário de dados e termos](#17-dicionário-de-dados-e-termos)

---

## Guia rápido de comandos

Use esta tabela para encontrar o comando certo sem precisar ler o manual inteiro.

### Pipeline completo (recomendado)

| Pergunta / Objetivo                                                                                      | Comando                                                               | O que cria                                                                                                                       | Onde salva                                 |
| -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Rodar tudo para um ano (default: termos `avalia educa`, coleção SciELO Brasil, campos `titulo keywords`) | `uv run python run_pipeline.py --year 2024`                           | CSV de busca, 3 pastas de scraping, análise, 3 arquivos de termos, 3 gráficos, relatório, wordcloud, PDFs PRISMA, `pipeline_stats.json`, `pipeline_<ts>.log` | `runs/2024/`                               |
| Rodar tudo para vários anos em sequência                                                                 | `uv run python run_pipeline.py --per-year --year 2022 2023 2024 2025` | Idem por ano + gráfico agregado de comparação entre anos                                                                                                    | `runs/<ano>/` cada um + `runs/chart_*.png` |
| Ver o que seria executado sem rodar                                                                      | `uv run python run_pipeline.py --year 2024 --dry-run`                 | Nada (apenas imprime os comandos)                                                                                                                            | —                                          |
| Reutilizar busca já feita (pular `scielo_search.py`)                                                     | `uv run python run_pipeline.py --year 2024 --skip-search`             | Idem sem nova busca                                                                                                                                          | `runs/2024/`                               |
| Reutilizar scraping já feito (pular scraper)                                                             | `uv run python run_pipeline.py --year 2024 --skip-scrape`             | Análise + termos + gráficos + relatório + wordcloud + prisma                                                                                                 | `runs/2024/`                               |
| Pular análise de discrepância                                                                            | `uv run python run_pipeline.py --year 2024 --skip-analysis`           | Busca + scraping + termos + gráficos + relatório + wordcloud + prisma                                                                                        | `runs/2024/`                               |
| Pular detecção de termos                                                                                 | `uv run python run_pipeline.py --year 2024 --skip-match`              | Busca + scraping + análise + gráficos                                                                                                                        | `runs/2024/`                               |
| Pular gráficos de processo                                                                               | `uv run python run_pipeline.py --year 2024 --skip-charts`             | Busca + scraping + análise + termos + relatório + wordcloud + prisma                                                                                         | `runs/2024/`                               |
| Pular relatório científico                                                                               | `uv run python run_pipeline.py --year 2024 --skip-report`             | Busca + scraping + análise + termos + gráficos                                                                                                               | `runs/2024/`                               |
| Pular wordcloud                                                                                          | `uv run python run_pipeline.py --year 2024 --skip-wordcloud`          | Idem sem wordcloud                                                                                                                                           | `runs/2024/`                               |
| Pular diagrama PRISMA                                                                                    | `uv run python run_pipeline.py --year 2024 --skip-prisma`             | Idem sem PDFs PRISMA                                                                                                                                         | `runs/2024/`                               |
| PRISMA apenas em português                                                                               | `uv run python run_pipeline.py --year 2024 --prisma-lang pt`          | Gera apenas `prisma_*_pt_*.pdf` (default: `both` = pt + en)                                                                                                 | `runs/2024/`                               |
| Ver relatório consolidado de todos os anos                                                               | `uv run python run_pipeline.py --stats-report`                        | Imprime Markdown no terminal                                                                                                                                 | —                                          |
| Salvar relatório em arquivo                                                                              | `uv run python run_pipeline.py --stats-report > stats.md`             | `stats.md`                                                                                                                                                   | Diretório atual                            |
| Ver versão de todos os scripts                                                                           | `uv run python run_pipeline.py --versions`                            | Imprime versões no terminal                                                                                                                                  | —                                          |
| Preview do que seria removido pelo reset                                                                 | `uv run python run_pipeline.py --reset-working-tree --dry-run`        | Imprime lista de itens a remover                                                                                                                             | —                                          |
| Resetar working tree (remove tudo gerado, preserva scripts e docs)                                      | `uv run python run_pipeline.py --reset-working-tree`                  | Pede confirmação y/N; remove runs/, exemplos/ e todos os arquivos gerados                                                                                   | —                                          |

### Busca de artigos

| Pergunta / Objetivo                                         | Comando                                                                                  | O que cria                            | Onde salva      |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------- | --------------- |
| Buscar artigos com termos e anos                            | `uv run python scielo_search.py --terms avalia educa --years 2022-2025`                  | `sc_<ts>.csv` + `sc_<ts>_params.json` | Diretório atual |
| Buscar em outra coleção (default: `scl` = Brasil)           | `uv run python scielo_search.py --terms avalia educa --years 2022-2025 --collection arg` | `sc_<ts>.csv` + `sc_<ts>_params.json` | Diretório atual |
| Buscar sem truncamento (default: truncamento ativo com `$`) | `uv run python scielo_search.py --terms avaliação educação --no-truncate`                | `sc_<ts>.csv` + `sc_<ts>_params.json` | Diretório atual |
| Ver parâmetros da última busca                              | `uv run python scielo_search.py --show-params`                                           | Nada (imprime no terminal)            | —               |
| Listar todas as coleções disponíveis                        | `uv run python scielo_search.py --list-collections`                                      | Nada (imprime no terminal)            | —               |

### Scraping de artigos

| Pergunta / Objetivo                                                         | Comando                                                      | O que cria                                   | Onde salva                   |
| --------------------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------- | ---------------------------- |
| Extrair título, resumo e keywords (default: api+html, checkpoint a cada 25) | `uv run python scielo_scraper.py sc_<ts>.csv`                | `resultado.csv`, `scraper.log`, `stats.json` | `sc_<ts>_s_<ts>_api+html/`   |
| Extrair apenas via API (mais rápido, sem AoPs)                              | `uv run python scielo_scraper.py sc_<ts>.csv --only-api`     | Idem                                         | `sc_<ts>_s_<ts>_api/`        |
| Extrair apenas via HTML (API fora do ar)                                    | `uv run python scielo_scraper.py sc_<ts>.csv --only-html`    | Idem                                         | `sc_<ts>_s_<ts>_html/`       |
| Retomar execução interrompida                                               | `uv run python scielo_scraper.py sc_<ts>.csv --resume`       | Nada novo — continua na pasta existente      | Pasta mais recente existente |
| Ver estatísticas de uma execução anterior                                   | `uv run python scielo_scraper.py sc_<ts>.csv --stats-report` | Nada (imprime no terminal)                   | —                            |

### Detecção de termos

| Pergunta / Objetivo                                                                                                 | Comando                                                                   | O que cria                                                  | Onde salva      |
| ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------- | --------------- |
| Detectar termos nos resultados (default: termos `avalia educa`, campos `titulo keywords`, todos os anos em `runs/`) | `uv run python terms_matcher.py`                                          | `terms_<ts>.csv`, `terms_<ts>.log`, `terms_<ts>_stats.json` | Diretório atual |
| Detectar termos em anos específicos                                                                                 | `uv run python terms_matcher.py --years 2022 2024`                        | Idem                                                        | Diretório atual |
| Alterar campos verificados em `criterio_ok` (default: `titulo keywords`)                                            | `uv run python terms_matcher.py --required-fields titulo resumo keywords` | Idem                                                        | Diretório atual |
| Exigir qualquer termo (default: todos os termos)                                                                    | `uv run python terms_matcher.py --match-mode any`                         | Idem                                                        | Diretório atual |
| Ver relatório do último run de termos                                                                               | `uv run python terms_matcher.py --stats-report`                           | Nada (imprime no terminal)                                  | —               |

### Gráficos de diagnóstico do processo

| Pergunta / Objetivo                       | Comando                                                       | O que cria                                                                    | Onde salva      |
| ----------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------- |
| Gerar gráficos a partir de `runs/`        | `uv run python process_charts.py`                             | `chart_status.png`, `chart_sources.png`, `chart_time.png`, `chart_stats.json` | Diretório atual |
| Gráficos de anos específicos              | `uv run python process_charts.py --years 2022 2024`           | Idem                                                                          | Diretório atual |
| Salvar gráficos em outra pasta            | `uv run python process_charts.py --output graficos/`          | Idem                                                                          | `graficos/`     |
| Gráfico agregado comparando todos os anos | `uv run python process_charts.py --base runs/ --output runs/` | `chart_status.png`, `chart_sources.png`, `chart_time.png`                     | `runs/`         |
| Gráficos em inglês                        | `uv run python process_charts.py --lang en`                   | `chart_status.png`, `chart_sources.png`, `chart_time.png`                     | Diretório atual |
| Gráficos em todos os idiomas              | `uv run python process_charts.py --lang all`                  | `chart_status_pt.png`, `chart_status_en.png`, ...                             | Diretório atual |
| Pular gráfico de fontes                   | `uv run python process_charts.py --no-sources`                | `chart_status.png`, `chart_time.png`                                          | Diretório atual |

### Artefatos científicos (resultados)

| Pergunta / Objetivo                                                        | Comando                                                                      | O que cria                                                      | Onde salva                                     |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------- |
| Gerar todos os artefatos (default: api+html, PT, todos os anos em `runs/`) | `uv run python results_report.py`                                            | 5 gráficos, 3 CSVs, `results_text_pt.md`, `results_report.json` | `results_<stem>/` ao lado da pasta de scraping |
| Consolidado multi-ano (série temporal completa)                            | `uv run python results_report.py --base runs/`                               | Idem, com funil por ano lado a lado e trend de evolução         | `runs/results_<ano_min>-<ano_max>/`            |
| Anos específicos                                                           | `uv run python results_report.py --years 2022 2024`                          | Idem                                                            | Idem                                           |
| Estratégia alternativa                                                     | `uv run python results_report.py --mode api`                                 | Idem                                                            | Idem                                           |
| Artefatos em inglês                                                        | `uv run python results_report.py --lang en`                                  | Idem com `results_text_en.md`                                   | Idem                                           |
| Ambos os idiomas                                                           | `uv run python results_report.py --lang all`                                 | PT + EN (`results_text_pt.md` + `results_text_en.md`)           | Idem                                           |
| Pasta de saída explícita                                                   | `uv run python results_report.py --output-dir relatorios/`                   | Idem                                                            | `relatorios/`                                  |
| Estilo de gráficos alternativo                                             | `uv run python results_report.py --style grayscale`                          | Idem (gráficos em escala de cinza)                              | Idem                                           |
| Colormap do heatmap alternativo                                            | `uv run python results_report.py --colormap plasma`                          | Idem (heatmap em plasma; default: viridis)                      | Idem                                           |
| Ver artefatos no terminal (sem regerar)                                    | `uv run python results_report.py --show-report runs/.../results_report.json` | Nada (imprime no terminal)                                      | —                                              |
| Gerar apenas artefatos selecionados                                        | `uv run python results_report.py --artifacts funnel,trend,heatmap`           | Apenas os artefatos listados                                    | `results_<stem>/`                              |
| Pular artefatos específicos                                                | `uv run python results_report.py --skip-artifacts text,report`               | Todos exceto os listados                                        | `results_<stem>/`                              |
| Listar todos os artefatos com descrição                                    | `uv run python results_report.py --help-artifacts`                           | Nada (imprime no terminal)                                      | —                                              |
| Descrição detalhada de um artefato                                         | `uv run python results_report.py --help-artifact results_funnel`             | Nada (imprime no terminal)                                      | —                                              |

### Nuvem de palavras

| Pergunta / Objetivo                                       | Comando                                                                  | O que cria                                                                                       | Onde salva      |
| --------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | --------------- |
| Auto-descoberta do CSV (sem parâmetro)                    | `uv run python scielo_wordcloud.py`                                      | `wordcloud_title_ptbr_<ts>.png`, `wordcloud_keywords_ptbr_<ts>.png`, `wordcloud_stats_<ts>.json` | Diretório atual |
| Gerar wordcloud de title + keywords (padrão, criterio_ok) | `uv run python scielo_wordcloud.py resultado.csv`                        | Idem                                                                                             | Diretório atual |
| Apenas um campo                                           | `uv run python scielo_wordcloud.py resultado.csv --field abstract`       | `wordcloud_abstract_ptbr_<ts>.png`, `wordcloud_stats_<ts>.json`                                  | Diretório atual |
| Todos os artigos extraídos (não só criterio_ok)           | `uv run python scielo_wordcloud.py resultado.csv --corpus all`           | Idem                                                                                             | Idem            |
| Shape personalizada                                       | `uv run python scielo_wordcloud.py resultado.csv --mask forma.png`       | Idem (recortado na forma)                                                                        | Idem            |
| Pasta de saída específica                                 | `uv run python scielo_wordcloud.py resultado.csv --output-dir graficos/` | Idem                                                                                             | `graficos/`     |
| Stopwords extras                                          | `uv run python scielo_wordcloud.py resultado.csv --stopwords extra.txt`  | Idem                                                                                             | Idem            |
| Colormap alternativo                                      | `uv run python scielo_wordcloud.py resultado.csv --colormap plasma`      | Idem (cores plasma)                                                                              | Idem            |
| Estilo matplotlib alternativo                             | `uv run python scielo_wordcloud.py resultado.csv --style ggplot`         | Idem (estilo diferente)                                                                          | Idem            |
| Simular sem gerar arquivos                                | `uv run python scielo_wordcloud.py resultado.csv --dry-run`              | Nada (imprime config)                                                                            | —               |

### Diagrama PRISMA 2020

| Pergunta / Objetivo                            | Comando                                                                                       | O que cria                       | Onde salva        |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------- | ----------------- |
| Auto-descoberta do JSON (sem parâmetro)        | `uv run python prisma_workflow.py`                                                            | `prisma_<stem>_pt_<ts>.pdf`      | Diretório do JSON |
| Gerar PDF PRISMA (campos humanos em branco)    | `uv run python prisma_workflow.py results_report.json`                                        | `prisma_<stem>_pt_<ts>.pdf`      | Diretório do JSON |
| Com campos humanos via CLI                     | `uv run python prisma_workflow.py results_report.json --included 80 --excluded-screening 523` | Idem (campos preenchidos no PDF) | Idem              |
| Modo interativo (terminal pergunta cada campo) | `uv run python prisma_workflow.py results_report.json -i`                                     | Idem                             | Idem              |
| Campos humanos de arquivo                      | `uv run python prisma_workflow.py results_report.json --human-data campos.json`               | Idem                             | Idem              |
| PDF em inglês                                  | `uv run python prisma_workflow.py results_report.json --lang en`                              | `prisma_<stem>_en_<ts>.pdf`      | Idem              |
| Pasta de saída específica                      | `uv run python prisma_workflow.py results_report.json --output-dir pdfs/`                     | Idem                             | `pdfs/`           |
| Simular sem gerar PDF                          | `uv run python prisma_workflow.py results_report.json --dry-run`                              | Nada (imprime dados calculados)  | —                 |
| Exportar template de layout para customização  | `uv run python prisma_workflow.py --export-template`                                          | `assets/PRISMAdiagram.json`      | Diretório atual   |

---

## Exemplos de artefatos gerados

> Todos os exemplos abaixo foram gerados com `run_pipeline.py --per-year --year 2021-2025`, termos `avalia educa`, coleção SciELO Brasil.

### Diagnóstico do processo — `process_charts.py`

Compara as três estratégias de extração por ano. O modo `api+html` domina com >99% de extração completa; o modo `apenas-html` apresenta mais erros e tempo até 2,6× maior.

![Distribuição de status por modo de extração](exemplos/chart_status.png)

### Funil de seleção — `results_report.py`

Do total buscado ao corpus para curadoria: 553 buscados → 553 scrapeados (100%) → 85 criterio_ok (15,4%). Ponto de partida direto para preencher o PRISMA.

![Funil de seleção](exemplos/results_funnel_pt.png)

### Distribuição de termos por campo — `results_report.py`

Frequência de cada termo nos campos detectados, base: artigos `criterio_ok`. *educa* concentra 94,1% nas palavras-chave; *avalia* distribui-se mais uniformemente entre título (76,5%) e resumo (88,2%).

![Heatmap de termos](exemplos/results_terms_heatmap_pt.png)

### Periódicos com maior representação — `results_report.py`

Top periódicos no corpus filtrado com percentuais. Em 2024, três periódicos concentraram 30,6% do total: *Educar em Revista* (n=10, 11,8%), *Ensaio: Avaliação e Políticas Públicas em Educação* (n=8, 9,4%) e *Revista Brasileira de Educação Médica* (n=8, 9,4%).

![Periódicos](exemplos/results_journals_pt.png)

### Nuvem de palavras — `scielo_wordcloud.py`

Gerada a partir das palavras-chave do corpus `criterio_ok`. Domínio de *saúde*, *educação* e *enfermagem* — revela o perfil temático do corpus de forma imediata.

![Wordcloud de palavras-chave](exemplos/wordcloud_keywords.png)

### Diagrama PRISMA 2020 — `prisma_workflow.py`

PDF A4 preenchível com a fase de Identificação auto-preenchida (n=553, triagem=552, incluídos sugeridos=85). As fases de Triagem e Inclusão ficam como campos AcroForm editáveis para curadoria humana no Acrobat Reader, Edge ou Foxit.

![Diagrama PRISMA](exemplos/prisma_preview.png)

### Texto publication-ready — `results_report.py`

O `results_text_pt.md` entrega seções prontas para submissão. Exemplo de trecho automático da seção de Metodologia (2024):

> *"A busca bibliográfica, conduzida em 5 de maio de 2026, foi realizada na plataforma SciELO Brasil por meio do SciELO Search, utilizando os termos "avalia" e "educa" com truncamento automático (operador $), nos campos de título e resumo, abrangendo o ano de 2024. Foram recuperados 553 registros. [...] A etapa de filtragem automática verificou a presença simultânea de todos os termos em pelo menos um dos campos requeridos (título e palavras-chave), identificando 85 artigos (15,4%) como potencialmente relevantes para curadoria humana."*

O arquivo inclui ainda: nota técnica com URL da busca, seção de Resultados, Limitações, e descrição textual de cada figura em versão curta (legenda) e longa (substituto textual para publicações sem imagens).

---

## 0. Buscando artigos com scielo_search.py

Antes de extrair dados com o scraper, é preciso ter uma lista de PIDs. O `scielo_search.py` faz isso automaticamente: ele consulta o SciELO Search e gera um CSV pronto para usar como entrada do scraper.

### Uso básico

```bash
uv run python scielo_search.py --terms avalia educa --years 2022-2025
```

### Arquivos gerados

A busca gera dois arquivos lado a lado:

- `sc_20260411_143022.csv` — lista de artigos com PIDs e metadados básicos
- `sc_20260411_143022_params.json` — registro completo dos parâmetros usados

O `_params.json` tem esta estrutura:

```json
{
  "timestamp": "2026-04-11T14:30:22",
  "versao_searcher": "1.3",
  "colecao": "scl",
  "termos_originais": ["avalia", "educa"],
  "truncamento": true,
  "campos": "ti+ab",
  "anos": [2022, 2023, 2024, 2025],
  "total_resultados": 847,
  "query_url": "https://search.scielo.org/?q=..."
}
```

> O campo `versao_searcher` é gravado a partir da v1.3 do `scielo_search.py` e é lido pelo `results_report.py` para enriquecer o texto de Metodologia.

### Consultar os parâmetros de uma busca anterior

```bash
# Última busca no diretório atual
uv run python scielo_search.py --show-params

# Busca específica (outro diretório)
uv run python scielo_search.py --show-params exemplos/2024/sc_20260413_092345_params.json
```

Imprime o JSON formatado no terminal, útil para documentar ou reproduzir a busca.

### Termos exatos (sem truncamento)

Por padrão os termos são truncados com `$` (ex: `avalia$` casa com "avaliação", "avaliativo", etc.). Para desativar:

```bash
uv run python scielo_search.py --terms avaliação educação --no-truncate
```

### Outras coleções

```bash
uv run python scielo_search.py --terms avalia educa --years 2022-2025 --collection arg
```

### Ajuda

```bash
uv run python scielo_search.py --help
uv run python scielo_search.py -?
```

### Fluxo completo: searcher → scraper

```bash
# 1. Gerar a lista de artigos
uv run python scielo_search.py --terms avalia educa --years 2022-2025

# 2. Extrair os dados completos (título, resumo, palavras-chave)
uv run python scielo_scraper.py sc_20260411_143022.csv
```

---

## 1. Instalação

### Pré-requisitos

- Python 3.10 ou superior
- [uv](https://github.com/astral-sh/uv) instalado

### Instalar dependências

```bash
# Dependências do scraper (núcleo)
uv pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli

# Dependências opcionais (necessárias para os scripts de análise)
uv pip install matplotlib matplotlib-venn upsetplot  # gráficos e diagramas de Venn
uv pip install wordcloud nltk pillow                 # nuvem de palavras
uv pip install reportlab                             # diagrama PRISMA (PDF)
```

> **Por que `brotli`?** O servidor do SciELO comprime as páginas com o algoritmo Brotli. Sem este pacote, o conteúdo chega corrompido e o scraping falha — mesmo sem mensagem de erro visível.

---

## 2. Preparando o CSV de entrada

O CSV precisa ter **obrigatoriamente** uma coluna chamada `ID` com os PIDs SciELO.

**Formato mínimo:**

```csv
ID
S1982-88372022000300013
S1984-92302022000400750
S0103-64402022000600044
```

**Com colunas extras (também aceito):**

```csv
ID,Title,Author(s),Journal,Language(s),Publication year
S1982-88372022000300013,Título do artigo,Autor et al.,Revista X,Português,2022
```

As colunas extras são mantidas no resultado.

### Como é um PID SciELO?

Um PID tem o formato `S` + ISSN + ano + volume/fascículo + sequência. Exemplo:

```
S 1982-8837 2022 000 3 00013
│ └── ISSN ┘ └ano┘ └─┘ └seq┘
│                   vol/fasc
└── sempre S
```

PIDs com `-scl` ou `-oai` no final são aceitos — o script remove o sufixo automaticamente.

---

## 3. Rodando o script

### Execução simples

```bash
uv run python scielo_scraper.py minha_lista.csv
```

O script cria automaticamente uma pasta de saída chamada `minha_lista_s_20240101_120000_api+html/` (com data, hora e modo) contendo:

- `resultado.csv` — dados extraídos
- `scraper.log` — log detalhado
- `stats.json` — estatísticas

### Acompanhando o progresso

O progresso aparece no terminal com barra (`tqdm`) e logs coloridos. Exemplo:

```
2024-01-01 12:00:05  INFO      ────────────────────────────────────────────
2024-01-01 12:00:05  INFO      Linha CSV 2 | PID: 'S1982-88372022000300013'
2024-01-01 12:00:06  INFO        ✓ Titulo_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✓ Resumo_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✓ Palavras_Chave_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✅ Resultado: T:✓  R:✓  KW:✓  [ok_completo]
```

O sistema é mantido acordado automaticamente durante a execução (via `wakepy`) — não precisa se preocupar com o computador entrar em modo de suspensão.

### Checkpoint

Por padrão o script salva o CSV a cada 25 artigos. Para alterar:

```bash
# Salvar a cada 50 artigos
uv run python scielo_scraper.py minha_lista.csv --checkpoint 50

# Salvar após cada artigo (mais seguro, um pouco mais lento)
uv run python scielo_scraper.py minha_lista.csv --checkpoint 1

# Salvar apenas no final
uv run python scielo_scraper.py minha_lista.csv --checkpoint 0
```

### Ajuda

```bash
uv run python scielo_scraper.py --help
uv run python scielo_scraper.py -?
```

---

## 4. Entendendo os resultados

### Status de cada artigo

| Status              | Significado                                           |
| ------------------- | ----------------------------------------------------- |
| `ok_completo`       | Título, resumo e palavras-chave extraídos com sucesso |
| `ok_parcial`        | Pelo menos um campo extraído, mas não todos           |
| `nada_encontrado`   | Página acessada mas sem dados encontrados             |
| `erro_extracao`     | Falha na extração (ex: página não encontrada)         |
| `erro_pid_invalido` | PID não reconhecido como válido                       |

### Relatório final

Ao terminar, o script imprime um resumo:

```
==============================================================
  ESTATÍSTICAS FINAIS  (script v2.5)
==============================================================
    Total processados               : 564
    ✅  ok_completo                 : 562  (99.6%)
    🟡  ok_parcial                  : 1  (0.2%)
    ✅+🟡 sucesso total             : 563  (99.8%)
    ❌  erro_extracao               : 1  (0.2%)
    ⏱   Tempo total                 : 1545.82s  (25m 45s)
    ⏱   Média por artigo            : 2.74s
```

### Coluna `fonte_extracao`

Indica de onde cada campo veio:

| Valor                                | Significado                        |
| ------------------------------------ | ---------------------------------- |
| `articlemeta_isis[T]`                | Título via ArticleMeta API         |
| `articlemeta_isis[R]`                | Resumo via ArticleMeta API         |
| `articlemeta_isis[K]`                | Palavras-chave via ArticleMeta API |
| `Titulo_PT←pag1_meta_tags`           | Título via meta tags HTML          |
| `Resumo_PT←pag1_html_body`           | Resumo via corpo da página HTML    |
| `Palavras_Chave_PT←pag_pt_meta_tags` | Keywords via versão PT da página   |

---

## 5. Retomando uma execução interrompida

Se a execução foi interrompida (queda de energia, fechamento do terminal, etc.), use `--resume`:

```bash
uv run python scielo_scraper.py minha_lista.csv --resume
```

O script encontra automaticamente a execução anterior mais recente, carrega os artigos já processados com sucesso e continua a partir de onde parou.

### Como funciona o resume

- O script procura a pasta `minha_lista_s_*/` mais recente no mesmo diretório do CSV
- **Reutiliza a pasta existente** — nenhuma pasta nova é criada
- O log é **anexado** à execução anterior, com um separador indicando a retomada:
  
  ```
  ══ RETOMADA ══
  ```
- As estatísticas finais acumulam o tempo total das duas execuções
- O `stats.json` registra `"resume": "CONTINUED"` para identificar execuções retomadas
- Artigos com status `ok_completo` ou `ok_parcial` não são reprocessados
- Artigos com erro são reprocessados

### Forçar início do zero

```bash
uv run python scielo_scraper.py minha_lista.csv --no-resume
```

---

## 6. Estratégias de extração

### Padrão (API + HTML) — recomendado

```bash
uv run python scielo_scraper.py minha_lista.csv
```

Usa a ArticleMeta API como fonte primária e o scraping HTML como fallback automático. Melhor resultado com menor tempo. A pasta de saída terá o sufixo `_api+html`.

### Apenas API

```bash
uv run python scielo_scraper.py minha_lista.csv --only-api
```

Mais rápido, mas perde artigos Ahead of Print (AoP) — a API não retorna dados para eles. Recomendado apenas para testes ou quando a cobertura de AoPs não for importante. A pasta de saída terá o sufixo `_api`.

### Apenas HTML

```bash
uv run python scielo_scraper.py minha_lista.csv --only-html
```

Mais lento (~10 min a mais para 564 artigos), mas útil quando a API estiver fora do ar. Recupera praticamente os mesmos artigos que o modo padrão. A pasta de saída terá o sufixo `_html`.

### Comparativo

Resultados observados em cinco anos de coleta (SciELO Brasil, termos: *avalia$*, *educa$*):

| Estratégia        | ok_completo | Tempo médio | Pasta gerada       | Quando usar                     |
| ----------------- | ----------- | ----------- | ------------------ | ------------------------------- |
| Padrão (api+html) | 99.4–99.8%  | ~24–32 min  | `_s_..._api+html/` | Sempre — melhor custo-benefício |
| Apenas API        | 98.6–99.2%  | ~24–28 min  | `_s_..._api/`      | Testes rápidos sem AoPs         |
| Apenas HTML       | 96.8–98.9%  | ~33–71 min  | `_s_..._html/`     | API fora do ar                  |

Dados detalhados por ano (2021–2025):

| Ano  | n   | Estratégia        | ok_completo | ok_parcial | erro     | Tempo       | vs. html  |
| ---- | --- | ----------------- | ----------- | ---------- | -------- | ----------- | --------- |
| 2021 | 561 | `--only-api`      | 99.1%       | 0.9%       | 0.0%     | ~25 min     |           |
| 2021 | 561 | `--only-html`     | 96.8%       | 0.2%       | 3.0%     | ~33 min     |           |
| 2021 | 561 | padrão (api+html) | **99.5%**   | 0.5%       | **0.0%** | **~28 min** | **−15%**  |
| 2022 | 564 | `--only-api`      | 98.6%       | 1.1%       | 0.4%     | ~25 min     |           |
| 2022 | 564 | `--only-html`     | 98.9%       | 0.2%       | 0.9%     | ~50 min     |           |
| 2022 | 564 | padrão (api+html) | **99.8%**   | 0.2%       | **0.0%** | **~26 min** | **−48%**  |
| 2023 | 468 | `--only-api`      | 98.9%       | 1.1%       | 0.0%     | ~24 min     |           |
| 2023 | 468 | `--only-html`     | 98.3%       | 0.6%       | 1.1%     | ~57 min     |           |
| 2023 | 468 | padrão (api+html) | **99.4%**   | 0.6%       | **0.0%** | **~24 min** | **−58%**  |
| 2024 | 553 | `--only-api`      | 98.9%       | 0.9%       | 0.2%     | ~27 min     |           |
| 2024 | 553 | `--only-html`     | 98.2%       | 0.2%       | 1.6%     | ~71 min     |           |
| 2024 | 553 | padrão (api+html) | **99.6%**   | 0.2%       | **0.2%** | **~27 min** | **−62%**  |
| 2025 | 603 | `--only-api`      | 99.2%       | 0.8%       | 0.0%     | ~28 min     |           |
| 2025 | 603 | `--only-html`     | 98.2%       | 0.5%       | 1.3%     | ~57 min     |           |
| 2025 | 603 | padrão (api+html) | **99.7%**   | 0.3%       | **0.0%** | **~32 min** | **−45%**  |

A coluna **vs. html** indica a economia de tempo do modo padrão em relação ao `--only-html`.

> O modo `--only-html` é o mais lento e o de menor cobertura: chegou a 71 min em 2024 e apresentou até 3.0% de erros (2021). O modo `--only-api` é mais rápido mas perde artigos Ahead of Print (AoP), que não estão indexados na API.

---

## 7. Outras coleções SciELO

Por padrão o script acessa a coleção Brasil (`scl`). Para ver todas as coleções disponíveis:

```bash
uv run python scielo_scraper.py --list-collections
```

Saída:

```
==============================================================
  Coleções SciELO disponíveis  (36 total)
==============================================================

  COD     Nome                            Domínio                        Artigos
  ------  ------------------------------  -----------------------------  -------

  Ativas (32):
  arg     Argentina                       www.scielo.org.ar               66914 docs
  chl     Chile                           www.scielo.cl                   99324 docs
  col     Colômbia                        www.scielo.org.co              113554 docs
  ...
  scl     Brasil                          www.scielo.br                  552840 docs
  ...
```

Para usar outra coleção:

```bash
# Argentina
uv run python scielo_scraper.py lista.csv --collection arg

# Portugal
uv run python scielo_scraper.py lista.csv --collection prt

# México
uv run python scielo_scraper.py lista.csv --collection mex
```

---

## 8. Ajustando velocidade e comportamento

### Delay entre requisições

Por padrão o script espera 1.5s ± 0.5s entre cada artigo (para não sobrecarregar o servidor). Para aumentar ou diminuir:

```bash
# Mais lento (mais respeitoso com o servidor)
uv run python scielo_scraper.py lista.csv --delay 3.0 --jitter 1.0

# Mais rápido (use com cuidado)
uv run python scielo_scraper.py lista.csv --delay 0.5 --jitter 0.2

# Default: --delay 1.5 --jitter 0.5
```

### Processamento paralelo

Para processar vários artigos ao mesmo tempo (máximo 4 workers):

```bash
uv run python scielo_scraper.py lista.csv --workers 2
```

> Use com moderação — muitas requisições paralelas podem resultar em bloqueio temporário pelo servidor.

### Pasta de saída personalizada

```bash
uv run python scielo_scraper.py lista.csv --output-dir resultados/minha_pasta
```

### Log detalhado para depuração

```bash
uv run python scielo_scraper.py lista.csv --log-level DEBUG
```

O modo DEBUG mostra cada URL acessada, cada campo encontrado ou não, e o motivo de cada fallback.

---

## 9. Verificando estatísticas de uma execução anterior

```bash
# Com CSV (procura a pasta mais recente automaticamente)
uv run python scielo_scraper.py lista.csv --stats-report

# Com pasta específica (CSV não obrigatório)
uv run python scielo_scraper.py --stats-report --output-dir resultados/minha_pasta
```

---

## 10. Gráficos de diagnóstico com process_charts.py

O `process_charts.py` é o script de **diagnóstico técnico do processo** — visualiza como o scraping correu (taxas de sucesso, fontes de extração, tempo). Lê as pastas `runs/<ano>/` e produz três gráficos PNG.

### Uso básico

```bash
uv run python process_charts.py
```

Lê automaticamente todos os anos presentes em `runs/` e salva os gráficos no diretório atual.

### Gráficos e artefatos gerados

| Arquivo             | O que mostra                                                                                                                                                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `chart_status.png`  | Distribuição de status (`ok_completo`, `ok_parcial`, `erro_extracao`) por modo e ano. Barras cinzas para a categoria dominante; cores fortes para casos raros. Tabela inset com n exatos.                                                                     |
| `chart_sources.png` | Fontes de extração no modo `api+html` por ano. Distingue: *ArticleMeta API* (todos os campos via API), *Fallback API+HTML* (API parcial + complemento HTML), *Fallback HTML* (API sem dados + extração inteiramente via HTML), *Falha de acesso* (erro HTTP). |
| `chart_time.png`    | Tempo total de scraping (em minutos) por modo e ano, para comparar custo entre estratégias.                                                                                                                                                                   |
| `chart_stats.json`  | Metadados da execução: `versao_script`, `gerado_em`, `modo`, `labels` (anos/stems processados), `idiomas` e `arquivos_gerados`. Gravado automaticamente na pasta `--output`.                                                                                  |

### Opções

```bash
uv run python process_charts.py --years 2022 2024            # apenas esses anos (default: todos em runs/)
uv run python process_charts.py --base outra/pasta           # pasta raiz alternativa (default: runs/)
uv run python process_charts.py --output graficos/           # pasta de saída (default: diretório atual)
uv run python process_charts.py --stem sc_20260411_143022    # run específico (evita ambiguidade)
uv run python process_charts.py --lang en                    # gráficos em inglês (default: pt)
uv run python process_charts.py --lang all                   # todos os idiomas, sufixo _pt/_en (default: pt)
uv run python process_charts.py --no-sources                 # pular gráfico de fontes
uv run python process_charts.py --no-status --no-time        # apenas gráfico de fontes
uv run python process_charts.py --version                    # mostrar versão
uv run python process_charts.py -?                           # ajuda
```

---

## 11. Relatório consolidado com run_pipeline.py --stats-report

Gera um relatório Markdown com as estatísticas de todas as execuções armazenadas em `runs/`, sem executar nenhum scraping.

```bash
# Relatório para runs/ no diretório atual (imprime no terminal)
uv run python run_pipeline.py --stats-report

# Salvar em arquivo
uv run python run_pipeline.py --stats-report > stats.md

# Usar pasta alternativa
uv run python run_pipeline.py --stats-report outra/pasta
```

O relatório inclui, por ano e por modo (`api+html`, `api`, `html`):

- Total de artigos e distribuição de status com percentuais
- Fontes de extração (`por_fonte_extracao`)
- Tempo de execução e média por artigo

E ao final, totais globais: artigos, tempo por estratégia, média geral.

> `--stats-report` não requer `--year` — funciona de forma standalone.

---

## 12. Detecção de termos com terms_matcher.py

Consolida os `resultado.csv` de um ou mais anos e detecta termos de busca em cada campo PT, gerando colunas booleanas auditáveis em planilha eletrônica — sem requisições à internet.

### Uso básico

```bash
# Todos os anos, termos padrão (avalia, educa), campos required padrão (titulo, keywords)
uv run python terms_matcher.py

# Anos específicos
uv run python terms_matcher.py --years 2022 2024

# Termos personalizados
uv run python terms_matcher.py --terms avalia educa fisica --years 2022 2023 2024 2025

# Alterar campos usados em criterio_ok
uv run python terms_matcher.py --required-fields titulo resumo keywords

# Relatório do último run (sem processar CSVs)
uv run python terms_matcher.py --stats-report

# Relatório de um arquivo específico
uv run python terms_matcher.py --stats-report terms_20260414_211522_stats.json
```

### Colunas adicionadas ao CSV original

| Coluna              | Tipo | Descrição                                                |
| ------------------- | ---- | -------------------------------------------------------- |
| `n_palavras_titulo` | int  | Nº de palavras no Titulo_PT                              |
| `n_palavras_resumo` | int  | Nº de palavras no Resumo_PT                              |
| `n_keywords_pt`     | int  | Nº de keywords separadas por ";"                         |
| `<termo>_titulo`    | bool | Termo encontrado em Titulo_PT                            |
| `<termo>_resumo`    | bool | Termo encontrado em Resumo_PT                            |
| `<termo>_keywords`  | bool | Termo encontrado em Palavras_Chave_PT                    |
| `criterio_ok`       | bool | Todos os termos em pelo menos um dos `--required-fields` |

> ⚠ **Atenção:** o nº de colunas booleanas cresce com T termos × 3 campos = 3T colunas. Padrão (2 termos): 6 colunas. Com 5 termos: 15 colunas. Considere isso ao abrir em planilhas.
> As colunas booleanas cobrem sempre os 3 campos (titulo, resumo, keywords); o `criterio_ok` avalia apenas os `--required-fields` (padrão: titulo e keywords).

### Saídas geradas

| Arquivo                 | Conteúdo                                              |
| ----------------------- | ----------------------------------------------------- |
| `terms_<ts>.csv`        | CSV consolidado com colunas originais + novas         |
| `terms_<ts>.log`        | Log detalhado da execução                             |
| `terms_<ts>_stats.json` | Estatísticas por ano e globais, parâmetros, auditoria |

### Estatísticas no log e no stats.json

Por ano e, quando há mais de um ano, consolidadas globalmente:

- `criterio_ok`: artigos que atendem ao critério (n e %)
- Por termo: presença em cada campo (titulo, resumo, keywords)
- Médias de n_palavras_titulo, n_palavras_resumo, n_keywords

### Campos disponíveis para --required-fields

| Campo      | Coluna do CSV     |
| ---------- | ----------------- |
| `titulo`   | Titulo_PT         |
| `resumo`   | Resumo_PT         |
| `keywords` | Palavras_Chave_PT |

### Opções completas

```bash
uv run python terms_matcher.py --years 2022 2024                        # anos específicos (default: todos em runs/)
uv run python terms_matcher.py --terms avalia educa                     # termos (default: avalia educa)
uv run python terms_matcher.py --required-fields titulo keywords        # campos do criterio_ok (default: titulo keywords)
uv run python terms_matcher.py --match-mode any                         # qualquer termo satisfaz (default: all = todos)
uv run python terms_matcher.py --no-truncate                            # não remover $ dos termos
uv run python terms_matcher.py --mode api                               # modo alternativo (default: api+html)
uv run python terms_matcher.py --base outra/pasta                       # pasta base alternativa (default: runs/)
uv run python terms_matcher.py --output saida.csv                       # nome de saída (default: terms_<ts>.csv)
uv run python terms_matcher.py --stats-report                           # relatório do último run
uv run python terms_matcher.py --log-level DEBUG                        # log detalhado (default: INFO)
uv run python terms_matcher.py -?                                       # ajuda
```

---

## 13. Artefatos científicos com results_report.py

Gera o arcabouço completo de artefatos científicos publication-ready a partir do `terms_*.csv` produzido pelo `terms_matcher.py`. Focado nos **resultados** — o que foi encontrado, não como o processo técnico correu.

Contexto: ferramenta do projeto *Estado da Arte da Avaliação* (e-Aval), grupo de pesquisa do Mestrado Profissional em Avaliação da Fundação Cesgranrio.

### Uso básico

```bash
# Todos os anos em runs/, estratégia api+html (padrão) — um conjunto por ano
uv run python results_report.py

# Anos específicos
uv run python results_report.py --years 2022 2023 2024 2025

# Consolidado multi-ano → runs/results_2021-2025/
uv run python results_report.py --base runs/

# Pasta de saída explícita
uv run python results_report.py --output-dir meus_relatorios/

# Artefatos em inglês
uv run python results_report.py --lang en

# Todos os idiomas (gera um conjunto por idioma)
uv run python results_report.py --lang all
```

### Modo consolidado (`--base runs/`)

Quando `--base` aponta para uma pasta com múltiplos anos, o script agrega todos os dados num único conjunto de artefatos com visão de série temporal completa:

- **Funil:** painéis lado a lado por ano
- **Trend:** evolução de criterio_ok (n e %) ao longo dos anos
- **Heatmap e periódicos:** calculados sobre o corpus total agregado

A pasta de saída segue o padrão `runs/results_<ano_min>-<ano_max>/` (ex: `runs/results_2021-2025/`). Para uma pasta personalizada, use `--output-dir`.

### Artefatos gerados em `results_<stem>/`

**Gráficos:**

| Arquivo                     | O que mostra                                                                                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `results_funnel.png`        | Funil de seleção: total buscado → scrapeado → criterio_ok, por ano                                                                                                    |
| `results_trend.png`         | Evolução temporal de criterio_ok: n artigos e % por ano                                                                                                               |
| `results_terms_heatmap.png` | Heatmap termos × campos: % de artigos (base: criterio_ok=True) onde cada termo aparece em cada campo                                                                  |
| `results_journals.png`      | Top N periódicos com mais artigos criterio_ok                                                                                                                         |
| `results_coverage.png`      | % de artigos com título / resumo / palavras-chave em PT presentes, por ano                                                                                            |
| `results_venn[_en].png`     | Diagrama de Venn (≤3 termos) ou UpSet (≥4 termos) — sobreposição de termos por campo no corpus completo. Inclui legenda colorida identificando qual cor = qual termo. |

**Tabelas:**

| Arquivo                      | Conteúdo                                                   |
| ---------------------------- | ---------------------------------------------------------- |
| `results_table_summary.csv`  | Funil por ano: total buscado, scrapeado, criterio_ok n e % |
| `results_table_terms.csv`    | Por termo × campo: n e % de ocorrência (base: criterio_ok) |
| `results_table_journals.csv` | Todos os periódicos com contagem, % e anos presentes       |

**Texto:**

| Arquivo              | Conteúdo                                                                                                                                                                                                                                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `results_text_pt.md` | Texto publication-ready em PT-BR com: Metodologia (data da busca, versões dos scripts, tempo de extração, taxa de sucesso, explicação leiga da estratégia api+html) + Nota técnica (URL da busca) + Resultados + Limitações + Descrição dos resultados por figura (versão curta e longa para cada gráfico) |
| `results_text_en.md` | Idem em inglês (gerado com `--lang en` ou `--lang all`)                                                                                                                                                                                                                                                    |

> O arquivo sempre é gerado com sufixo de idioma (`_pt` ou `_en`). Não existe `results_text.md` sem sufixo.

**Metadados:**

| Arquivo               | Conteúdo                                                       |
| --------------------- | -------------------------------------------------------------- |
| `results_report.json` | Todos os dados calculados — para consulta, reúso ou integração |

### Opções completas

```bash
uv run python results_report.py --base outra/pasta        # pasta raiz alternativa (default: runs/)
uv run python results_report.py --years 2022 2024         # anos específicos (default: todos em runs/)
uv run python results_report.py --mode api                # estratégia alternativa (default: api+html)
uv run python results_report.py --scrape-dir sc_<ts>_s_<ts>_api+html/  # pasta direta (sem --base)
uv run python results_report.py --output-dir relatorios/  # pasta de saída (default: results_<stem>/ ao lado da pasta de scraping)
uv run python results_report.py --lang pt                 # português (default)
uv run python results_report.py --lang en                 # inglês
uv run python results_report.py --lang all                # todos os idiomas (PT + EN)
uv run python results_report.py --top-journals 20         # top 20 periódicos (default: 15)
uv run python results_report.py --style seaborn-v0_8      # estilo matplotlib (default: default)
uv run python results_report.py --list-styles             # listar estilos disponíveis
uv run python results_report.py --colormap plasma         # colormap do heatmap (default: viridis)
uv run python results_report.py --list-colormaps          # listar colormaps disponíveis
uv run python results_report.py --artifacts funnel,trend  # gerar apenas estes artefatos (aliases curtos)
uv run python results_report.py --skip-artifacts text,report  # pular estes artefatos
uv run python results_report.py --dry-run                 # simula sem gravar
uv run python results_report.py --version                 # mostrar versão
uv run python results_report.py -?                        # ajuda
uv run python results_report.py --show-report             # renderiza results_report.json existente no terminal
uv run python results_report.py --show-report outro/caminho/results_report.json  # arquivo específico
uv run python results_report.py --help-artifacts          # lista resumida de todos os artefatos com aliases
uv run python results_report.py --help-artifact results_funnel  # descrição detalhada de um artefato
```

**Aliases de artefatos disponíveis** (para `--artifacts` e `--skip-artifacts`):

| Alias            | Artefato completo        |
| ---------------- | ------------------------ |
| `funnel`         | `results_funnel`         |
| `trend`          | `results_trend`          |
| `heatmap`        | `results_terms_heatmap`  |
| `journals`       | `results_journals`       |
| `coverage`       | `results_coverage`       |
| `venn`           | `results_venn`           |
| `text`           | `results_text`           |
| `table_summary`  | `results_table_summary`  |
| `table_terms`    | `results_table_terms`    |
| `table_journals` | `results_table_journals` |
| `report`         | `results_report`         |

### Consultando artefatos gerados

**`--show-report`** — exibe um relatório formatado no terminal a partir de um `results_report.json` já gerado, sem precisar reprocessar os dados:

```bash
# Usa results_report.json no diretório atual
uv run python results_report.py --show-report

# Aponta para arquivo específico
uv run python results_report.py --show-report runs/2026/results_.../results_report.json
```

Mostra: resumo por ano (buscados, scrapeados, critério ok), tabela de termos × campos e top 10 periódicos.

**`--help-artifacts`** — lista todos os artefatos com nome, tipo e nome de arquivo:

```bash
uv run python results_report.py --help-artifacts
```

**`--help-artifact <nome>`** — descrição detalhada de um artefato específico, em PT-BR e EN:

```bash
uv run python results_report.py --help-artifact results_terms_heatmap
uv run python results_report.py --help-artifact results_text
uv run python results_report.py --help-artifact results_report
```

Nomes de artefatos disponíveis: `results_funnel`, `results_trend`, `results_terms_heatmap`, `results_journals`, `results_coverage`, `results_table_summary`, `results_table_terms`, `results_table_journals`, `results_text`, `results_report`.

---

## 14. Nuvem de palavras com scielo_wordcloud.py

Gera nuvens de palavras a partir do `resultado.csv` do scraping. Útil para visualizar os termos mais frequentes nos títulos, resumos ou palavras-chave dos artigos.

### Uso básico

```bash
# Auto-descobre o resultado.csv (busca no diretório atual e pastas padrão)
uv run python scielo_wordcloud.py

# CSV explícito
uv run python scielo_wordcloud.py sc_ts_s_ts_api+html/resultado.csv

# Apenas um campo
uv run python scielo_wordcloud.py resultado.csv --field abstract

# Todos os artigos extraídos (não só criterio_ok)
uv run python scielo_wordcloud.py resultado.csv --corpus all
```

> **Auto-descoberta:** se o CSV não for passado, o script busca automaticamente:
> `resultado.csv` no diretório atual → `*_s_*_api+html/resultado.csv` → `*_s_*_api/` → `runs/*/`.
> Com múltiplos candidatos, usa o mais recente e avisa.

### Opções principais

```bash
uv run python scielo_wordcloud.py resultado.csv --field title        # campo: title | abstract | keywords (default: title + keywords)
uv run python scielo_wordcloud.py resultado.csv --field title+abstract  # múltiplos campos separados por +
uv run python scielo_wordcloud.py resultado.csv --field all          # todos os três campos
uv run python scielo_wordcloud.py resultado.csv --lang pt-br         # idioma das stopwords NLTK (default: pt-br)
uv run python scielo_wordcloud.py resultado.csv --stopwords extra.txt  # stopwords adicionais (1 por linha ou CSV key,value)
uv run python scielo_wordcloud.py resultado.csv --no-domain-stopwords  # desativa stopwords acadêmicas do domínio
uv run python scielo_wordcloud.py resultado.csv --mask forma.png     # shape personalizada (PNG/JPG; pixels escuros = área)
uv run python scielo_wordcloud.py resultado.csv --width 1200         # largura em pixels (default: 800; height = width/2)
uv run python scielo_wordcloud.py resultado.csv --height 600         # altura em pixels (width = height*2 se omitido)
uv run python scielo_wordcloud.py resultado.csv --colormap plasma    # colormap matplotlib (default: viridis)
uv run python scielo_wordcloud.py resultado.csv --style ggplot       # estilo matplotlib para o gráfico
uv run python scielo_wordcloud.py resultado.csv --max-words 100      # máx. palavras (default: 200)
uv run python scielo_wordcloud.py resultado.csv --output-dir graficos/  # pasta de saída
uv run python scielo_wordcloud.py resultado.csv --dry-run            # mostrar config sem gerar arquivos
uv run python scielo_wordcloud.py --list-langs                       # listar idiomas NLTK disponíveis
uv run python scielo_wordcloud.py --list-colormaps                   # listar colormaps disponíveis
uv run python scielo_wordcloud.py --list-styles                      # listar estilos matplotlib disponíveis
uv run python scielo_wordcloud.py --version                          # mostrar versão
uv run python scielo_wordcloud.py -?                                 # ajuda
```

### Saída

- `wordcloud_{campo}_{lang}_{ts}.png` — uma imagem por campo processado
- `wordcloud_stats_{ts}.json` — metadados: campo, idioma, corpus, colormap, estilo, n artigos, n tokens, palavras mais frequentes

### Stopwords

O script combina três fontes de stopwords (por padrão):

1. **NLTK** — lista geral do idioma (português: 207 palavras; inglês: 198; espanhol: 313). Baixada automaticamente na primeira execução.
2. **Domínio acadêmico** — termos do contexto SciELO/avaliação educacional (ex: "artigo", "estudo", "resultado"). Desative com `--no-domain-stopwords`.
3. **Arquivo personalizado** — via `--stopwords ARQ` (uma palavra por linha, ou CSV com coluna `word`).

### Validação de CSV

Se as colunas esperadas (`Titulo_PT`, `Resumo_PT`, `Palavras_Chave_PT`) não existirem no arquivo, o script:

- Exibe a lista de colunas encontradas
- Avisa se o arquivo não parece ser um `resultado.csv` do scraper
- Indica o comando para gerar o arquivo correto

---

## 15. Diagrama PRISMA 2020 com prisma_workflow.py

Gera um PDF A4 preenchível com o Diagrama de Fluxo PRISMA 2020. O layout está embutido diretamente no script — nenhum arquivo externo é necessário. A fase de **Identificação** é auto-preenchida a partir do `results_report.json`. As fases de **Triagem** e **Inclusão** ficam como campos AcroForm editáveis para preenchimento após curadoria humana.

> **Layout customizável:** use `--export-template` para exportar o template de layout como JSON e modificá-lo. Se o arquivo `assets/PRISMAdiagram.json` existir, ele sobrepõe o layout padrão embutido.

> **Nota:** o pipeline automatiza apenas a fase de Identificação. Triagem e Inclusão dependem de revisão humana dos artigos.

### Uso básico

```bash
# Auto-descobre o results_report.json (busca no diretório atual e runs/*/results_*/)
uv run python prisma_workflow.py

# JSON explícito
uv run python prisma_workflow.py runs/2026/results_*/results_report.json

# Passando campos humanos pela linha de comando
uv run python prisma_workflow.py results_report.json --included 80 --excluded-screening 523

# Modo interativo (terminal pergunta cada campo humano um a um)
uv run python prisma_workflow.py results_report.json -i

# Campos humanos de arquivo JSON
uv run python prisma_workflow.py results_report.json --human-data campos_humanos.json
```

> **Auto-descoberta:** se o JSON não for passado, o script busca automaticamente no diretório atual → `runs/*/results_*/` → `results_*/`. Com múltiplos candidatos, lista as opções e pede que o usuário escolha.

### Campos auto-preenchidos (da fase de Identificação)

| Campo                      | Fonte                                               |
| -------------------------- | --------------------------------------------------- |
| Total buscado (n)          | `total_buscado` do JSON                             |
| Registros para triagem (n) | Calculado: buscado − duplicatas − automação − erros |
| Registros de automação (n) | Artigos marcados inelegíveis automaticamente        |
| Erros/outros (n)           | `erro_extracao` + `erro_pid_invalido`               |
| Incluídos (sugestão)       | `criterio_ok` (editável no PDF)                     |

### Campos humanos (Triagem e Inclusão)

Preencher no PDF após curadoria, ou passar via CLI/arquivo:

| Flag                       | Campo PRISMA                                   |
| -------------------------- | ---------------------------------------------- |
| `--duplicates N`           | Registros duplicados removidos                 |
| `--sought N`               | Relatórios buscados para recuperação           |
| `--not-retrieved N`        | Relatórios não recuperados                     |
| `--assessed N`             | Relatórios avaliados para elegibilidade        |
| `--excluded-screening N`   | Registros excluídos na triagem (título/resumo) |
| `--excluded-eligibility N` | Relatórios excluídos por elegibilidade         |
| `--included N`             | Estudos incluídos na revisão                   |
| `--included-reports N`     | Relatórios dos estudos incluídos               |

### Opções completas

```bash
uv run python prisma_workflow.py results_report.json --lang en          # PDF em inglês (default: pt)
uv run python prisma_workflow.py results_report.json --output-dir pdfs/ # pasta de saída
uv run python prisma_workflow.py results_report.json --dry-run          # mostrar dados sem gerar PDF
uv run python prisma_workflow.py --export-template                      # exportar template de layout para assets/PRISMAdiagram.json
uv run python prisma_workflow.py --export-template meu_layout.json      # exportar para caminho específico
uv run python prisma_workflow.py --version                              # mostrar versão
uv run python prisma_workflow.py -?                                     # ajuda
```

### Campos AcroForm

Todos os campos `n =` do diagrama são editáveis no PDF (AcroForm). Os que têm valor calculado automaticamente vêm pré-preenchidos; os demais ficam em branco. Não há distinção visual de cor entre campos automáticos e humanos — todos têm o mesmo estilo, facilitando microajustes manuais no Acrobat ou qualquer leitor PDF com suporte a formulários.

### Formato do arquivo `--human-data`

**JSON:**

```json
{
  "duplicates": 12,
  "sought": 687,
  "not_retrieved": 5,
  "assessed": 682,
  "excluded_screening": 523,
  "excluded_eligibility": 85,
  "included": 80,
  "included_reports": 80
}
```

**CSV:**

```
key,value
duplicates,12
sought,687
included,80
```

### Saída

- `prisma_<stem>_<lang>_<ts>.pdf` — PDF preenchível, abrível em qualquer leitor (Acrobat Reader, Edge, Foxit, LibreOffice)

---

## 16. Problemas comuns

### "PID inválido"

O PID não segue o padrão esperado. Verifique se a coluna `ID` contém PIDs no formato correto (ex: `S1982-88372022000300013`). PIDs com `-scl` ou `-oai` são aceitos.

### Muitos `erro_extracao` em artigos AoP

Artigos Ahead of Print têm `005` na posição 14–16 do PID (ex: `S1414-462X2022**005**024201`). A ArticleMeta API não retorna dados para eles — o modo padrão (api+html) resolve isso automaticamente via scraping HTML.

### Script lento ou timeout frequente

O servidor do SciELO pode estar lento. Tente aumentar o timeout:

```bash
uv run python scielo_scraper.py lista.csv --timeout 40
```

### Execução interrompida no meio

Use `--resume` para continuar de onde parou — os artigos já processados com sucesso não são reprocessados, e a pasta existente é reutilizada.

### Artigo com `ok_parcial` — falta resumo ou palavras-chave

Alguns artigos genuinamente não têm resumo ou palavras-chave em português disponíveis em nenhuma fonte (API nem HTML). Verifique a página do artigo manualmente para confirmar.

### Erro de encoding no terminal Windows

Se aparecerem caracteres estranhos no terminal, defina a variável de ambiente antes de rodar:

```bash
set PYTHONUTF8=1
uv run python scielo_scraper.py lista.csv
```

---

## 17. Dicionário de dados e termos

### Conceitos e terminologia

| Termo              | Definição                                                                                                                                                                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **PID**            | Identificador único SciELO. Formato: `S` + ISSN (com hífen, 9 chars) + ano (4) + volume/fascículo (3) + sequência (5) + dígito verificador (1) + letra de coleção (1). Total: 23 caracteres. Ex: `S1982-88372022000300013`.                                                                |
| **ISSN**           | International Standard Serial Number — identificador de periódico. Embutido no PID nas posições 1–9 (ex: `1982-8837`, já com hífen).                                                                                                                                                       |
| **AoP**            | Ahead of Print — artigo publicado online antes de receber volume/fascículo definitivo. Identificado por `005` nas posições 14–16 do PID. Não indexado na ArticleMeta API; extraído apenas via HTML.                                                                                        |
| **Coleção**        | Conjunto de periódicos de um país ou região na plataforma SciELO. Identificada por código de 3 letras (ex: `scl` = Brasil, `arg` = Argentina, `prt` = Portugal).                                                                                                                           |
| **ISIS-JSON**      | Formato de resposta da ArticleMeta API, derivado do formato de banco de dados CDS/ISIS usado pelo SciELO internamente. Contém os campos do artigo em múltiplos idiomas.                                                                                                                    |
| **Truncamento**    | Adição de `$` ao final de um termo de busca, para casar com variações morfológicas. Ex: `avalia$` casa com "avalia", "avaliação", "avaliativo", "avaliações". Ativo por padrão no `scielo_search.py`. No `terms_matcher.py`, o `$` é removido automaticamente para detecção por substring. |
| **criterio_ok**    | Coluna booleana do `terms_matcher.py`: `True` se todos os termos buscados forem encontrados em pelo menos um dos `--required-fields` (padrão: titulo ou keywords).                                                                                                                         |
| **campo required** | Campo(s) considerados no cálculo de `criterio_ok`. Cada termo deve aparecer em pelo menos um deles (não necessariamente o mesmo campo para todos os termos). Padrão: `titulo` e `keywords`.                                                                                                |
| **fallback HTML**  | Estratégia secundária de extração: quando a ArticleMeta API não retorna um campo, o scraper acessa a página HTML do artigo para tentar extraí-lo via meta tags ou corpo da página.                                                                                                         |

### Colunas do resultado.csv (scielo_scraper.py)

| Coluna              | Tipo | Origem      | Descrição                                                |
| ------------------- | ---- | ----------- | -------------------------------------------------------- |
| `ID`                | str  | CSV entrada | PID bruto conforme fornecido                             |
| `Title`             | str  | CSV entrada | Título conforme indexado no SciELO Search                |
| `Author(s)`         | str  | CSV entrada | Autores                                                  |
| `Source`            | str  | CSV entrada | Abreviatura do periódico                                 |
| `Journal`           | str  | CSV entrada | Nome completo do periódico                               |
| `Language(s)`       | str  | CSV entrada | Idioma(s) do artigo                                      |
| `Publication year`  | int  | CSV entrada | Ano de publicação                                        |
| `PID_limpo`         | str  | scraper     | PID normalizado (sufixos removidos, validado pelo regex) |
| `URL_PT`            | str  | scraper     | URL da versão em português consultada                    |
| `Titulo_PT`         | str  | scraper     | Título em português extraído                             |
| `Resumo_PT`         | str  | scraper     | Resumo em português extraído                             |
| `Palavras_Chave_PT` | str  | scraper     | Palavras-chave em português, separadas por `;`           |
| `status`            | str  | scraper     | Status da extração (ver abaixo)                          |
| `fonte_extracao`    | str  | scraper     | Fonte(s) usadas por campo                                |
| `url_acedida`       | str  | scraper     | URL(s) efetivamente acessadas                            |

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

| Status              | Significado                                            |
| ------------------- | ------------------------------------------------------ |
| `ok_completo`       | Título + resumo + palavras-chave extraídos com sucesso |
| `ok_parcial`        | Pelo menos um campo extraído, mas não todos            |
| `nada_encontrado`   | Página acessada, nenhum dado encontrado                |
| `erro_extracao`     | Falha de acesso (ex: HTTP 404, timeout)                |
| `erro_pid_invalido` | PID fora do padrão esperado                            |

### Fontes de extração (`fonte_extracao`)

| Valor                                       | Significado                            |
| ------------------------------------------- | -------------------------------------- |
| `articlemeta_isis[T]`                       | Título via ArticleMeta API (ISIS-JSON) |
| `articlemeta_isis[R]`                       | Resumo via ArticleMeta API             |
| `articlemeta_isis[K]`                       | Palavras-chave via ArticleMeta API     |
| `Titulo_PT←pag1_meta_tags`                  | Título via meta tags da URL legacy     |
| `Titulo_PT←pag1_html_body`                  | Título via corpo HTML da URL legacy    |
| `Resumo_PT←pag_pt_meta_tags`                | Resumo via meta tags da versão PT      |
| `Resumo_PT←pag_pt_html_body`                | Resumo via corpo HTML da versão PT     |
| `Palavras_Chave_PT←pag_pt_meta_tags`        | Keywords via meta tags da versão PT    |
| `Palavras_Chave_PT←pag_aop_ogurl_meta_tags` | Keywords via og:url (AoP)              |

### Nomenclatura de arquivos e pastas

| Padrão                   | Exemplo                                                  | Gerado por        |
| ------------------------ | -------------------------------------------------------- | ----------------- |
| `sc_<ts>.csv`                    | `sc_20260411_143022.csv`                                 | scielo_search.py  |
| `sc_<ts>_params.json`            | `sc_20260411_143022_params.json`                         | scielo_search.py  |
| `<stem>_s_<ts>_<modo>/`          | `sc_20260411_s_20260411_150312_api+html/`                | scielo_scraper.py |
| `runs/<ano>/`                    | `runs/2024/`                                             | run_pipeline.py   |
| `pipeline_<ts>.log`              | `pipeline_20260501_143022.log`                           | run_pipeline.py   |
| `pipeline_stats.json`            | `pipeline_stats.json`                                    | run_pipeline.py   |
| `terms_<ts>.csv`                 | `terms_20260415_161055.csv`                              | terms_matcher.py  |
| `terms_<ts>.log`                 | `terms_20260415_161055.log`                              | terms_matcher.py  |
| `terms_<ts>_stats.json`          | `terms_20260415_161055_stats.json`                       | terms_matcher.py  |
| `results_<stem>/`                | `results_sc_20260418_132349_s_20260418_132356_api+html/` | results_report.py |
| `results_<ano_min>-<ano_max>/`   | `results_2021-2025/` (dentro de `runs/`)                 | results_report.py (multi-ano) |
| `results_text_<lang>.md`         | `results_text_pt.md`, `results_text_en.md`               | results_report.py |
| `results_report.json`            | `results_report.json`                                    | results_report.py |
| `wordcloud_<campo>_<lang>_<ts>.png` | `wordcloud_title_ptbr_20260501_120000.png`            | scielo_wordcloud.py |
| `wordcloud_stats_<ts>.json`      | `wordcloud_stats_20260501_120000.json`                   | scielo_wordcloud.py |
| `prisma_<stem>_<lang>_<ts>.pdf`  | `prisma_sc_..._pt_20260501_120000.pdf`                   | prisma_workflow.py  |
