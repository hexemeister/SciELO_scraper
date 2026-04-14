# Análise de Discrepância — 2025

**Corpus:** 603 artigos SciELO Brasil (2025), termos: avalia$, educa$
**Gerado em:** 2026-04-13 23:29:55

---

## 1. Resumo executivo

| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |
|---|---|---|---|---|---|
| **padrão** | 602 (99.8%) | 1 (0.2%) | 0 (0.0%) | 603 (100.0%) | 27m 50s |
| **apenas-api** | 598 (99.2%) | 5 (0.8%) | 0 (0.0%) | 603 (100.0%) | 27m 52s |
| **apenas-html** | 597 (99.0%) | 3 (0.5%) | 3 (0.5%) | 600 (99.5%) | 42m 43s |

---

## 2. Artigos corrigidos pelo fallback HTML (4)

| PID | Status (api) | Status (padrao) | Fonte no padrao |
|---|---|---|---|
| `S1518-29242025000100302` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S1678-69712025000500601` | ok_parcial | ok_completo | articlemeta_isis[T] | articlemeta_isis[R] | Palavras_Chave_PT←pag1_meta_tags |
| `S2176-94512025000500307` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S2317-16342025000101005` | ok_parcial | ok_completo | articlemeta_isis[T] | articlemeta_isis[R] | Palavras_Chave_PT←pag1_meta_tags |

---

## 3. Artigos que o HTML-only falhou mas a API recuperou (4)

| PID | Status (api) | Status (html) | Fonte HTML |
|---|---|---|
| `S0034-71672025000300158` | ok_completo | erro_extracao | nan |
| `S0103-636X2025000100518` | ok_completo | ok_parcial | Titulo_PT←pag1_meta_tags | Resumo_PT←pag1_meta_tags |
| `S2237-96222025000100272` | ok_completo | erro_extracao | nan |
| `S2317-16342025000101035` | ok_completo | erro_extracao | nan |

---

## 4. Artigos persistentemente incompletos (1)

Estes artigos não atingiram `ok_completo` em nenhuma estratégia — a limitação é da fonte, não do scraper.

| PID | Título (PT) |
|---|---|
| `S0104-40362025000300100` | Educação, política e transformação: avaliação, inclusão e in |

---

## 5. Desempenho temporal

| Modo | Tempo total | Média/artigo |
|---|---|---|
| padrão | 27m 50s | 2.77 s |
| apenas-api | 27m 52s | 2.77 s |
| apenas-html | 42m 43s | 4.25 s |
