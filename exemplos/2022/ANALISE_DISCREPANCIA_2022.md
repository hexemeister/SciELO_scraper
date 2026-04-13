# Análise de Discrepância — API vs Web Scraping

**Corpus:** 564 artigos SciELO Brasil (2022), coleção `avalia_educa_2022.csv`  
**Referência:** execuções comparativas de 2026-04-09/10 (padrão, --only-api, --only-html)

---

## Resumo executivo

A diferença de cobertura entre a estratégia só-API (93,8%) e a estratégia padrão API+HTML (99,6%) explica-se quase inteiramente por **um único fenómeno estrutural**: artigos *Ahead of Print* (AoP) não estão indexados na ArticleMeta API no momento da publicação, mas já estão acessíveis via HTML.

Das 29 falhas no modo `--only-api`, **28 são artigos AoP** (PID com `005` nas posições 14–16). O HTML recuperou 27 deles; o 28.º (`S1519-69842022000100303`) é um 404 legítimo em todas as fontes.

---

## 1. O que é um artigo Ahead of Print?

Um AoP é publicado online antes de ser atribuído a um número/volume de revista. O PID reflecte esse estado:

```
S1414-462X  2022  005  024201
└── ISSN ┘  └ano┘ └┘  └seq┘
                  005 = fascículo "especial" AoP
```

O fluxo de indexação na SciELO tem dois momentos distintos:

| Momento                         | Disponível em HTML?       | Disponível na API? |
| ------------------------------- | ------------------------- | ------------------ |
| Publicação AoP                  | Sim (URL canónica activa) | **Não**            |
| Atribuição ao fascículo regular | Sim                       | Sim                |

Quando o script foi executado, os 28 artigos AoP já tinham URL canónica funcional em `scielo.br` mas ainda não tinham sido processados pelo pipeline ISIS/ArticleMeta. Por isso a API devolvia `null` para todos os campos PT.

---

## 2. O que o HTML tinha que a API não tinha

### 2.1 Artigos AoP — campos completamente ausentes na API

Para os 28 AoPs, a API devolvia uma resposta válida (HTTP 200, JSON com chave `"article"`) mas com todos os campos PT a `None`. O HTML da página tinha os três campos:

| Campo          | Fonte HTML usada                                                     |
| -------------- | -------------------------------------------------------------------- |
| Título         | `<meta name="citation_title">`                                       |
| Resumo         | `<meta name="citation_abstract">` ou `<div data-anchor="Resumo"><p>` |
| Palavras-chave | `<meta name="citation_keywords">` ou `.keywords span`                |

Exemplo concreto — `S1414-462X2022005024201` (AoP confirmado):

- **API:** sem dados PT (retorna `None` para titulo/resumo/palavras_chave)
- **HTML legacy** (`?script=sci_arttext&pid=...&lang=pt`): redireccionou para URL canónica; `is_article_page()` = True; todos os três campos extraídos via meta tags

### 2.2 Artigos em língua estrangeira — resumo PT ausente na API, presente no HTML

Alguns artigos têm o corpo em inglês ou espanhol mas incluem resumo em português como tradução obrigatória. A API ISIS retorna apenas o idioma principal. O HTML da versão PT (seguida via link "Texto (Português)") contém o resumo traduzido nas meta tags `citation_abstract`.

Este caso corresponde aos 6 artigos classificados `ok_parcial` no modo `--only-api` (que passaram a `ok_completo` no modo padrão).

### 2.3 Palavras-chave — normalização diferente

A API retorna keywords como lista separada por `|`, extraída do XML ISIS. O HTML serve-as em `<meta name="citation_keywords">` separadas por `,`. Em nenhum dos casos do corpus foi detectada discrepância de conteúdo, apenas de formatação — o script normaliza para `;` em ambos os casos.

---

## 3. O que a API tinha que o HTML não tinha

A API revelou-se **mais fiável em conteúdo textual** para artigos já indexados:

- **Sem truncagem:** a API devolve o resumo completo em texto plano, sem risco de HTML incompleto por truncagem de resposta.
- **Sem ambiguidade de idioma:** o campo `lang` no XML ISIS é explícito; o HTML por vezes tem `dc.language` em conflito com `citation_language`.
- **Sem ruído de marcação:** a API entrega texto limpo; o HTML pode incluir referências de rodapé, números de secção ou artefactos de formatação dentro dos parágrafos de resumo.

---

## 4. Casos residuais — o que ficou por resolver

### 4.1 `ok_parcial` que persiste no modo padrão (1 artigo)

Um artigo permanece `ok_parcial` mesmo no modo API+HTML. Após verificação manual, o artigo não tem resumo em português em **nenhuma fonte** — a publicação original é em inglês sem tradução de resumo exigida (artigo de carta/nota editorial curta).

### 4.2 Falha total — `S1519-69842022000100303`

Retorna 404 em todas as URLs tentadas (legacy, og:url) e não está indexado na API. É provável que o PID exista no CSV de entrada mas o artigo tenha sido retirado ou movido sem redirect.

---

## 5. Conclusão — quando usar cada estratégia

| Estratégia        | Cobre AoPs? | Tempo   | Recomendado quando              |
| ----------------- | ----------- | ------- | ------------------------------- |
| `--only-api`      | Não         | ~26 min | Teste rápido; corpus sem AoPs   |
| `--only-html`     | Sim         | ~36 min | API fora do ar                  |
| Padrão (api+html) | Sim         | ~26 min | Sempre — melhor custo-benefício |

A estratégia padrão é o equilíbrio óptimo: usa a API para ~94% dos artigos (mais rápida e mais limpa) e activa o HTML apenas para os ~6% em que a API falha ou retorna dados incompletos. O HTML funciona como rede de segurança para a janela temporal entre a publicação AoP e a indexação completa no pipeline ISIS.
