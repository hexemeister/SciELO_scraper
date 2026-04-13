---
name: scielo-methodology
description: Apoia decisões metodológicas no SciELO Scraper — design de buscas, seleção de termos, interpretação de cobertura, hipóteses sobre falhas de extração
license: MIT
metadata:
    skill-author: hexemeister
---

# scielo-methodology

Skill para raciocínio metodológico no contexto do SciELO Scraper. Ajuda a tomar decisões sobre design de buscas, interpretar resultados e formular hipóteses sobre comportamentos do scraper.

## Quando usar

- Decidir quais termos usar na busca (`scielo_search.py`)
- Escolher o modo de extração adequado para o objetivo
- Interpretar taxa de erro e formular hipóteses sobre causas
- Avaliar cobertura de um corpus
- Design de experimentos de benchmarking do scraper
- Decidir como tratar artigos AoP ou bilíngues

## Decisões de design de busca

### Truncamento de termos

| Situação | Recomendação |
|---|---|
| Termos raiz (ex: "avalia", "educa") | Usar truncamento padrão (`avalia$` → avaliação, avaliativo...) |
| Termos exatos (ex: "avaliação somativa") | Usar `--no-truncate` |
| Busca exploratória | Truncamento ativado — maior recall |
| Busca para corpus específico | `--no-truncate` — maior precisão |

### Campos de busca

- `ti` (título) + `ab` (resumo): padrão, boa cobertura
- Só `ti`: corpus mais restrito, maior precisão
- `ti` + `ab` + `kw` (palavras-chave): máximo recall

### Período temporal

- Artigos do ano corrente podem estar incompletos no índice
- AoPs são mais frequentes no ano mais recente
- Para corpora históricos (>3 anos): taxa de AoP tende a ser menor

## Seleção de modo de extração

```
Objetivo: máxima cobertura, tempo não crítico
→ Modo padrão (api+html)

Objetivo: teste rápido, artigos AoP não importam
→ --only-api

Objetivo: API fora do ar, ou validação independente
→ --only-html

Objetivo: corpora grandes (>1000 artigos)
→ api+html com --workers 2 (cuidado: risco de bloqueio)
```

## Interpretação de cobertura

### Taxa de ok_completo esperada por contexto

| Contexto | ok_completo esperado | Principal causa de queda |
|---|---|---|
| Corpus geral Brasil (api+html) | 99-100% | Artigos sem resumo PT |
| Corpus com muitos AoP | 95-99% | AoP sem HTML ainda publicado |
| Apenas API | 93-95% | AoP não indexados na API |
| Apenas HTML | 98-100% | Timeout ou 404 |

### Hipóteses para alta taxa de erro

| Sintoma | Hipótese | Verificação |
|---|---|---|
| Erros concentrados num período | Artigos AoP daquele ano | `df[df.PID_limpo.str[14:17]=="005"]` |
| Erros concentrados numa revista | Migração de domínio ou ISSN | Verificar URL manualmente |
| Erros aleatórios, baixa taxa | Instabilidade do servidor | Reprocessar com `--resume` |
| Erros >10% modo API | Coleção tem muitos AoP | Usar modo padrão |
| `ok_parcial` alto | Artigos em inglês sem PT | Verificar `Language(s)` no CSV |

### Artigos ok_parcial — o que falta tipicamente

- Resumo ausente: artigos de opinião, cartas, editoriais
- Palavras-chave ausentes: artigos mais antigos (<2010) ou editoriais
- Título ausente: raro, indica problema de estrutura HTML

## Hipóteses sobre comportamento do scraper

### Quando formular hipóteses sobre falhas

1. **Taxa de erro > 2%**: investigar padrão nos PIDs com erro
2. **Tempo médio/artigo > 5s**: possível throttling pelo servidor
3. **ok_parcial concentrado em um campo**: problema sistemático de extração
4. **Discrepância entre modos > 3%**: revisar lógica de fallback

### Framework para análise de discrepância

```
1. Identificar artigos que diferem entre modos
2. Classificar por tipo: AoP, bilíngue, editorial, etc.
3. Verificar manualmente 3-5 casos representativos
4. Formular hipótese sobre causa raiz
5. Propor ajuste no scraper ou na busca
```

## Decisões sobre corpus

### Incluir ou excluir artigos ok_parcial

- **Incluir** se o campo extraído é suficiente para o objetivo (ex: só precisa do título)
- **Excluir** se a ausência de resumo inviabiliza a análise (ex: análise textual)
- **Investigar** se ok_parcial > 1% — pode indicar problema sistemático

### Artigos bilíngues

Artigos PT+EN tipicamente têm resumo em ambos os idiomas. Se o scraper retorna só EN:
- Verificar se a página PT está acessível
- Verificar coluna `Language(s)` no CSV de entrada
- Usar `--only-html` que segue o link "Texto (Português)" explicitamente

## Boas práticas

- Documentar sempre: termos, anos, coleção, modo, data da coleta, versão do script
- Guardar o `_params.json` junto com o CSV de busca — reprodutibilidade
- Para corpora de pesquisa: usar checkpoint baixo (`--checkpoint 1`) e `--resume` disponível
- Validar manualmente uma amostra de ~20 artigos antes de usar o corpus
- Comparar ao menos dois modos para corpora críticos
