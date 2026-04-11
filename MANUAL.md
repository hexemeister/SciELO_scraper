# Manual do Usuário — SciELO Scraper v2.4

## Sumário

1. [Instalação](#1-instalação)
2. [Preparando o CSV de entrada](#2-preparando-o-csv-de-entrada)
3. [Rodando o script](#3-rodando-o-script)
4. [Entendendo os resultados](#4-entendendo-os-resultados)
5. [Retomando uma execução interrompida](#5-retomando-uma-execução-interrompida)
6. [Estratégias de extração](#6-estratégias-de-extração)
7. [Outras coleções SciELO](#7-outras-coleções-scielo)
8. [Ajustando velocidade e comportamento](#8-ajustando-velocidade-e-comportamento)
9. [Verificando estatísticas de uma execução anterior](#9-verificando-estatísticas-de-uma-execução-anterior)
10. [Problemas comuns](#10-problemas-comuns)

---

## 1. Instalação

### Pré-requisitos

- Python 3.9 ou superior
- [uv](https://github.com/astral-sh/uv) instalado

### Instalar dependências

```bash
uv pip install requests beautifulsoup4 lxml pandas tqdm wakepy brotli
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

O script cria automaticamente uma pasta de saída chamada `minha_lista_new_20240101_120000/` (com data e hora) contendo:

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

---

## 4. Entendendo os resultados

### Status de cada artigo

| Status | Significado |
|---|---|
| `ok_completo` | Título, resumo e palavras-chave extraídos com sucesso |
| `ok_parcial` | Pelo menos um campo extraído, mas não todos |
| `nada_encontrado` | Página acessada mas sem dados encontrados |
| `erro_extracao` | Falha na extração (ex: página não encontrada) |
| `erro_pid_invalido` | PID não reconhecido como válido |

### Relatório final

Ao terminar, o script imprime um resumo:

```
==============================================================
  ESTATÍSTICAS FINAIS  (script v2.4)
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
|---|---|
| `articlemeta_isis[T]` | Título via ArticleMeta API |
| `articlemeta_isis[R]` | Resumo via ArticleMeta API |
| `articlemeta_isis[K]` | Palavras-chave via ArticleMeta API |
| `Titulo_PT←pag1_meta_tags` | Título via meta tags HTML |
| `Resumo_PT←pag1_html_body` | Resumo via corpo da página HTML |
| `Palavras_Chave_PT←pag_pt_meta_tags` | Keywords via versão PT da página |

---

## 5. Retomando uma execução interrompida

Se a execução foi interrompida (queda de energia, fechamento do terminal, etc.), use `--resume`:

```bash
uv run python scielo_scraper.py minha_lista.csv --resume
```

O script encontra automaticamente a execução anterior mais recente, carrega os artigos já processados com sucesso e continua a partir de onde parou.

### Como funciona o resume

- O script procura a pasta `minha_lista_new_*/` mais recente no mesmo diretório do CSV
- Carrega apenas artigos com status `ok_completo` ou `ok_parcial`
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

Usa a ArticleMeta API como fonte primária e o scraping HTML como fallback automático. Melhor resultado com menor tempo.

### Apenas API

```bash
uv run python scielo_scraper.py minha_lista.csv --only-api
```

Mais rápido, mas perde artigos Ahead of Print (AoP) — a API não retorna dados para eles. Recomendado apenas para testes ou quando a cobertura de AoPs não for importante.

### Apenas HTML

```bash
uv run python scielo_scraper.py minha_lista.csv --only-html
```

Mais lento (~10 min a mais para 564 artigos), mas útil quando a API estiver fora do ar. Recupera praticamente os mesmos artigos que o modo padrão.

### Comparativo

| Estratégia | Cobertura | Tempo (564 artigos) | Quando usar |
|---|---|---|---|
| Padrão (api+html) | 99.6% | ~26 min | Sempre — melhor custo-benefício |
| Apenas HTML | 99.5% | ~36 min | API fora do ar |
| Apenas API | 93.8% | ~26 min | Testes rápidos sem AoPs |

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

## 10. Problemas comuns

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

Use `--resume` para continuar de onde parou — os artigos já processados com sucesso não são reprocessados.

### Artigo com `ok_parcial` — falta resumo ou palavras-chave

Alguns artigos genuinamente não têm resumo ou palavras-chave em português disponíveis em nenhuma fonte (API nem HTML). Verifique a página do artigo manualmente para confirmar.

### Erro de encoding no terminal Windows

Se aparecerem caracteres estranhos no terminal, defina a variável de ambiente antes de rodar:

```bash
set PYTHONUTF8=1
uv run python scielo_scraper.py lista.csv
```
