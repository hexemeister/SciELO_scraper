---
name: scielo-communication
description: Redige seções científicas sobre metodologia e resultados do SciELO Scraper — metodologia de coleta, análise de cobertura, limitações, citações
license: MIT
metadata:
    skill-author: hexemeister
---

# scielo-communication

Skill para comunicação científica no contexto do SciELO Scraper. Conhece o vocabulário, as limitações e os resultados típicos do projeto para redigir textos precisos.

## Quando usar

- Redigir seção de **Metodologia** de coleta de dados
- Redigir seção de **Resultados** com estatísticas do scraper
- Escrever **análise de discrepância** entre modos de extração
- Elaborar **limitações** do método de coleta
- Revisar e melhorar textos científicos sobre o processo

## Vocabulário do projeto

| Termo técnico | Definição para uso em texto |
|---|---|
| PID SciELO | Identificador único de artigo no formato `S` + ISSN + ano + sequência |
| ArticleMeta API | API REST do SciELO para acesso estruturado a metadados via ISIS-JSON |
| Artigo AoP | Artigo Ahead of Print, disponível antes da paginação final; PID com `005` nas posições 14-16 |
| Fallback HTML | Estratégia secundária de extração por scraping da página HTML quando a API não retorna dados |
| Coleção SCL | Coleção brasileira do SciELO (`scielo.br`), com ~552.000 documentos |
| ok_completo | Extração com sucesso de título, resumo e palavras-chave em português |
| ok_parcial | Extração parcial — pelo menos um campo obtido |

## Estrutura padrão para seção de Metodologia

```
### Coleta de dados

Os dados foram coletados utilizando [nome do script] v2.4,
ferramenta desenvolvida para extração sistemática de metadados 
do portal SciELO Brasil (scielo.br).

**Busca:** A identificação dos artigos foi realizada por meio da 
API de busca do SciELO Search, com os termos [termos] nos campos 
título e resumo, limitada ao período [anos]. Foram identificados 
[N] artigos.

**Extração:** Os metadados (título, resumo e palavras-chave em 
português) foram extraídos em dois estágios:
1. Consulta à ArticleMeta REST API (fonte primária, cobertura ~94%)
2. Scraping HTML da página do artigo como fallback automático

**Taxa de sucesso:** [X]% dos artigos tiveram extração completa 
(`ok_completo`), [Y]% extração parcial (`ok_parcial`) e [Z]% 
resultaram em erro de extração.
```

## Estrutura padrão para análise de discrepância

```markdown
## Análise de Discrepância

**Corpus:** [N] artigos SciELO Brasil ([ano]), termos: [termos]

### Resumo executivo

| Modo | ok_completo | ok_parcial | erro | Tempo |
|---|---|---|---|---|
| padrão (api+html) | X% | Y% | Z% | Xm |
| apenas-api | X% | Y% | Z% | Xm |
| apenas-html | X% | Y% | Z% | Xm |

### Artigos AoP

Dos [N] artigos com erro no modo apenas-api, [X]% eram AoP 
(PID com `005` nas posições 14-16). Esses artigos não são 
indexados pela ArticleMeta API e requerem scraping HTML.

### Conclusão

O modo padrão (api+html) oferece o melhor custo-benefício:
cobertura equivalente ao modo html com tempo próximo ao modo api.
```

## Frases de limitação padrão

Para incluir na seção de limitações:

- "A extração foi limitada a metadados disponíveis publicamente no portal SciELO Brasil, sem acesso ao texto completo dos artigos."
- "Artigos Ahead of Print (AoP) não estão indexados na ArticleMeta API e dependem de scraping HTML, sujeito a variações de estrutura da página."
- "A coleta foi realizada em [data], podendo não refletir atualizações posteriores nos metadados dos artigos."
- "Artigos sem resumo ou palavras-chave em português no portal SciELO foram classificados como `ok_parcial` ou `nada_encontrado`, independentemente de versões em outros idiomas."

## Boas práticas

- Sempre reportar a versão do script (v2.4) e a data da coleta
- Citar o modo de extração usado (`api+html`, `apenas-api` ou `apenas-html`)
- Reportar total, ok_completo (%), ok_parcial (%), erro (%) e tempo de execução
- Separar a análise de artigos AoP dos regulares quando relevante
- Usar termos em português nos textos: "extração completa", "extração parcial", "erro de extração"
