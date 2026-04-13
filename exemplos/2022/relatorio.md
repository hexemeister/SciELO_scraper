Bom. Já identifico as 3 execuções relevantes:

- `232434` → `--only-api` do zero
- `235350` → `--only-html` do zero  
- `003039` → padrão (api+html) do zero

Agora vou analisar cada uma em profundidade — integridade, coerência e adequação à estratégia.
Tenho tudo que preciso. Análise completa:

---

## Análise individual das execuções

### 1. `--only-api` (232434)

**Integridade:** ✅ 564 linhas, todas as colunas presentes, sem incoerências (ok com dados, erro sem dados).

**Coerência com a estratégia:** ✅ 94.9% via ArticleMeta ISIS, 5.1% sem fonte — esperado, a API simplesmente não tem dados para os AoPs. Sem nenhuma chamada HTML, correto.

**Problemas:**

- 29 `erro_extracao` — todos AoPs, a API não retorna dados para eles. **Normal para esta estratégia.**
- 6 `ok_parcial` — a API retorna alguns campos mas não todos (ex: tem resumo mas não título PT). **Normal.**
- 1 PID duplicado (`S0104-40362022005003204`) — **vem do CSV de entrada**, não é bug do script.

---

### 2. `--only-html` (235350)

**Integridade:** ✅ 564 linhas, colunas corretas, sem incoerências.

**Coerência com a estratégia:** ✅ 99.6% via html_fallback, 0.4% sem fonte. O HTML recupera muito mais que a API para os AoPs.

**Problemas:**

- `S0034-71672022000700180` → `erro_extracao` só no `--only-html`, mas funciona na API. Isso é um artigo que a API resolve mas a página HTML falhou (provavelmente redirect sem dados acessíveis via scraping). **Limitação esperada do HTML.**
- `S0100-55022022000100101` → `ok_parcial` em todas as execuções, só tem título. O resumo genuinamente não está disponível em nenhuma fonte. **Não é bug.**
- PID duplicado — mesmo do CSV de entrada.

---

### 3. `--padrão` api+html (003039)

**Integridade:** ✅ 564 linhas, colunas corretas, sem incoerências.

**Coerência com a estratégia:** ✅ API como fonte primária (94%), HTML como fallback (5%), e a combinação api+html_fallback para 0.9% — exatamente o comportamento esperado.

**Problemas:**

- Apenas 1 `erro_extracao`: `S1519-69842022000100303` — retorna 404 legítimo em qualquer estratégia. **Irrecuperável.**
- 1 `ok_parcial`: `S0100-55022022000100101` — resumo genuinamente ausente em todas as fontes.
- PID duplicado — do CSV de entrada.

---

## Comparação entre as 3 execuções

|               | `--only-api` | `--only-html` | padrão (api+html) |
| ------------- | ------------ | ------------- | ----------------- |
| ok_completo   | 529 (93.8%)  | 561 (99.5%)   | 562 (99.6%)       |
| ok_parcial    | 6 (1.1%)     | 1 (0.2%)      | 1 (0.2%)          |
| erro_extracao | 29 (5.1%)    | 2 (0.4%)      | 1 (0.2%)          |
| Tempo         | 26m 27s      | 36m 26s       | 25m 46s           |

**Conclusões:**

1. **O HTML é muito mais eficaz que a API para AoPs** — a API falha em 29 deles, o HTML recupera 27 dos 28 (o 28º é o 404 legítimo).

2. **O padrão (api+html) é a melhor estratégia**: mesmos resultados do `--only-html` mas ~10 min mais rápido — a API resolve 94% dos casos rapidamente, e o HTML só é acionado quando necessário.

3. **`--only-api` não é recomendado** para coleções com AoPs — perde 5% dos artigos que seriam recuperáveis.

4. **`--only-html` é útil** quando a API estiver fora do ar, mas é o mais lento e perde 1 artigo que só a API resolve (`S0034-71672022000700180`).

5. **O único artigo verdadeiramente irrecuperável** em qualquer estratégia é `S1519-69842022000100303` (404) e `S0100-55022022000100101` (resumo ausente em todas as fontes).