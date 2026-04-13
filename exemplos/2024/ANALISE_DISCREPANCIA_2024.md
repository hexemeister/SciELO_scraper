# Analise de Discrepancia — 2024

**Corpus:** 553 artigos SciELO Brasil (2024), termos: avalia$, educa$
**Gerado em:** 2026-04-13 10:47:25

---

## 1. Resumo executivo

| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |
|---|---|---|---|---|---|
| **padrão** | 551 (99.6%) | 1 (0.2%) | 1 (0.2%) | 552 (99.8%) | 26m 41s |
| **apenas-api** | 547 (98.9%) | 5 (0.9%) | 1 (0.2%) | 552 (99.8%) | 26m 18s |
| **apenas-html** | 549 (99.3%) | 1 (0.2%) | 3 (0.5%) | 550 (99.5%) | 30m 5s |

---

## 2. Artigos corrigidos pelo fallback HTML (4)

| PID | Status (api) | Status (padrao) | Fonte no padrao |
|---|---|---|---|
| `S0103-64402024000100261` | ok_parcial | ok_completo | articlemeta_isis[R] | Titulo_PT←pag1_meta_tags | Palavras_Chave_PT←pag1_meta_tags |
| `S1678-69712024000400302` | ok_parcial | ok_completo | articlemeta_isis[T] | articlemeta_isis[R] | Palavras_Chave_PT←pag1_meta_tags |
| `S2176-94512024000500301` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S2176-94512024000600306` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |

---

## 3. Artigos que o HTML-only falhou mas a API recuperou (2)

| PID | Status (api) | Status (html) | Fonte HTML |
|---|---|---|
| `S1983-14472024000100463` | ok_completo | erro_extracao | nan |
| `S2448-24552024000102237` | ok_completo | erro_extracao | nan |

---

## 4. Artigos persistentemente nao-completos (2)

Estes artigos nao atingiram `ok_completo` em nenhuma estrategia — a limitacao e da fonte, nao do scraper.

| PID | Titulo (PT) |
|---|---|
| `S0066-782X2024001200310` | nan |
| `S0100-69912024000100912` | Comentários a “Reflexões acerca do contexto atual e da avali |

---

## 5. Desempenho temporal

| Modo | Tempo total | Media/artigo |
|---|---|---|
| padrão | 26m 41s | 2.9 s |
| apenas-api | 26m 18s | 2.85 s |
| apenas-html | 30m 5s | 3.26 s |
