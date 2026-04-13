---
name: scielo-analysis
description: Analisa CSVs de resultado do SciELO Scraper — EDA, comparação de modos, visualizações de cobertura e performance
license: MIT
metadata:
    skill-author: hexemeister
---

# scielo-analysis

Skill para análise de dados gerados pelo SciELO Scraper v2.4. Conhece o formato exato dos arquivos e como interpretá-los.

## Quando usar

- Analisar `resultado.csv` de uma execução do scraper
- Comparar modos de extração (`api`, `html`, `api+html`)
- Gerar gráficos de cobertura, performance e fontes de extração
- Fazer EDA de metadados extraídos (títulos, resumos, palavras-chave)
- Ler e interpretar `stats.json`

## Estrutura dos arquivos

### CSV de entrada (`sc_<timestamp>.csv`)

Colunas obrigatórias:
- `ID` — PID SciELO (ex: `S1982-88372022000300013-scl`)

Colunas opcionais (vindas do searcher):
- `Title`, `Author(s)`, `Source`, `Journal`, `Language(s)`, `Publication year`, `Fulltext URL`

### CSV de resultado (`resultado.csv`)

Colunas adicionadas pelo scraper:
- `PID_limpo` — PID normalizado sem sufixo
- `URL_PT` — URL da versão PT
- `Titulo_PT` — Título em português
- `Resumo_PT` — Resumo em português
- `Palavras_Chave_PT` — Keywords separadas por `;`
- `status` — `ok_completo` | `ok_parcial` | `nada_encontrado` | `erro_extracao` | `erro_pid_invalido`
- `fonte_extracao` — fontes usadas (ex: `articlemeta_isis[T] | articlemeta_isis[R] | articlemeta_isis[K]`)
- `url_acedida` — URLs acessadas durante o scraping

### stats.json

```json
{
  "versao_script": "2.4",
  "modo": { "extracao": "api+html", "resume": "NEW", "workers": 1, "collection": "scl" },
  "total": 564,
  "ok_completo": 562, "ok_completo_pct": "99.6%",
  "ok_parcial": 1, "ok_parcial_pct": "0.2%",
  "sucesso_total": 563, "sucesso_total_pct": "99.8%",
  "erro_extracao": 1, "erro_extracao_pct": "0.2%",
  "elapsed_seconds": 1545.82,
  "elapsed_humanizado": "25m 45s",
  "avg_per_article_s": 2.74,
  "por_fonte_extracao": { "articlemeta_isis": {"n": 529, "pct": "93.8%"} }
}
```

## Padrões de análise

### Carregar resultado.csv

```python
import pandas as pd

df = pd.read_csv("resultado.csv")

# Distribuição de status
print(df["status"].value_counts(normalize=True).mul(100).round(1))

# Artigos com erro
erros = df[df["status"] == "erro_extracao"]

# Artigos AoP (posições 14-16 do PID == "005")
df["is_aop"] = df["PID_limpo"].str[14:17] == "005"
```

### Comparar modos de extração

```python
import json, glob

# Carregar todos os stats.json de uma pasta de ano
stats_files = glob.glob("exemplos/2024/*/stats.json")
dados = []
for f in stats_files:
    with open(f) as fh:
        s = json.load(fh)
    dados.append({
        "modo": s["modo"]["extracao"],
        "ok_completo_pct": float(s["ok_completo_pct"].strip("%")),
        "tempo_min": s["elapsed_seconds"] / 60,
        "total": s["total"]
    })
df_stats = pd.DataFrame(dados)
```

### Análise de fontes de extração

```python
# Expandir fonte_extracao (campo separado por pipe)
fontes = df["fonte_extracao"].str.split(" | ").explode()
print(fontes.value_counts())

# Quantos vieram só da API vs. só do HTML vs. misto
df["via_api"] = df["fonte_extracao"].str.contains("articlemeta_isis")
df["via_html"] = df["fonte_extracao"].str.contains("pag|html|meta_tags")
```

### Visualizações típicas

```python
import matplotlib.pyplot as plt

# Gráfico de barras: status por modo
fig, ax = plt.subplots(figsize=(8, 5))
df_stats.plot(x="modo", y="ok_completo_pct", kind="bar", ax=ax)
ax.set_ylabel("ok_completo (%)")
ax.set_title("Cobertura por modo de extração")
ax.set_ylim(0, 100)
plt.tight_layout()
plt.savefig("cobertura_modos.png", dpi=150)
```

## Dependências

```bash
uv pip install pandas matplotlib seaborn
```

## Boas práticas

- Sempre verificar encoding: CSVs do scraper são UTF-8 com BOM (`encoding="utf-8-sig"`)
- Colunas com aspas extras (artefato do Windows CSV): usar `df.columns = df.columns.str.strip('"')`
- Para análise de palavras-chave: `df["Palavras_Chave_PT"].str.split(";").explode().str.strip()`
- Artigos AoP têm `005` nas posições 14-16 do PID — tratá-los separadamente, pois a API não os indexa
