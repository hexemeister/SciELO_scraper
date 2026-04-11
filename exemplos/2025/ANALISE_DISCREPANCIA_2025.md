# Análise de Discrepância — API vs Web Scraping (2025)

**Corpus:** 602 artigos SciELO Brasil (2025), coleção `search_20260410_184300.csv`  
**Referência:** execuções comparativas de 2026-04-10/11 (padrão, --only-api, --only-html)

---

## Resumo executivo

| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |
|---|---|---|---|---|---|
| **Padrão** (api+html) | 601 (99,8%) | 1 (0,2%) | 0 | **100,0%** | 27m 10s |
| **--only-api** | 597 (99,2%) | 5 (0,8%) | 0 | **100,0%** | 27m 28s |
| **--only-html** | 596 (99,0%) | 3 (0,5%) | 3 (0,5%) | **99,5%** | 33m 22s |

O corpus de 2025 é de **artigos já indexados** na ArticleMeta — nenhum deles é AoP (PID com `005`). Isso explica o desempenho superior da API em relação ao corpus de 2022 e o comportamento diferente dos modos. O fallback HTML ainda resolve 4 casos; o HTML puro falha em 3 artigos que a API recupera sem problemas.

---

## 1. O que o fallback HTML corrigiu (modo padrão vs. --only-api)

4 artigos passaram de `ok_parcial` para `ok_completo` no modo padrão graças ao HTML:

| PID | Campo faltante na API | Resolvido pelo HTML |
|---|---|---|
| `S1518-29242025000100302` | Título PT | `pag1_meta_tags` |
| `S2176-94512025000500307` | Título PT | `pag1_meta_tags` |
| `S2317-16342025000101005` | Palavras-chave | `pag1_meta_tags` |
| `S1678-69712025000500601` | Palavras-chave | `pag1_meta_tags` |

**Padrão:** API retornava resumo e/ou keywords, mas sem título PT ou sem palavras-chave. O HTML das meta tags `citation_title` e `citation_keywords` completou os campos.

Diferente do corpus de 2022, **nenhum destes é AoP**. O fenómeno é distinto: artigos indexados cujo registo ISIS não inclui a versão PT de determinado campo (provavelmente artigos originalmente em outro idioma com metadados PT incompletos no XML de origem).

---

## 2. O artigo persistentemente parcial (S0104-40362025000300100)

Este artigo permanece `ok_parcial` nos três modos:

| Modo | Campos extraídos | Campos ausentes |
|---|---|---|
| Padrão | Título PT | Resumo, Palavras-chave |
| --only-api | Título PT | Resumo, Palavras-chave |
| --only-html | Título PT | Resumo, Palavras-chave |

O resumo e as palavras-chave não existem em nenhuma fonte. O artigo é um **editorial/apresentação de número especial** — publicações deste tipo frequentemente não têm resumo estruturado nem palavras-chave exigidos.

---

## 3. O que o HTML-only falhou que a API resolveu

3 artigos resultaram em `erro_extracao` no modo `--only-html` mas foram extraídos com sucesso pela API:

| PID | Erro HTML | API |
|---|---|---|
| `S2237-96222025000100272` | 404 na URL legacy | ok_completo |
| `S2317-16342025000101035` | 404 na URL legacy | ok_completo |
| `S0034-71672025000300158` | 404 na URL legacy | ok_completo |

Todos os três retornaram **HTTP 404** na URL `scielo.php?script=sci_arttext&pid=...&lang=pt`. A URL moderna (`/j/ISSN/a/PID/`) pode estar funcional, mas o script HTML-only depende da URL legacy como ponto de entrada. A API não tem essa dependência — acede diretamente ao XML ISIS pelo PID.

Adicionalmente, 1 artigo foi `ok_parcial` no HTML (sem keywords) mas `ok_completo` na API:

| PID | HTML | API |
|---|---|---|
| `S0103-636X2025000100518` | ok_parcial (sem keywords) | ok_completo |

---

## 4. Comparação com o corpus de 2022

| Dimensão | 2022 (564 artigos) | 2025 (602 artigos) |
|---|---|---|
| Principal causa de falha --only-api | AoP não indexados (28 casos) | Metadados PT incompletos no ISIS (4 casos) |
| AoPs no corpus | ~29 (5%) | **0** |
| Ganho do fallback HTML | +27 artigos (5%) | +4 artigos (0,7%) |
| Falhas do --only-html | 1 (404 legítimo) | 3 (404 URLs legacy) |
| Modo padrão vs. --only-api | +5,8 pp de ok_completo | +0,6 pp de ok_completo |

O corpus de 2025 é mais homogéneo: todos os artigos já estão atribuídos a fascículos regulares e indexados. O fallback HTML é menos determinante que em 2022, mas ainda resolve 4 casos (0,7%) de metadados PT incompletos na API.

---

## 5. Desempenho temporal

| Modo | Tempo total | Média/artigo |
|---|---|---|
| Padrão | 27m 10s | 2,71 s |
| --only-api | 27m 28s | 2,74 s |
| --only-html | **33m 22s** | **3,33 s** |

O modo padrão é **praticamente tão rápido quanto o --only-api** (18 segundos de diferença para 602 artigos) porque apenas 4 artigos ativaram o fallback HTML. O --only-html é ~23% mais lento porque tenta sempre o HTML (incluindo seguir redirects e parsear a página) em vez de fazer uma chamada JSON à API.

---

## 6. Conclusão

A estratégia padrão **api+html continua a ser o equilíbrio óptimo** mesmo para corpus sem AoPs. Neste corpus de 2025:

- A API resolveu **99,8% dos artigos** de forma limpa e rápida.
- O fallback HTML resolveu **4 casos** de metadados incompletos na API sem custo temporal relevante.
- O HTML-only **falhou em 3 artigos** que a API recuperou normalmente (404 na URL legacy).
- O único `ok_parcial` persistente (editorial sem resumo) é uma **limitação da fonte**, não do scraper.

| Estratégia | Cobre metadados incompletos? | Cobre AoPs? | Tempo | Recomendado quando |
|---|---|---|---|---|
| `--only-api` | Não | Não | ~27 min | Teste rápido; aceitável para corpus sem AoPs |
| `--only-html` | Parcialmente | Sim | ~33 min | API indisponível (cuidado com 404s legacy) |
| **Padrão (api+html)** | **Sim** | **Sim** | **~27 min** | **Sempre — melhor custo-benefício** |
