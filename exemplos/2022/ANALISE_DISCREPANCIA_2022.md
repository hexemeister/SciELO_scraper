# Análise de Discrepância — 2022

**Corpus:** 564 artigos SciELO Brasil (2022), termos: avalia$, educa$
**Gerado em:** 2026-04-13 19:00:37

---

## 1. Resumo executivo

| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |
|---|---|---|---|---|---|
| **padrão** | 563 (99.8%) | 1 (0.2%) | 0 (0.0%) | 564 (100.0%) | 26m 52s |
| **apenas-api** | 556 (98.6%) | 6 (1.1%) | 2 (0.4%) | 562 (99.6%) | 25m 59s |
| **apenas-html** | 561 (99.5%) | 1 (0.2%) | 2 (0.4%) | 562 (99.6%) | 36m 35s |

---

## 2. Artigos corrigidos pelo fallback HTML (7)

| PID | Status (api) | Status (padrao) | Fonte no padrao |
|---|---|---|---|
| `S0004-27492022005007211`  (AoP) | erro_extracao | ok_completo | Titulo_PT←pag1_meta_tags | Resumo_PT←pag1_meta_tags | Palavras_Chave_PT←pag1_meta_tags |
| `S0004-27492022005011211`  (AoP) | erro_extracao | ok_completo | Titulo_PT←pag1_meta_tags | Resumo_PT←pag1_meta_tags | Palavras_Chave_PT←pag1_meta_tags |
| `S0101-41612022000400809` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S0103-64402022000600044` | ok_parcial | ok_completo | articlemeta_isis[R] | Titulo_PT←pag1_meta_tags | Palavras_Chave_PT←pag1_meta_tags |
| `S1413-65382022000100302` | ok_parcial | ok_completo | articlemeta_isis[T] | articlemeta_isis[R] | Palavras_Chave_PT←pag1_meta_tags |
| `S2176-94512022000100305` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S2176-94512022000300500` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |

---

## 3. Artigos que o HTML-only falhou mas a API recuperou (2)

| PID | Status (api) | Status (html) | Fonte HTML |
|---|---|---|
| `S0034-71672022000700180` | ok_completo | erro_extracao | nan |
| `S1676-06032022000500603` | ok_completo | erro_extracao | nan |

---

## 4. Artigos persistentemente incompletos (1)

Estes artigos não atingiram `ok_completo` em nenhuma estratégia — a limitação é da fonte, não do scraper.

| PID | Título (PT) |
|---|---|
| `S0100-55022022000100101` | Teste de Progresso da Abem: consolidando uma estratégia de a |

---

## 5. Desempenho temporal

| Modo | Tempo total | Média/artigo |
|---|---|---|
| padrão | 26m 52s | 2.86 s |
| apenas-api | 25m 59s | 2.77 s |
| apenas-html | 36m 35s | 3.89 s |
