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
- [0. Instalação](#0-instalação)
- [1. Pipeline completo com run_pipeline.py](#1-pipeline-completo-com-run_pipelinepy)
- [2. Buscando artigos com scielo_search.py](#2-buscando-artigos-com-scielo_searchpy)
- [3. Preparando o CSV de entrada](#3-preparando-o-csv-de-entrada)
- [4. Extraindo metadados com scielo_scraper.py](#4-extraindo-metadados-com-scielo_scraperpy)
- [5. Entendendo os resultados](#5-entendendo-os-resultados)
- [6. Retomando uma execução interrompida](#6-retomando-uma-execução-interrompida)
- [7. Estratégias de extração](#7-estratégias-de-extração)
- [8. Outras coleções SciELO](#8-outras-coleções-scielo)
- [9. Ajustando velocidade e comportamento](#9-ajustando-velocidade-e-comportamento)
- [10. Verificando estatísticas de uma execução anterior](#10-verificando-estatísticas-de-uma-execução-anterior)
- [11. Gráficos de diagnóstico com process_charts.py](#11-gráficos-de-diagnóstico-com-process_chartspy)
- [12. Relatório consolidado com run_pipeline.py --stats-report](#12-relatório-consolidado-com-run_pipelinepy---stats-report)
- [13. Detecção de termos com terms_matcher.py](#13-detecção-de-termos-com-terms_matcherpy)
- [14. Artefatos científicos com results_report.py](#14-artefatos-científicos-com-results_reportpy)
- [15. Nuvem de palavras com scielo_wordcloud.py](#15-nuvem-de-palavras-com-scielo_wordcloudpy)
- [16. Diagrama PRISMA 2020 com prisma_workflow.py](#16-diagrama-prisma-2020-com-prisma_workflowpy)
- [17. Exemplos de artefatos gerados](#17-exemplos-de-artefatos-gerados)
- [18. Problemas comuns](#18-problemas-comuns)
- [19. Dicionário de dados e termos](#19-dicionário-de-dados-e-termos)

---

## Guia rápido de comandos

Use esta tabela para encontrar o comando certo sem precisar ler o manual inteiro.

### Pipeline completo (recomendado)

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Rodar tudo para um ano | `uv run python run_pipeline.py --year 2024` | `runs/2024/` |
| Rodar tudo para vários anos em sequência | `uv run python run_pipeline.py --per-year --year 2022 2023 2024 2025` | `runs/<ano>/` cada um |
| Ver o que seria executado sem rodar | `uv run python run_pipeline.py --year 2024 --dry-run` | — |
| Reutilizar busca já feita | `uv run python run_pipeline.py --year 2024 --skip-search` | `runs/2024/` |
| Reutilizar scraping já feito | `uv run python run_pipeline.py --year 2024 --skip-scrape` | `runs/2024/` |
| Pular análise de discrepância | `uv run python run_pipeline.py --year 2024 --skip-analysis` | `runs/2024/` |
| Pular detecção de termos | `uv run python run_pipeline.py --year 2024 --skip-match` | `runs/2024/` |
| Pular gráficos de processo | `uv run python run_pipeline.py --year 2024 --skip-charts` | `runs/2024/` |
| Pular relatório científico | `uv run python run_pipeline.py --year 2024 --skip-report` | `runs/2024/` |
| Pular wordcloud | `uv run python run_pipeline.py --year 2024 --skip-wordcloud` | `runs/2024/` |
| Pular diagrama PRISMA | `uv run python run_pipeline.py --year 2024 --skip-prisma` | `runs/2024/` |
| PRISMA apenas em português | `uv run python run_pipeline.py --year 2024 --prisma-lang pt` | `runs/2024/` |
| Ver relatório consolidado de todos os anos | `uv run python run_pipeline.py --stats-report` | — |
| Ver versão de todos os scripts | `uv run python run_pipeline.py --versions` | — |
| Preview do que seria removido pelo reset | `uv run python run_pipeline.py --reset-working-tree --dry-run` | — |
| Resetar working tree | `uv run python run_pipeline.py --reset-working-tree` | — |

### Busca de artigos

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Buscar artigos com termos e anos | `uv run python scielo_search.py --terms avalia educa --years 2022-2025` | Diretório atual |
| Buscar em outra coleção | `uv run python scielo_search.py --terms avalia educa --years 2022-2025 --collection arg` | Diretório atual |
| Buscar sem truncamento | `uv run python scielo_search.py --terms avaliação educação --no-truncate` | Diretório atual |
| Ver parâmetros da última busca | `uv run python scielo_search.py --show-params` | — |
| Listar todas as coleções disponíveis | `uv run python scielo_search.py --list-collections` | — |

### Scraping de artigos

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Extrair título, resumo e keywords | `uv run python scielo_scraper.py sc_<ts>.csv` | `sc_<ts>_s_<ts>_api+html/` |
| Extrair apenas via API | `uv run python scielo_scraper.py sc_<ts>.csv --only-api` | `sc_<ts>_s_<ts>_api/` |
| Extrair apenas via HTML | `uv run python scielo_scraper.py sc_<ts>.csv --only-html` | `sc_<ts>_s_<ts>_html/` |
| Retomar execução interrompida | `uv run python scielo_scraper.py sc_<ts>.csv --resume` | Pasta existente |
| Ver estatísticas de execução anterior | `uv run python scielo_scraper.py sc_<ts>.csv --stats-report` | — |

### Detecção de termos

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Detectar termos em todos os anos | `uv run python terms_matcher.py` | Diretório atual |
| Anos específicos | `uv run python terms_matcher.py --years 2022 2024` | Diretório atual |
| Alterar campos do `criterio_ok` | `uv run python terms_matcher.py --required-fields titulo resumo keywords` | Diretório atual |
| Exigir qualquer termo (não todos) | `uv run python terms_matcher.py --match-mode any` | Diretório atual |

### Gráficos de diagnóstico do processo

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Gerar gráficos a partir de `runs/` | `uv run python process_charts.py` | Diretório atual |
| Anos específicos | `uv run python process_charts.py --years 2022 2024` | Diretório atual |
| Salvar em outra pasta | `uv run python process_charts.py --output graficos/` | `graficos/` |
| Gráfico agregado comparando todos os anos | `uv run python process_charts.py --base runs/ --output runs/` | `runs/` |
| Gráficos em inglês | `uv run python process_charts.py --lang en` | Diretório atual |
| Todos os idiomas | `uv run python process_charts.py --lang all` | Diretório atual |

### Artefatos científicos (resultados)

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Gerar todos os artefatos | `uv run python results_report.py` | `results_<stem>/` |
| Consolidado multi-ano | `uv run python results_report.py --base runs/` | `runs/results_<ano_min>-<ano_max>/` |
| Anos específicos | `uv run python results_report.py --years 2022 2024` | `results_<stem>/` |
| Artefatos em inglês | `uv run python results_report.py --lang en` | `results_<stem>/` |
| Ambos os idiomas | `uv run python results_report.py --lang all` | `results_<stem>/` |
| Pasta de saída explícita | `uv run python results_report.py --output-dir relatorios/` | `relatorios/` |
| Gerar apenas artefatos selecionados | `uv run python results_report.py --artifacts funnel,trend,heatmap` | `results_<stem>/` |
| Pular artefatos específicos | `uv run python results_report.py --skip-artifacts text,report` | `results_<stem>/` |

### Nuvem de palavras

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Auto-descoberta do CSV | `uv run python scielo_wordcloud.py` | Diretório atual |
| CSV explícito | `uv run python scielo_wordcloud.py resultado.csv` | Diretório atual |
| Apenas um campo | `uv run python scielo_wordcloud.py resultado.csv --field abstract` | Diretório atual |
| Todos os artigos extraídos | `uv run python scielo_wordcloud.py resultado.csv --corpus all` | Diretório atual |
| Shape personalizada | `uv run python scielo_wordcloud.py resultado.csv --mask forma.png` | Diretório atual |

### Diagrama PRISMA 2020

| Pergunta / Objetivo | Comando | Onde salva |
| ------------------- | ------- | ---------- |
| Auto-descoberta do JSON | `uv run python prisma_workflow.py` | Diretório do JSON |
| Gerar PDF (campos humanos em branco) | `uv run python prisma_workflow.py results_report.json` | Diretório do JSON |
| Com campos humanos via CLI | `uv run python prisma_workflow.py results_report.json --included 80 --excluded-screening 523` | Diretório do JSON |
| Modo interativo | `uv run python prisma_workflow.py results_report.json -i` | Diretório do JSON |
| PDF em inglês | `uv run python prisma_workflow.py results_report.json --lang en` | Diretório do JSON |
| Exportar template de layout | `uv run python prisma_workflow.py --export-template` | Diretório atual |

---

## 0. Instalação

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

## 1. Pipeline completo com run_pipeline.py

Para a maioria dos usos, o `run_pipeline.py` é o ponto de entrada correto. Ele executa automaticamente todas as etapas em sequência — busca, 3 estratégias de scraping, análise de discrepância, detecção de termos, gráficos, relatório científico, nuvem de palavras e diagrama PRISMA — e organiza tudo em `runs/<ano>/`.

Use os scripts individuais (seções 2–16) quando precisar repetir uma etapa específica, ajustar parâmetros ou depurar.

```bash
# Um ano completo
uv run python run_pipeline.py --year 2024

# Cinco anos, cada um em sua pasta, com gráfico agregado comparando todos
uv run python run_pipeline.py --per-year --year 2021-2025

# Ver os comandos que seriam executados, sem rodar nada
uv run python run_pipeline.py --year 2024 --dry-run
```

O pipeline gera em `runs/<ano>/`:

| Arquivo / Pasta | Conteúdo |
| --------------- | -------- |
| `sc_<ts>.csv` + `sc_<ts>_params.json` | Busca |
| `sc_<ts>_s_<ts>_api+html/` | Scraping modo padrão |
| `sc_<ts>_s_<ts>_api/` | Scraping apenas API |
| `sc_<ts>_s_<ts>_html/` | Scraping apenas HTML |
| `ANALISE_DISCREPANCIA_<ano>.md` | Comparação entre as três estratégias |
| `chart_status.png`, `chart_sources.png`, `chart_time.png` | Diagnóstico do processo |
| `results_<stem>/` | Artefatos científicos (gráficos, tabelas, texto, JSON) |
| `wordcloud_<campo>_<lang>_<ts>.png` | Nuvem de palavras |
| `prisma_<stem>_pt_<ts>.pdf` + `_en_<ts>.pdf` | Diagrama PRISMA |
| `pipeline_<ts>.log` | Log completo da execução |
| `pipeline_stats.json` | Resumo da execução em JSON |

### Flags de controle

```bash
uv run python run_pipeline.py --year 2024 --skip-search       # reutiliza CSV existente
uv run python run_pipeline.py --year 2024 --skip-scrape       # reutiliza scraping existente
uv run python run_pipeline.py --year 2024 --skip-analysis     # pula análise de discrepância
uv run python run_pipeline.py --year 2024 --skip-match        # pula detecção de termos
uv run python run_pipeline.py --year 2024 --skip-charts       # pula gráficos de processo
uv run python run_pipeline.py --year 2024 --skip-report       # pula relatório científico
uv run python run_pipeline.py --year 2024 --skip-wordcloud    # pula nuvem de palavras
uv run python run_pipeline.py --year 2024 --skip-prisma       # pula diagrama PRISMA
uv run python run_pipeline.py --year 2024 --prisma-lang pt    # PRISMA só em PT (default: pt + en)
```

### Manutenção

```bash
uv run python run_pipeline.py --stats-report          # relatório de todas as runs em runs/
uv run python run_pipeline.py --versions              # versão de todos os scripts
uv run python run_pipeline.py --reset-working-tree --dry-run  # preview do que seria removido
uv run python run_pipeline.py --reset-working-tree    # remove tudo gerado (pede confirmação)
```

---

## 2. Buscando artigos com scielo_search.py

Antes de extrair dados com o scraper, é preciso ter uma lista de PIDs. O `scielo_search.py` consulta o SciELO Search e gera um CSV pronto para usar como entrada do scraper.

### Uso básico

```bash
uv run python scielo_search.py --terms avalia educa --years 2022-2025
```

A busca gera dois arquivos:

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

> O campo `versao_searcher` é lido pelo `results_report.py` para enriquecer o texto de Metodologia.

### Truncamento

Por padrão os termos são truncados com `$` — `avalia$` casa com "avaliação", "avaliativo", "avaliações", etc. Para buscar o termo exato:

```bash
uv run python scielo_search.py --terms avaliação educação --no-truncate
```

### Consultar parâmetros de uma busca anterior

```bash
uv run python scielo_search.py --show-params
uv run python scielo_search.py --show-params exemplos/2024/sc_20260413_092345_params.json
```

### Outras coleções

```bash
uv run python scielo_search.py --terms avalia educa --years 2022-2025 --collection arg
uv run python scielo_search.py --list-collections   # lista as 36 coleções disponíveis
```

---

## 3. Preparando o CSV de entrada

O CSV precisa ter obrigatoriamente uma coluna chamada `ID` com os PIDs SciELO.

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

```
S 1982-8837 2022 000 3 00013
│ └── ISSN ┘ └ano┘ └─┘ └seq┘
│                   vol/fasc
└── sempre S
```

PIDs com `-scl` ou `-oai` no final são aceitos — o script remove o sufixo automaticamente.

---

## 4. Extraindo metadados com scielo_scraper.py

### Execução simples

```bash
uv run python scielo_scraper.py minha_lista.csv
```

O script cria automaticamente uma pasta `minha_lista_s_20240101_120000_api+html/` com:

- `resultado.csv` — dados extraídos
- `scraper.log` — log detalhado
- `stats.json` — estatísticas

### Acompanhando o progresso

O progresso aparece no terminal com barra de progresso e logs coloridos:

```
2024-01-01 12:00:05  INFO      ────────────────────────────────────────────
2024-01-01 12:00:05  INFO      Linha CSV 2 | PID: 'S1982-88372022000300013'
2024-01-01 12:00:06  INFO        ✓ Titulo_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✓ Resumo_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✓ Palavras_Chave_PT  via ArticleMeta ISIS
2024-01-01 12:00:06  INFO        ✅ Resultado: T:✓  R:✓  KW:✓  [ok_completo]
```

O sistema é mantido acordado automaticamente durante a execução (`wakepy`) — sem risco de suspensão.

### Checkpoint

Por padrão o CSV é salvo a cada 25 artigos. Para alterar:

```bash
uv run python scielo_scraper.py minha_lista.csv --checkpoint 50   # a cada 50
uv run python scielo_scraper.py minha_lista.csv --checkpoint 1    # após cada artigo
uv run python scielo_scraper.py minha_lista.csv --checkpoint 0    # só no final
```

---

## 5. Entendendo os resultados

### Status de cada artigo

| Status | Significado |
| ------ | ----------- |
| `ok_completo` | Título, resumo e palavras-chave extraídos com sucesso |
| `ok_parcial` | Pelo menos um campo extraído, mas não todos |
| `nada_encontrado` | Página acessada mas sem dados encontrados |
| `erro_extracao` | Falha na extração (ex: página não encontrada) |
| `erro_pid_invalido` | PID não reconhecido como válido |

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

| Valor | Significado |
| ----- | ----------- |
| `articlemeta_isis[T]` | Título via ArticleMeta API |
| `articlemeta_isis[R]` | Resumo via ArticleMeta API |
| `articlemeta_isis[K]` | Palavras-chave via ArticleMeta API |
| `Titulo_PT←pag1_meta_tags` | Título via meta tags HTML |
| `Resumo_PT←pag1_html_body` | Resumo via corpo da página HTML |
| `Palavras_Chave_PT←pag_pt_meta_tags` | Keywords via versão PT da página |

---

## 6. Retomando uma execução interrompida

Se a execução foi interrompida (queda de energia, fechamento do terminal), use `--resume`:

```bash
uv run python scielo_scraper.py minha_lista.csv --resume
```

O script encontra a pasta mais recente, carrega os artigos já processados e continua de onde parou. Artigos com `ok_completo` ou `ok_parcial` não são reprocessados; artigos com erro são reprocessados. O log é anexado com um separador `══ RETOMADA ══` e o tempo acumula.

Para forçar início do zero:

```bash
uv run python scielo_scraper.py minha_lista.csv --no-resume
```

---

## 7. Estratégias de extração

O scraper tem três modos. O padrão (`api+html`) é o recomendado para uso regular.

| Estratégia | ok_completo | Tempo médio | Pasta gerada | Quando usar |
| ---------- | ----------- | ----------- | ------------ | ----------- |
| Padrão (api+html) | 99.4–99.8% | ~24–32 min | `_s_..._api+html/` | Sempre — melhor custo-benefício |
| Apenas API | 98.6–99.2% | ~24–28 min | `_s_..._api/` | Testes rápidos sem AoPs |
| Apenas HTML | 96.8–98.9% | ~33–71 min | `_s_..._html/` | API fora do ar |

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

A coluna **vs. html** mostra a economia de tempo do modo padrão em relação ao `--only-html`. O modo `--only-html` chegou a 71 min em 2024 e apresentou até 3,0% de erros em 2021. O modo `--only-api` é mais rápido mas perde artigos Ahead of Print (AoP), não indexados na API.

---

## 8. Outras coleções SciELO

Por padrão o script acessa a coleção Brasil (`scl`). Para listar as 36 coleções disponíveis:

```bash
uv run python scielo_search.py --list-collections
```

Para usar outra coleção:

```bash
uv run python scielo_scraper.py lista.csv --collection arg   # Argentina
uv run python scielo_scraper.py lista.csv --collection prt   # Portugal
uv run python scielo_scraper.py lista.csv --collection mex   # México
```

---

## 9. Ajustando velocidade e comportamento

### Delay entre requisições

Por padrão o script espera 1,5s ± 0,5s entre artigos. Para alterar:

```bash
uv run python scielo_scraper.py lista.csv --delay 3.0 --jitter 1.0   # mais lento
uv run python scielo_scraper.py lista.csv --delay 0.5 --jitter 0.2   # mais rápido (use com cuidado)
```

### Processamento paralelo

```bash
uv run python scielo_scraper.py lista.csv --workers 2   # máximo: 4
```

Use com moderação — requisições paralelas em excesso podem resultar em bloqueio temporário pelo servidor.

### Pasta de saída personalizada

```bash
uv run python scielo_scraper.py lista.csv --output-dir resultados/minha_pasta
```

### Log detalhado para depuração

```bash
uv run python scielo_scraper.py lista.csv --log-level DEBUG
```

Mostra cada URL acessada, cada campo encontrado ou não, e o motivo de cada fallback.

---

## 10. Verificando estatísticas de uma execução anterior

```bash
# Com CSV (procura a pasta mais recente automaticamente)
uv run python scielo_scraper.py lista.csv --stats-report

# Com pasta específica
uv run python scielo_scraper.py --stats-report --output-dir resultados/minha_pasta
```

---

## 11. Gráficos de diagnóstico com process_charts.py

Use este script para verificar *como o scraping correu* — taxas de sucesso por estratégia, fontes de extração e tempo. É diagnóstico técnico do processo, não análise dos resultados científicos.

### Uso básico

```bash
uv run python process_charts.py
```

Lê todos os anos em `runs/` e salva três gráficos no diretório atual.

### Gráficos gerados

| Arquivo | O que mostra |
| ------- | ------------ |
| `chart_status.png` | Distribuição de status (`ok_completo`, `ok_parcial`, `erro_extracao`) por modo e ano |
| `chart_sources.png` | Fontes de extração no modo `api+html` por ano: API pura, fallback parcial, fallback total, falha de acesso |
| `chart_time.png` | Tempo total de scraping por modo e ano |
| `chart_stats.json` | Metadados da execução: versão, timestamp, labels, idiomas, arquivos gerados |

### Opções

```bash
uv run python process_charts.py --years 2022 2024            # anos específicos
uv run python process_charts.py --base outra/pasta           # pasta raiz alternativa
uv run python process_charts.py --output graficos/           # pasta de saída
uv run python process_charts.py --stem sc_20260411_143022    # run específico
uv run python process_charts.py --lang en                    # gráficos em inglês
uv run python process_charts.py --lang all                   # todos os idiomas (_pt/_en)
uv run python process_charts.py --no-sources                 # pular gráfico de fontes
uv run python process_charts.py --no-status --no-time        # apenas gráfico de fontes
```

---

## 12. Relatório consolidado com run_pipeline.py --stats-report

Gera um relatório Markdown com as estatísticas de todas as execuções em `runs/`, sem rodar nenhum scraping.

```bash
uv run python run_pipeline.py --stats-report           # imprime no terminal
uv run python run_pipeline.py --stats-report > stats.md  # salva em arquivo
uv run python run_pipeline.py --stats-report outra/pasta # pasta alternativa
```

O relatório inclui, por ano e por modo, total de artigos, distribuição de status, fontes de extração e tempo. Ao final: totais globais.

> `--stats-report` não requer `--year` — funciona de forma standalone.

---

## 13. Detecção de termos com terms_matcher.py

Use este script para saber quais artigos do scraping contêm os termos de busca em cada campo (título, resumo, palavras-chave) e gerar o `criterio_ok` que alimenta o `results_report.py`. Roda offline — sem requisições à internet.

### Uso básico

```bash
uv run python terms_matcher.py                                              # todos os anos
uv run python terms_matcher.py --years 2022 2024                           # anos específicos
uv run python terms_matcher.py --terms avalia educa fisica --years 2024    # termos personalizados
uv run python terms_matcher.py --required-fields titulo resumo keywords    # alterar campos do criterio_ok
uv run python terms_matcher.py --stats-report                              # relatório do último run
```

### Colunas adicionadas ao CSV

| Coluna | Tipo | Descrição |
| ------ | ---- | --------- |
| `n_palavras_titulo` | int | Nº de palavras no Titulo_PT |
| `n_palavras_resumo` | int | Nº de palavras no Resumo_PT |
| `n_keywords_pt` | int | Nº de keywords separadas por ";" |
| `<termo>_titulo` | bool | Termo encontrado em Titulo_PT |
| `<termo>_resumo` | bool | Termo encontrado em Resumo_PT |
| `<termo>_keywords` | bool | Termo encontrado em Palavras_Chave_PT |
| `criterio_ok` | bool | Todos os termos em pelo menos um dos `--required-fields` |

> ⚠ O nº de colunas booleanas cresce com T termos × 3 campos. Padrão (2 termos): 6 colunas. Com 5 termos: 15 colunas.
> As colunas booleanas cobrem sempre os 3 campos; o `criterio_ok` avalia apenas os `--required-fields` (padrão: titulo e keywords).

### Saídas geradas

| Arquivo | Conteúdo |
| ------- | -------- |
| `terms_<ts>.csv` | CSV consolidado com colunas originais + novas |
| `terms_<ts>.log` | Log detalhado da execução |
| `terms_<ts>_stats.json` | Estatísticas por ano e globais |

### Opções completas

```bash
uv run python terms_matcher.py --years 2022 2024                 # anos específicos
uv run python terms_matcher.py --terms avalia educa              # termos
uv run python terms_matcher.py --required-fields titulo keywords # campos do criterio_ok
uv run python terms_matcher.py --match-mode any                  # qualquer termo satisfaz (default: all)
uv run python terms_matcher.py --no-truncate                     # não remover $ dos termos
uv run python terms_matcher.py --mode api                        # modo alternativo (default: api+html)
uv run python terms_matcher.py --base outra/pasta                # pasta base alternativa
uv run python terms_matcher.py --output saida.csv                # nome de saída
uv run python terms_matcher.py --log-level DEBUG                 # log detalhado
```

---

## 14. Artefatos científicos com results_report.py

Gera o conjunto completo de artefatos publication-ready a partir do `terms_*.csv` do `terms_matcher.py`. O foco é nos **resultados** — o que foi encontrado — não em como o processo técnico correu.

### Uso básico

```bash
uv run python results_report.py                            # todos os anos, api+html, PT
uv run python results_report.py --years 2022 2023 2024    # anos específicos
uv run python results_report.py --base runs/              # consolidado multi-ano
uv run python results_report.py --lang all                # PT + EN
```

### Modo consolidado (`--base runs/`)

Quando `--base` aponta para uma pasta com múltiplos anos, o script agrega todos os dados num único conjunto de artefatos com visão de série temporal completa: funil por ano lado a lado, trend de evolução, heatmap e ranking de periódicos sobre o corpus total. A pasta de saída é `runs/results_<ano_min>-<ano_max>/` (ex: `runs/results_2021-2025/`).

### Artefatos gerados

**Gráficos:**

| Arquivo | O que mostra |
| ------- | ------------ |
| `results_funnel.png` | Total buscado → scrapeado → criterio_ok, por ano |
| `results_trend.png` | Evolução temporal de criterio_ok: n e % por ano |
| `results_terms_heatmap.png` | Frequência de cada termo por campo (base: criterio_ok) |
| `results_journals.png` | Top N periódicos com mais artigos criterio_ok |
| `results_coverage.png` | % de artigos com cada campo PT presente, por ano |
| `results_venn[_en].png` | Sobreposição de termos por campo (Venn ≤3 termos ou UpSet ≥4) |

**Tabelas:**

| Arquivo | Conteúdo |
| ------- | -------- |
| `results_table_summary.csv` | Funil por ano: buscado, scrapeado, criterio_ok n e % |
| `results_table_terms.csv` | Por termo × campo: n e % (base: criterio_ok) |
| `results_table_journals.csv` | Todos os periódicos com contagem e % |

**Texto e metadados:**

| Arquivo | Conteúdo |
| ------- | -------- |
| `results_text_pt.md` | Metodologia, Resultados, Limitações e descrição de figuras prontos para publicação |
| `results_text_en.md` | Idem em inglês (com `--lang en` ou `--lang all`) |
| `results_report.json` | Todos os dados calculados — para consulta, reúso ou integração |

> O arquivo de texto sempre usa sufixo de idioma (`_pt` ou `_en`). Não existe `results_text.md` sem sufixo.

### Opções completas

```bash
uv run python results_report.py --base outra/pasta           # pasta raiz alternativa
uv run python results_report.py --years 2022 2024            # anos específicos
uv run python results_report.py --mode api                   # estratégia alternativa
uv run python results_report.py --scrape-dir sc_<ts>_s_<ts>_api+html/  # pasta direta
uv run python results_report.py --output-dir relatorios/     # pasta de saída
uv run python results_report.py --lang pt|en|all             # idioma dos artefatos
uv run python results_report.py --top-journals 20            # top 20 periódicos (default: 15)
uv run python results_report.py --style seaborn-v0_8         # estilo matplotlib
uv run python results_report.py --colormap plasma            # colormap do heatmap (default: viridis)
uv run python results_report.py --artifacts funnel,trend     # gerar apenas estes
uv run python results_report.py --skip-artifacts text,report # pular estes
uv run python results_report.py --dry-run                    # simula sem gravar
uv run python results_report.py --show-report                # exibe JSON existente no terminal
uv run python results_report.py --help-artifacts             # lista todos os artefatos
uv run python results_report.py --help-artifact results_funnel  # detalhe de um artefato
uv run python results_report.py --list-styles                # estilos disponíveis
uv run python results_report.py --list-colormaps             # colormaps disponíveis
```

**Aliases de artefatos** (para `--artifacts` e `--skip-artifacts`):

| Alias | Artefato |
| ----- | -------- |
| `funnel` | `results_funnel` |
| `trend` | `results_trend` |
| `heatmap` | `results_terms_heatmap` |
| `journals` | `results_journals` |
| `coverage` | `results_coverage` |
| `venn` | `results_venn` |
| `text` | `results_text` |
| `table_summary` | `results_table_summary` |
| `table_terms` | `results_table_terms` |
| `table_journals` | `results_table_journals` |
| `report` | `results_report` |

---

## 15. Nuvem de palavras com scielo_wordcloud.py

Gera nuvens de palavras a partir do `resultado.csv` do scraping. Útil para visualizar os termos mais frequentes em títulos, resumos ou palavras-chave.

### Uso básico

```bash
uv run python scielo_wordcloud.py                             # auto-descobre o resultado.csv
uv run python scielo_wordcloud.py sc_ts_s_ts_api+html/resultado.csv
uv run python scielo_wordcloud.py resultado.csv --field abstract
uv run python scielo_wordcloud.py resultado.csv --corpus all  # todos os artigos, não só criterio_ok
```

> **Auto-descoberta:** o script busca `resultado.csv` no diretório atual → `*_s_*_api+html/` → `*_s_*_api/` → `runs/*/`. Com múltiplos candidatos, usa o mais recente e avisa.

### Opções principais

```bash
uv run python scielo_wordcloud.py resultado.csv --field title          # title | abstract | keywords (default: title+keywords)
uv run python scielo_wordcloud.py resultado.csv --field title+abstract # múltiplos campos
uv run python scielo_wordcloud.py resultado.csv --field all            # todos os campos
uv run python scielo_wordcloud.py resultado.csv --lang pt-br           # idioma das stopwords (default: pt-br)
uv run python scielo_wordcloud.py resultado.csv --stopwords extra.txt  # stopwords adicionais
uv run python scielo_wordcloud.py resultado.csv --no-domain-stopwords  # desativa stopwords acadêmicas
uv run python scielo_wordcloud.py resultado.csv --mask forma.png       # shape personalizada
uv run python scielo_wordcloud.py resultado.csv --width 1200           # largura em pixels (default: 800)
uv run python scielo_wordcloud.py resultado.csv --colormap plasma      # colormap (default: viridis)
uv run python scielo_wordcloud.py resultado.csv --max-words 100        # máx. palavras (default: 200)
uv run python scielo_wordcloud.py resultado.csv --output-dir graficos/ # pasta de saída
uv run python scielo_wordcloud.py resultado.csv --dry-run              # config sem gerar arquivos
uv run python scielo_wordcloud.py --list-langs                         # idiomas NLTK disponíveis
uv run python scielo_wordcloud.py --list-colormaps                     # colormaps disponíveis
```

### Saída

- `wordcloud_{campo}_{lang}_{ts}.png` — uma imagem por campo processado
- `wordcloud_stats_{ts}.json` — metadados: campo, idioma, corpus, colormap, n artigos, palavras mais frequentes

### Stopwords

O script combina três fontes por padrão:

1. **NLTK** — lista geral do idioma (português: 207 palavras). Baixada automaticamente na primeira execução.
2. **Domínio acadêmico** — termos do contexto SciELO/avaliação (ex: "artigo", "estudo", "resultado"). Desative com `--no-domain-stopwords`.
3. **Arquivo personalizado** — via `--stopwords ARQ` (uma palavra por linha, ou CSV com coluna `word`).

### Validação de CSV

Se as colunas esperadas não existirem, o script exibe as colunas encontradas e indica o comando para gerar o arquivo correto.

---

## 16. Diagrama PRISMA 2020 com prisma_workflow.py

Gera um PDF A4 preenchível com o Diagrama de Fluxo PRISMA 2020. A fase de **Identificação** é auto-preenchida a partir do `results_report.json`. As fases de **Triagem** e **Inclusão** ficam como campos AcroForm editáveis para preenchimento após curadoria humana.

> O pipeline automatiza apenas a fase de Identificação. Triagem e Inclusão dependem de revisão humana.

### Uso básico

```bash
uv run python prisma_workflow.py                                              # auto-descobre o JSON
uv run python prisma_workflow.py runs/2026/results_*/results_report.json     # JSON explícito
uv run python prisma_workflow.py results_report.json --included 80 --excluded-screening 523
uv run python prisma_workflow.py results_report.json -i                      # modo interativo
uv run python prisma_workflow.py results_report.json --human-data campos.json
```

> **Auto-descoberta:** busca no diretório atual → `runs/*/results_*/` → `results_*/`. Com múltiplos candidatos, lista as opções.

### Campos auto-preenchidos (fase de Identificação)

| Campo | Fonte |
| ----- | ----- |
| Total buscado (n) | `total_buscado` do JSON |
| Registros para triagem (n) | Calculado: buscado − duplicatas − automação − erros |
| Registros de automação (n) | Artigos inelegíveis automaticamente |
| Erros/outros (n) | `erro_extracao` + `erro_pid_invalido` |
| Incluídos (sugestão) | `criterio_ok` (editável no PDF) |

### Campos humanos (Triagem e Inclusão)

Preencher no PDF após curadoria, ou passar via CLI/arquivo:

| Flag | Campo PRISMA |
| ---- | ------------ |
| `--duplicates N` | Registros duplicados removidos |
| `--sought N` | Relatórios buscados para recuperação |
| `--not-retrieved N` | Relatórios não recuperados |
| `--assessed N` | Relatórios avaliados para elegibilidade |
| `--excluded-screening N` | Registros excluídos na triagem |
| `--excluded-eligibility N` | Relatórios excluídos por elegibilidade |
| `--included N` | Estudos incluídos na revisão |
| `--included-reports N` | Relatórios dos estudos incluídos |

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

### Opções completas

```bash
uv run python prisma_workflow.py results_report.json --lang en          # PDF em inglês
uv run python prisma_workflow.py results_report.json --output-dir pdfs/ # pasta de saída
uv run python prisma_workflow.py results_report.json --dry-run          # dados sem gerar PDF
uv run python prisma_workflow.py --export-template                      # exportar layout para assets/PRISMAdiagram.json
uv run python prisma_workflow.py --export-template meu_layout.json      # caminho específico
```

> **Layout customizável:** use `--export-template` para exportar o template como JSON e modificá-lo. Se `assets/PRISMAdiagram.json` existir, sobrepõe o layout padrão embutido.

Todos os campos `n =` são AcroForm editáveis no PDF, abrível em Acrobat Reader, Edge, Foxit ou LibreOffice.

---

## 17. Exemplos de artefatos gerados

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

Com o modo consolidado (`--base runs/`), o ranking muda com 5 anos agregados (n=370): a *Revista Brasileira de Educação Médica* sobe para 1º lugar com 50 artigos (13,5%), presença distribuída que não se destaca em nenhum ano isolado.

![Periódicos](exemplos/results_journals_pt.png)

### Nuvem de palavras — `scielo_wordcloud.py`

Gerada a partir das palavras-chave do corpus `criterio_ok`. Domínio de *saúde*, *educação* e *enfermagem* — revela o perfil temático do corpus de forma imediata.

![Wordcloud de palavras-chave](exemplos/wordcloud_keywords.png)

### Diagrama PRISMA 2020 — `prisma_workflow.py`

PDF A4 preenchível com a fase de Identificação auto-preenchida (n=553, triagem=552, incluídos sugeridos=85). As fases de Triagem e Inclusão ficam como campos AcroForm editáveis para curadoria humana.

![Diagrama PRISMA](exemplos/prisma_preview.png)

### Texto publication-ready — `results_report.py`

O `results_text_pt.md` entrega seções prontas para submissão. Exemplo da seção de Metodologia (2024):

> *"A busca bibliográfica, conduzida em 5 de maio de 2026, foi realizada na plataforma SciELO Brasil por meio do SciELO Search, utilizando os termos "avalia" e "educa" com truncamento automático (operador $), nos campos de título e resumo, abrangendo o ano de 2024. Foram recuperados 553 registros. [...] A etapa de filtragem automática verificou a presença simultânea de todos os termos em pelo menos um dos campos requeridos (título e palavras-chave), identificando 85 artigos (15,4%) como potencialmente relevantes para curadoria humana."*

O arquivo inclui ainda: nota técnica com URL da busca, Resultados, Limitações, e descrição de cada figura em versão curta (legenda) e longa (substituto textual para publicações sem imagens).

---

## 18. Problemas comuns

### "PID inválido"

O PID não segue o padrão esperado. Verifique se a coluna `ID` contém PIDs no formato correto (ex: `S1982-88372022000300013`). PIDs com `-scl` ou `-oai` são aceitos.

### Muitos `erro_extracao` em artigos AoP

Artigos Ahead of Print têm `005` nas posições 14–16 do PID. A ArticleMeta API não retorna dados para eles — o modo padrão (`api+html`) resolve automaticamente via scraping HTML.

### Script lento ou timeout frequente

O servidor do SciELO pode estar lento. Tente aumentar o timeout:

```bash
uv run python scielo_scraper.py lista.csv --timeout 40
```

### Execução interrompida no meio

Use `--resume` para continuar de onde parou — artigos já processados com sucesso não são reprocessados.

### Artigo com `ok_parcial` — falta resumo ou palavras-chave

Alguns artigos não têm resumo ou palavras-chave em português disponíveis em nenhuma fonte. Verifique a página do artigo manualmente para confirmar.

### Erro de encoding no terminal Windows

```bash
set PYTHONUTF8=1
uv run python scielo_scraper.py lista.csv
```

---

## 19. Dicionário de dados e termos

### Conceitos e terminologia

| Termo | Definição |
| ----- | --------- |
| **PID** | Identificador único SciELO. Formato: `S` + ISSN (9 chars) + ano (4) + volume/fascículo (3) + sequência (5) + dígito verificador (1) + letra de coleção (1). Total: 23 caracteres. Ex: `S1982-88372022000300013`. |
| **ISSN** | International Standard Serial Number — identificador de periódico. Embutido no PID nas posições 1–9 (ex: `1982-8837`). |
| **AoP** | Ahead of Print — artigo publicado online antes de receber volume/fascículo definitivo. Identificado por `005` nas posições 14–16 do PID. Não indexado na ArticleMeta API; extraído apenas via HTML. |
| **Coleção** | Conjunto de periódicos de um país ou região na plataforma SciELO. Identificada por código de 3 letras (ex: `scl` = Brasil, `arg` = Argentina, `prt` = Portugal). |
| **ISIS-JSON** | Formato de resposta da ArticleMeta API, derivado do banco de dados CDS/ISIS usado pelo SciELO internamente. Contém os campos do artigo em múltiplos idiomas. |
| **Truncamento** | Adição de `$` ao final de um termo de busca para casar com variações morfológicas. Ex: `avalia$` casa com "avalia", "avaliação", "avaliativo". Ativo por padrão no `scielo_search.py`; removido automaticamente no `terms_matcher.py`. |
| **criterio_ok** | Coluna booleana do `terms_matcher.py`: `True` se todos os termos aparecerem em pelo menos um dos `--required-fields` (padrão: titulo ou keywords). |
| **campo required** | Campo(s) considerados no cálculo de `criterio_ok`. Cada termo deve aparecer em pelo menos um deles. Padrão: `titulo` e `keywords`. |
| **fallback HTML** | Estratégia secundária: quando a API não retorna um campo, o scraper acessa a página HTML do artigo para extraí-lo via meta tags ou corpo. |

### Colunas do resultado.csv (scielo_scraper.py)

| Coluna | Tipo | Origem | Descrição |
| ------ | ---- | ------ | --------- |
| `ID` | str | CSV entrada | PID bruto conforme fornecido |
| `Title` | str | CSV entrada | Título conforme indexado no SciELO Search |
| `Author(s)` | str | CSV entrada | Autores |
| `Source` | str | CSV entrada | Abreviatura do periódico |
| `Journal` | str | CSV entrada | Nome completo do periódico |
| `Language(s)` | str | CSV entrada | Idioma(s) do artigo |
| `Publication year` | int | CSV entrada | Ano de publicação |
| `PID_limpo` | str | scraper | PID normalizado (sufixos removidos, validado) |
| `URL_PT` | str | scraper | URL da versão em português consultada |
| `Titulo_PT` | str | scraper | Título em português extraído |
| `Resumo_PT` | str | scraper | Resumo em português extraído |
| `Palavras_Chave_PT` | str | scraper | Palavras-chave em português, separadas por `;` |
| `status` | str | scraper | Status da extração (ver abaixo) |
| `fonte_extracao` | str | scraper | Fonte(s) usadas por campo |
| `url_acedida` | str | scraper | URL(s) efetivamente acessadas |

### Colunas adicionadas pelo terms_matcher.py

| Coluna | Tipo | Descrição |
| ------ | ---- | --------- |
| `n_palavras_titulo` | int | Nº de palavras em Titulo_PT |
| `n_palavras_resumo` | int | Nº de palavras em Resumo_PT |
| `n_keywords_pt` | int | Nº de keywords em Palavras_Chave_PT (separador `;`) |
| `<termo>_titulo` | bool | Termo detectado em Titulo_PT (case-insensitive, substring) |
| `<termo>_resumo` | bool | Termo detectado em Resumo_PT |
| `<termo>_keywords` | bool | Termo detectado em Palavras_Chave_PT |
| `criterio_ok` | bool | Todos os termos presentes em ≥1 campo required |

### Status de extração

| Status | Significado |
| ------ | ----------- |
| `ok_completo` | Título + resumo + palavras-chave extraídos com sucesso |
| `ok_parcial` | Pelo menos um campo extraído, mas não todos |
| `nada_encontrado` | Página acessada, nenhum dado encontrado |
| `erro_extracao` | Falha de acesso (ex: HTTP 404, timeout) |
| `erro_pid_invalido` | PID fora do padrão esperado |

### Fontes de extração (`fonte_extracao`)

| Valor | Significado |
| ----- | ----------- |
| `articlemeta_isis[T]` | Título via ArticleMeta API (ISIS-JSON) |
| `articlemeta_isis[R]` | Resumo via ArticleMeta API |
| `articlemeta_isis[K]` | Palavras-chave via ArticleMeta API |
| `Titulo_PT←pag1_meta_tags` | Título via meta tags da URL legacy |
| `Titulo_PT←pag1_html_body` | Título via corpo HTML da URL legacy |
| `Resumo_PT←pag_pt_meta_tags` | Resumo via meta tags da versão PT |
| `Resumo_PT←pag_pt_html_body` | Resumo via corpo HTML da versão PT |
| `Palavras_Chave_PT←pag_pt_meta_tags` | Keywords via meta tags da versão PT |
| `Palavras_Chave_PT←pag_aop_ogurl_meta_tags` | Keywords via og:url (AoP) |

### Nomenclatura de arquivos e pastas

| Padrão | Exemplo | Gerado por |
| ------ | ------- | ---------- |
| `sc_<ts>.csv` | `sc_20260411_143022.csv` | scielo_search.py |
| `sc_<ts>_params.json` | `sc_20260411_143022_params.json` | scielo_search.py |
| `<stem>_s_<ts>_<modo>/` | `sc_20260411_s_20260411_150312_api+html/` | scielo_scraper.py |
| `runs/<ano>/` | `runs/2024/` | run_pipeline.py |
| `pipeline_<ts>.log` | `pipeline_20260501_143022.log` | run_pipeline.py |
| `pipeline_stats.json` | `pipeline_stats.json` | run_pipeline.py |
| `terms_<ts>.csv` | `terms_20260415_161055.csv` | terms_matcher.py |
| `terms_<ts>.log` | `terms_20260415_161055.log` | terms_matcher.py |
| `terms_<ts>_stats.json` | `terms_20260415_161055_stats.json` | terms_matcher.py |
| `results_<stem>/` | `results_sc_20260418_..._api+html/` | results_report.py |
| `results_<ano_min>-<ano_max>/` | `results_2021-2025/` (dentro de `runs/`) | results_report.py (multi-ano) |
| `results_text_<lang>.md` | `results_text_pt.md`, `results_text_en.md` | results_report.py |
| `results_report.json` | `results_report.json` | results_report.py |
| `wordcloud_<campo>_<lang>_<ts>.png` | `wordcloud_title_ptbr_20260501_120000.png` | scielo_wordcloud.py |
| `wordcloud_stats_<ts>.json` | `wordcloud_stats_20260501_120000.json` | scielo_wordcloud.py |
| `prisma_<stem>_<lang>_<ts>.pdf` | `prisma_sc_..._pt_20260501_120000.pdf` | prisma_workflow.py |
