# Algoritmo de Extração — SciELO Scraper v2.5

## Fluxograma de Decisão

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         process_article(row)                                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     clean_pid(raw_id)    │  Normaliza PID: strip,
                    │                         │  remove sufixo -scl / -oai,
                    │  Regex: [A-Z]\d{4}-     │  valida padrão de 23 chars
                    │  \d{3}[\dA-Z]\d{13}     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      PID válido?         │
                    └──────┬──────────┬────────┘
                        Não │          │ Sim
                           ▼          │
               ┌──────────────────┐   │
               │ status =         │   │
               │"erro_pid_invalido│   │
               └──────────────────┘   │
                                      │
          ┌───────────────────────────▼──────────────────────────────────────┐
          │                  FASE 1 — ArticleMeta API                        │
          │                  (ignorada se --only-html)                       │
          │                                                                  │
          │  GET articlemeta.scielo.org/api/v1/article                       │
          │      ?code={pid}&collection={col}&format=json                    │
          └───────────────────────────┬──────────────────────────────────────┘
                                      │
              ┌───────────────────────▼──────────────────────┐
              │       Resposta contém dados em PT?            │
              │  (dict com chave "article" + ≥1 campo PT)    │
              └──────┬───────────────────────┬───────────────┘
                 Não │                       │ Sim
                     │          ┌────────────▼───────────────┐
                     │          │   extract_pt_from_isis()   │
                     │          │                            │
                     │          │  Percorre "titles",        │
                     │          │  "abstracts", "keywords"   │
                     │          │  → filtra lang == "pt"     │
                     │          └────────────┬───────────────┘
                     │                       │
                     │          ┌────────────▼───────────────┐
                     │          │  T / R / KW preenchidos?   │
                     │          └────┬──────────────┬─────────┘
                     │          Todos│           Parcial│
                     │              ▼              ▼     │
                     │       ┌───────────┐  ┌──────────┐│
                     │       │ ok via API│  │ Missing: ││
                     │       │           │  │ [T][R][K]││
                     │       └─────┬─────┘  └────┬─────┘│
                     │             │              │      │
                     └─────────────┼──────────────┘      │
                                   │                      │
          ┌────────────────────────▼─────────────────────▼────────────────────┐
          │               FASE 2 — Fallback HTML                              │
          │               (ignorada se --only-api                             │
          │                OU se todos os campos já preenchidos)              │
          │                                                                   │
          │   Campos necessários: need_t / need_r / need_k                    │
          └───────────────────────────┬───────────────────────────────────────┘
                                      │
          ┌───────────────────────────▼──────────────────────────────────────┐
          │  ETAPA 1 — URL Legacy                                            │
          │                                                                  │
          │  scielo.br?script=sci_arttext&pid={pid}&lang=pt                  │
          │  → requests segue redirect automático                            │
          │    (pode chegar à URL canônica /j/.../a/.../                    │
          └───────────────────────────┬──────────────────────────────────────┘
                                      │
                    ┌─────────────────▼──────────────────┐
                    │     Erro HTTP / ConnectionError?    │
                    └──────┬──────────────────┬───────────┘
                        Sim│                  │ Não
                           ▼                  │
               ┌──────────────────┐           │
               │ return None      │           │
               │ (erro_extracao)  │           │
               └──────────────────┘           │
                                              │
                    ┌─────────────────────────▼──────────────────────┐
                    │  ETAPA 2 — is_article_page(soup)?               │
                    │                                                 │
                    │  True se qualquer um dos seguintes existir:     │
                    │  • meta[name="citation_title"]                  │
                    │  • meta[og:title] + div[data-anchor=Resumo]    │
                    │  • article#articleText                          │
                    │  • div[data-anchor="Resumo"]                   │
                    └──────┬──────────────────────────┬──────────────┘
                        Não│                          │ Sim
                           │                          ▼
                           │            ┌─────────────────────────────┐
                           │            │   apply_missing(meta, body)  │
                           │            │                              │
                           │            │  Para cada campo necessário: │
                           │            │  1. meta.get(campo)          │
                           │            │  2. body.get(campo)          │
                           │            │  Loga fonte: meta_tags       │
                           │            │             ou html_body     │
                           │            └──────────────┬──────────────┘
                           │                           │
                    ┌──────▼──────────────┐            │
                    │  is_aop(pid)?        │            │
                    │  pos[14:17] == "005" │            │
                    └────┬────────────┬───┘            │
                      Não│            │ Sim             │
                         │            ▼                 │
                         │  ┌──────────────────────┐   │
                         │  │  ETAPA 4 — AoP       │   │
                         │  │  Tentar og:url        │   │
                         │  │  da página home       │   │
                         │  │                       │   │
                         │  │  Se og:url ≠ legacy:  │   │
                         │  │  force lang=pt,       │   │
                         │  │  GET og:url           │   │
                         │  │  is_article_page()?   │   │
                         │  │  Sim → apply_missing  │   │
                         │  └──────────┬────────────┘   │
                         │             │                 │
                         └─────────────┴─────────────────┘
                                       │
                    ┌──────────────────▼────────────────────────────────────┐
                    │  ETAPA 3 — Língua da página ≠ PT?                     │
                    │  (e ainda há campos ausentes)                         │
                    │                                                       │
                    │  lang_orig (meta dc.language / citation_language)    │
                    └──────┬───────────────────────────┬────────────────────┘
                        Não│                           │ Sim
                           │              ┌────────────▼─────────────────┐
                           │              │  _find_pt_link(soup, base)   │
                           │              │                              │
                           │              │  Procura href com ?lang=pt   │
                           │              │  ou /pt/ nos links da página │
                           │              └──────┬─────────────┬─────────┘
                           │                 Não │             │ Sim
                           │                     │             ▼
                           │                     │  ┌────────────────────┐
                           │                     │  │  GET link PT       │
                           │                     │  │  apply_missing()   │
                           │                     │  └────────┬───────────┘
                           │                     │           │
                           └─────────────────────┴───────────┘
                                                 │
                    ┌────────────────────────────▼──────────────────────────┐
                    │                  RESULTADO FINAL                       │
                    │                                                        │
                    │  has_t = bool(titulo_val)                              │
                    │  has_r = bool(resumo_val)                              │
                    │  has_k = bool(kws_val)                                 │
                    │                                                        │
                    │  T ∧ R ∧ K  → "ok_completo"                           │
                    │  T ∨ R ∨ K  → "ok_parcial"                            │
                    │  url_ac ≠ "" → "nada_encontrado"                      │
                    │  (else)      → "erro_extracao"                        │
                    └───────────────────────────────────────────────────────┘
```

---

## Tabela de Decisão: API vs HTML

| Condição | Ação |
|---|---|
| `--only-html` | Ignora a Fase 1 completamente |
| `--only-api` | Ignora a Fase 2 completamente |
| API retorna 0 campos PT | HTML fallback ativado para T+R+K |
| API retorna 1–2 campos PT | HTML fallback ativado apenas para os campos ausentes |
| API retorna T+R+K completos | HTML fallback não é ativado |
| Página HTML não é artigo (`is_article_page = False`) | Ignora a extração, vai para Etapa 4 (se AoP) |
| AoP + página home ≠ artigo | Tenta `og:url` da página home |
| Língua da página ≠ `pt` e há campos ausentes | Segue link "Texto (Português)" |

---

## Prioridade dentro do HTML (apply_missing)

Para cada campo ausente, tenta por esta ordem:

1. **Meta tags** (`meta[name="citation_title"]`, `meta[name="citation_abstract"]`, `meta[name="citation_keywords"]`)
2. **Corpo HTML** (`h1.article-title`, `div[data-anchor=Resumo] p`, `.keywords span`)

A primeira fonte que tiver valor prevalece — as demais não são tentadas para esse campo.

---

## Fontes registradas em `fonte_extracao`

| Valor | O que significa |
|---|---|
| `articlemeta_isis[T]` | Título extraído da API ArticleMeta |
| `articlemeta_isis[R]` | Resumo extraído da API ArticleMeta |
| `articlemeta_isis[K]` | Palavras-chave extraídas da API ArticleMeta |
| `Titulo_PT←pag1_meta_tags` | Título via meta tags da URL legacy |
| `Titulo_PT←pag1_html_body` | Título via corpo HTML da URL legacy |
| `Resumo_PT←pag_pt_meta_tags` | Resumo via meta tags da versão PT |
| `Palavras_Chave_PT←pag_aop_ogurl_meta_tags` | Keywords via og:url (AoP) |
