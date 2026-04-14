# Análise de Discrepância — 2023

**Corpus:** 468 artigos SciELO Brasil (2023), termos: avalia$, educa$
**Gerado em:** 2026-04-13 20:24:51

---

## 1. Resumo executivo

| Modo | `ok_completo` | `ok_parcial` | `erro_extracao` | Sucesso total | Tempo |
|---|---|---|---|---|---|
| **padrão** | 465 (99.4%) | 3 (0.6%) | 0 (0.0%) | 468 (100.0%) | 22m 24s |
| **apenas-api** | 463 (98.9%) | 5 (1.1%) | 0 (0.0%) | 468 (100.0%) | 21m 21s |
| **apenas-html** | 464 (99.1%) | 3 (0.6%) | 1 (0.2%) | 467 (99.8%) | 39m 10s |

---

## 2. Artigos corrigidos pelo fallback HTML (2)

| PID | Status (api) | Status (padrao) | Fonte no padrao |
|---|---|---|---|
| `S1517-86922023000100394` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |
| `S2176-94512023000300302` | ok_parcial | ok_completo | articlemeta_isis[R] | articlemeta_isis[K] | Titulo_PT←pag1_meta_tags |

---

## 3. Artigos que o HTML-only falhou mas a API recuperou (1)

| PID | Status (api) | Status (html) | Fonte HTML |
|---|---|---|
| `S2176-66812023000100202` | ok_completo | erro_extracao | nan |

---

## 4. Artigos persistentemente incompletos (3)

Estes artigos não atingiram `ok_completo` em nenhuma estratégia — a limitação é da fonte, não do scraper.

| PID | Título (PT) |
|---|---|
| `S0101-32622023000300002` | QUALIDADE SOCIAL E AVALIAÇÃO EDUCACIONAL: PROCESSOS DE (DES) |
| `S0102-46982023000100701` | Apresentação: Sobre o debate acerca da qualidade e da avalia |
| `S1983-21172023000100101` | EXPERIÊNCIAS DA REVISTA ENSAIO PESQUISA EM EDUCAÇÃO EM CIÊNC |

---

## 5. Desempenho temporal

| Modo | Tempo total | Média/artigo |
|---|---|---|
| padrão | 22m 24s | 2.87 s |
| apenas-api | 21m 21s | 2.74 s |
| apenas-html | 39m 10s | 5.02 s |
