"""
scielo_wordcloud.py — Nuvem de palavras a partir de CSVs do SciELO Scraper.

Propósito: gerar wordclouds publication-ready a partir dos campos de texto
extraídos pelo scielo_scraper.py (ou do terms_*.csv produzido pelo
terms_matcher.py). Opera sobre Titulo_PT, Resumo_PT, Palavras_Chave_PT
(ou qualquer coluna arbitrária via --custom-field).

Uso:
    uv run python scielo_wordcloud.py resultado.csv
    uv run python scielo_wordcloud.py terms_*.csv --corpus all
    uv run python scielo_wordcloud.py resultado.csv --field keywords
    uv run python scielo_wordcloud.py resultado.csv --field all --lang en
    uv run python scielo_wordcloud.py resultado.csv --stopwords extras.txt
    uv run python scielo_wordcloud.py resultado.csv --mask cloud_shape.png
    uv run python scielo_wordcloud.py resultado.csv --width 1200 --colormap plasma
    uv run python scielo_wordcloud.py resultado.csv --custom-field Resumo_PT
    uv run python scielo_wordcloud.py resultado.csv --dry-run
    uv run python scielo_wordcloud.py --list-langs
    uv run python scielo_wordcloud.py --list-colormaps
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

__version__ = "1.0"

# ---------------------------------------------------------------------------
# Mapeamento de campos
# ---------------------------------------------------------------------------

# Nome do campo CLI → coluna no CSV
FIELD_MAP = {
    "title":    "Titulo_PT",
    "abstract": "Resumo_PT",
    "keywords": "Palavras_Chave_PT",
}

FIELD_LABELS = {
    "title":    {"pt": "Título",         "en": "Title"},
    "abstract": {"pt": "Resumo",         "en": "Abstract"},
    "keywords": {"pt": "Palavras-chave", "en": "Keywords"},
}

FIELDS_DEFAULT = ["title", "keywords"]
FIELDS_ALL     = ["title", "abstract", "keywords"]

# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

# Mapeamento idioma CLI → nome NLTK
_NLTK_LANG = {
    "pt":    "portuguese",
    "pt-br": "portuguese",
    "pt-pt": "portuguese",
    "en":    "english",
    "es":    "spanish",
}

# Stopwords de domínio embutidas (PT-BR acadêmico / SciELO)
_DOMAIN_STOPWORDS_PT = {
    "scielo", "doi", "artigo", "artigos", "estudo", "estudos",
    "resultado", "resultados", "objetivo", "objetivos", "método",
    "métodos", "metodologia", "conclusão", "conclusões", "introdução",
    "discussão", "análise", "brasil", "brasileira", "brasileiros",
    "pesquisa", "pesquisas", "dado", "dados", "uso", "área", "áreas",
    "tipo", "tipos", "forma", "formas", "parte", "partes", "caso",
    "casos", "vez", "vezes", "através", "entre", "sobre", "sendo",
    "podem", "deve", "podem", "pode", "foram", "seja", "sendo",
    "ainda", "também", "como", "mais", "bem", "duas", "dois",
    "grande", "maior", "menor", "anos", "ano", "número",
}

_DOMAIN_STOPWORDS_EN = {
    "study", "studies", "result", "results", "objective", "objectives",
    "method", "methods", "conclusion", "conclusions", "introduction",
    "discussion", "analysis", "brazil", "brazilian", "research",
    "data", "use", "area", "areas", "type", "types", "form", "forms",
    "part", "parts", "case", "cases", "two", "three", "large", "larger",
    "smaller", "year", "years", "number", "also", "however", "therefore",
    "doi", "scielo", "article", "articles",
}

_DOMAIN_STOPWORDS_ES = {
    "estudio", "estudios", "resultado", "resultados", "objetivo",
    "objetivos", "método", "métodos", "conclusión", "conclusiones",
    "introducción", "discusión", "análisis", "brasil", "brasileño",
    "investigación", "dato", "datos", "uso", "área", "áreas",
    "tipo", "tipos", "forma", "formas", "parte", "partes", "caso",
    "casos", "doi", "scielo", "artículo", "artículos",
}

_DOMAIN_BY_LANG = {
    "pt": _DOMAIN_STOPWORDS_PT,
    "pt-br": _DOMAIN_STOPWORDS_PT,
    "pt-pt": _DOMAIN_STOPWORDS_PT,
    "en": _DOMAIN_STOPWORDS_EN,
    "es": _DOMAIN_STOPWORDS_ES,
}


def _nltk_stopwords(lang: str) -> set[str]:
    """Carrega stopwords NLTK para o idioma dado. Baixa corpus se necessário."""
    nltk_lang = _NLTK_LANG.get(lang, "portuguese")
    try:
        import nltk
        try:
            from nltk.corpus import stopwords
            return set(stopwords.words(nltk_lang))
        except LookupError:
            print("  Baixando corpus de stopwords NLTK...")
            nltk.download("stopwords", quiet=True)
            from nltk.corpus import stopwords
            return set(stopwords.words(nltk_lang))
    except ImportError:
        print("  ⚠  nltk não instalado. Usando apenas stopwords embutidas.")
        print("     Para melhor cobertura: uv pip install nltk")
        return set()


def _carregar_stopwords_arquivo(path: Path) -> set[str]:
    """Lê arquivo de stopwords: uma por linha ou CSV de coluna única."""
    words: set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            # Detecta se é CSV (tem vírgula na primeira linha)
            primeiro = f.readline().strip()
            f.seek(0)
            if "," in primeiro:
                reader = csv.reader(f)
                for row in reader:
                    for w in row:
                        w = w.strip().lower()
                        if w:
                            words.add(w)
            else:
                for linha in f:
                    w = linha.strip().lower()
                    if w and not w.startswith("#"):
                        words.add(w)
    except FileNotFoundError:
        print(f"  ⚠  Arquivo de stopwords não encontrado: {path}", file=sys.stderr)
    return words


def _construir_stopwords(lang: str, stopwords_file: Path | None,
                          domain: bool) -> set[str]:
    """Monta conjunto final de stopwords."""
    stops = _nltk_stopwords(lang)
    if domain:
        stops |= _DOMAIN_BY_LANG.get(lang, _DOMAIN_STOPWORDS_PT)
    if stopwords_file:
        stops |= _carregar_stopwords_arquivo(stopwords_file)
    return stops

# ---------------------------------------------------------------------------
# Tokenização
# ---------------------------------------------------------------------------

def _tokenizar(texto: str) -> list[str]:
    """Tokeniza texto: minúsculas, remove pontuação, filtra tokens curtos."""
    import re
    tokens = re.findall(r"\b[a-záàâãäéèêëíìîïóòôõöúùûüçñ]{3,}\b",
                        texto.lower())
    return tokens


def _texto_para_frequencia(textos: list[str], stopwords: set[str]) -> dict[str, int]:
    """Conta frequência de tokens filtrados por stopwords."""
    freq: dict[str, int] = {}
    for txt in textos:
        for token in _tokenizar(txt):
            if token not in stopwords:
                freq[token] = freq.get(token, 0) + 1
    return freq

# ---------------------------------------------------------------------------
# Carregar CSV
# ---------------------------------------------------------------------------

def _bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "sim")


def carregar_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def filtrar_corpus(rows: list[dict], corpus: str) -> list[dict]:
    """Filtra rows por corpus: 'criterio_ok' ou 'all'."""
    if corpus == "all":
        return rows
    # criterio_ok: filtra pela coluna criterio_ok=True
    filtered = [r for r in rows if _bool(r.get("criterio_ok", "False"))]
    if not filtered:
        print("  ⚠  Nenhum artigo com criterio_ok=True. Usando corpus completo.")
        return rows
    return filtered

# ---------------------------------------------------------------------------
# Geração de wordcloud
# ---------------------------------------------------------------------------

_ASPECT_DEFAULT = 2.0   # largura / altura


def _resolver_dimensoes(width: int | None, height: int | None) -> tuple[int, int]:
    """Resolve dimensões mantendo proporção se só uma for fornecida."""
    if width and height:
        return width, height
    if width and not height:
        return width, max(1, round(width / _ASPECT_DEFAULT))
    if height and not width:
        return max(1, round(height * _ASPECT_DEFAULT)), height
    return 800, 400   # default


def _carregar_mascara(path: Path) -> "np.ndarray | None":
    """Carrega PNG como máscara numpy. Pixels brancos = área excluída."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        mask = np.array(img)
        # Converte para escala onde branco (255,255,255) = excluído
        # wordcloud espera: 255 = fundo (excluído), 0 = preenchível
        gray = np.mean(mask, axis=2).astype(np.uint8)
        return gray
    except ImportError:
        print("  ⚠  Pillow não instalado — máscara ignorada. "
              "Execute: uv pip install Pillow", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"  ⚠  Arquivo de máscara não encontrado: {path}", file=sys.stderr)
        return None


def gerar_wordcloud(
    freq: dict[str, int],
    width: int,
    height: int,
    colormap: str,
    mask: "np.ndarray | None",
    max_words: int,
    dest: Path,
    titulo: str,
) -> bool:
    """Gera e salva wordcloud como PNG. Retorna True se bem-sucedido."""
    if not freq:
        print(f"  ⚠  Nenhum token após filtragem — pulando {dest.name}.")
        return False

    try:
        from wordcloud import WordCloud
    except ImportError:
        print("  ✗  wordcloud não instalado. Execute: uv pip install wordcloud",
              file=sys.stderr)
        return False

    # Configura wordcloud
    wc_kwargs: dict = dict(
        width=width,
        height=height,
        background_color="white",
        colormap=colormap,
        max_words=max_words,
        prefer_horizontal=0.85,
        collocations=False,   # evita bigramas automáticos
    )
    if mask is not None:
        wc_kwargs["mask"] = mask
        wc_kwargs["contour_width"] = 1
        wc_kwargs["contour_color"] = "steelblue"

    wc = WordCloud(**wc_kwargs)
    wc.generate_from_frequencies(freq)

    # Salva via matplotlib (para adicionar título)
    dpi = 150
    fig_w = width  / dpi
    fig_h = height / dpi + 0.5   # espaço para título

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    fig.suptitle(titulo, fontsize=10, fontweight="bold", y=0.98)
    fig.tight_layout(pad=0.3)
    plt.savefig(dest, dpi=dpi, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {dest}  ({len(freq)} tokens únicos)")
    return True

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _list_langs():
    print("\nIdiomas disponíveis (--lang):\n")
    dados = [
        ("pt-br", "Português Brasil", "207 stopwords NLTK + lista domínio PT"),
        ("pt-pt", "Português Portugal", "207 stopwords NLTK + lista domínio PT (mesma base)"),
        ("pt",    "Português (alias)",  "Mesmo que pt-br"),
        ("en",    "English",            "198 stopwords NLTK + lista domínio EN"),
        ("es",    "Español",            "313 stopwords NLTK + lista domínio ES"),
    ]
    for code, name, note in dados:
        print(f"  {code:<8}  {name:<25}  {note}")
    print()
    print("Nota: distinção pt-br / pt-pt usa a mesma base NLTK 'portuguese'.")
    print("      Use --stopwords para adicionar stopwords regionais extras.\n")
    sys.exit(0)


def _list_colormaps():
    print("\nColormaps disponíveis (--colormap):\n")
    grupos = {
        "Sequenciais (recomendados)": [
            "viridis", "plasma", "inferno", "magma", "cividis",
            "Blues", "Greens", "Oranges", "Reds", "Purples",
            "YlOrRd", "YlGnBu", "RdPu",
        ],
        "Divergentes": ["RdYlGn", "RdBu", "PiYG", "coolwarm"],
        "Qualitativos (evitar para wordcloud)": ["tab10", "Set1", "Set2"],
    }
    for grupo, cmaps in grupos.items():
        print(f"  [{grupo}]")
        print("    " + "  ".join(cmaps))
        print()
    print("Qualquer colormap matplotlib é aceito: "
          "https://matplotlib.org/stable/gallery/color/colormap_reference.html\n")
    sys.exit(0)


def main():
    # Flags especiais antes do parser
    if "--list-langs" in sys.argv:
        _list_langs()
    if "--list-colormaps" in sys.argv:
        _list_colormaps()
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    parser = argparse.ArgumentParser(
        prog="scielo_wordcloud.py",
        description=(
            "Gera nuvens de palavras (wordclouds) a partir de CSVs do SciELO Scraper. "
            "Processa Titulo_PT, Resumo_PT, Palavras_Chave_PT ou qualquer coluna do CSV."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  uv run python scielo_wordcloud.py resultado.csv\n"
            "  uv run python scielo_wordcloud.py terms.csv --field all --lang en\n"
            "  uv run python scielo_wordcloud.py resultado.csv --corpus all\n"
            "  uv run python scielo_wordcloud.py resultado.csv --mask shape.png\n"
            "  uv run python scielo_wordcloud.py resultado.csv --width 1200\n"
            "  uv run python scielo_wordcloud.py --list-langs\n"
        ),
    )

    parser.add_argument("input", metavar="CSV",
                        help="CSV de entrada (resultado.csv ou terms_*.csv)")
    parser.add_argument(
        "--field", metavar="CAMPO", default=None,
        help=(
            "Campo(s) a processar: title | abstract | keywords | all | "
            "title+keywords (default). Separados por '+' para múltiplos."
        ),
    )
    parser.add_argument(
        "--custom-field", metavar="COLUNA", default=None,
        help="Coluna arbitrária do CSV (qualquer nome de coluna). "
             "Pode ser combinado com --field.",
    )
    parser.add_argument(
        "--lang", metavar="IDIOMA", default="pt-br",
        help="Idioma das stopwords: pt-br (default) | pt-pt | pt | en | es. "
             "Use --list-langs para ver todos.",
    )
    parser.add_argument(
        "--list-langs", action="store_true",
        help="Lista idiomas disponíveis e sai.",
    )
    parser.add_argument(
        "--stopwords", metavar="ARQUIVO", default=None,
        help="Arquivo com stopwords extras (uma por linha ou CSV de coluna única).",
    )
    parser.add_argument(
        "--no-domain-stopwords", action="store_true",
        help="Desativa a lista de stopwords de domínio embutida.",
    )
    parser.add_argument(
        "--corpus", choices=["criterio_ok", "all"], default="criterio_ok",
        help=(
            "Filtro de artigos. "
            "'criterio_ok' (default): apenas artigos que passaram no critério de matching. "
            "'all': todos os artigos extraídos, independente do critério."
        ),
    )
    parser.add_argument(
        "--mask", metavar="PNG", default=None,
        help="PNG com shape da nuvem. Pixels escuros = área preenchível; "
             "pixels brancos = área excluída.",
    )
    parser.add_argument(
        "--width", metavar="N", type=int, default=None,
        help="Largura em pixels (default: 800). Se só --width, "
             "height = width / 2.",
    )
    parser.add_argument(
        "--height", metavar="N", type=int, default=None,
        help="Altura em pixels (default: 400). Se só --height, "
             "width = height × 2.",
    )
    parser.add_argument(
        "--colormap", metavar="NOME", default="viridis",
        help="Colormap matplotlib (default: viridis). "
             "Use --list-colormaps para ver opções.",
    )
    parser.add_argument(
        "--list-colormaps", action="store_true",
        help="Lista colormaps recomendados e sai.",
    )
    parser.add_argument(
        "--max-words", metavar="N", type=int, default=200,
        help="Número máximo de palavras na nuvem (default: 200).",
    )
    parser.add_argument(
        "--output-dir", metavar="DIR", default=None,
        help="Pasta de saída (default: diretório atual).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra configuração e arquivos que seriam gerados, sem gravar.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"scielo_wordcloud.py v{__version__}",
    )

    args = parser.parse_args()

    # --- Resolver campos a processar ------------------------------------------
    campos_para_processar: list[tuple[str, str]] = []  # (field_key, col_name)

    raw_field = args.field or "title+keywords"

    if raw_field == "all":
        for key in FIELDS_ALL:
            campos_para_processar.append((key, FIELD_MAP[key]))
    else:
        for part in raw_field.split("+"):
            part = part.strip()
            if part in FIELD_MAP:
                campos_para_processar.append((part, FIELD_MAP[part]))
            else:
                print(f"❌  Campo desconhecido: '{part}'. "
                      f"Opções: {' | '.join(FIELD_MAP)} | all", file=sys.stderr)
                sys.exit(1)

    if args.custom_field:
        campos_para_processar.append((args.custom_field, args.custom_field))

    if not campos_para_processar:
        print("❌  Nenhum campo selecionado.", file=sys.stderr)
        sys.exit(1)

    # --- Validar input --------------------------------------------------------
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌  Arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    # --- Carregar dados -------------------------------------------------------
    rows = carregar_csv(input_path)
    if not rows:
        print(f"❌  CSV vazio: {input_path}", file=sys.stderr)
        sys.exit(1)

    rows_filtradas = filtrar_corpus(rows, args.corpus)
    n_total  = len(rows)
    n_corpus = len(rows_filtradas)

    # Verificar colunas disponíveis
    colunas_csv = set(rows[0].keys())
    for field_key, col_name in campos_para_processar:
        if col_name not in colunas_csv:
            print(f"❌  Coluna '{col_name}' não encontrada no CSV.", file=sys.stderr)
            print(f"    Colunas disponíveis: {', '.join(sorted(colunas_csv))}", file=sys.stderr)
            sys.exit(1)

    # --- Stopwords ------------------------------------------------------------
    stopwords_file = Path(args.stopwords) if args.stopwords else None
    domain_ativo   = not args.no_domain_stopwords
    stopwords      = _construir_stopwords(args.lang, stopwords_file, domain_ativo)

    # --- Dimensões ------------------------------------------------------------
    width, height = _resolver_dimensoes(args.width, args.height)

    # --- Máscara --------------------------------------------------------------
    mask = None
    if args.mask:
        mask = _carregar_mascara(Path(args.mask))

    # --- Pasta de saída -------------------------------------------------------
    output = Path(args.output_dir) if args.output_dir else Path.cwd()

    # --- Timestamp ------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- Resumo ---------------------------------------------------------------
    print(f"\nscielo_wordcloud.py v{__version__}")
    print(f"Input            : {input_path} ({n_total} artigos)")
    print(f"Corpus           : {args.corpus} ({n_corpus} artigos)")
    print(f"Campo(s)         : {[f for f, _ in campos_para_processar]}")
    print(f"Idioma           : {args.lang}")
    print(f"Stopwords        : {len(stopwords)} palavras"
          f"{' + arquivo' if stopwords_file else ''}"
          f"{' + domínio' if domain_ativo else ''}")
    print(f"Dimensões        : {width}×{height}px")
    print(f"Colormap         : {args.colormap}")
    print(f"Max words        : {args.max_words}")
    print(f"Máscara          : {args.mask or 'nenhuma (retangular)'}")
    print(f"Pasta de saída   : {output.resolve()}")

    # Arquivos que seriam gerados
    lang_suf = args.lang.replace("-", "")  # pt-br → ptbr
    arquivos_previstos = []
    for field_key, col_name in campos_para_processar:
        nome_campo = field_key.replace("_", "").replace("-", "")
        nome = f"wordcloud_{nome_campo}_{lang_suf}_{ts}.png"
        arquivos_previstos.append((field_key, col_name, output / nome))

    if args.dry_run:
        print("\n[dry-run] Arquivos que seriam gerados:")
        for _, _, dest in arquivos_previstos:
            print(f"  {dest}")
        print()
        return

    # --- Geração --------------------------------------------------------------
    output.mkdir(parents=True, exist_ok=True)
    print()

    arquivos_gerados = []
    stats_campos = {}

    for field_key, col_name, dest in arquivos_previstos:
        # Label legível para o título do gráfico
        if field_key in FIELD_LABELS:
            label = FIELD_LABELS[field_key].get(
                "pt" if args.lang.startswith("pt") else "en",
                field_key
            )
        else:
            label = col_name  # custom field: usa o nome da coluna

        corpus_label = (
            f"criterio_ok (n={n_corpus})"
            if args.corpus == "criterio_ok"
            else f"corpus completo (n={n_corpus})"
        )
        titulo = f"{label} — {corpus_label}"

        # Extrai textos do campo
        textos = [
            r.get(col_name, "").strip()
            for r in rows_filtradas
            if r.get(col_name, "").strip()
        ]

        if not textos:
            print(f"  ⚠  Campo '{col_name}' vazio para todos os artigos — pulando.")
            continue

        freq = _texto_para_frequencia(textos, stopwords)

        ok = gerar_wordcloud(
            freq=freq,
            width=width,
            height=height,
            colormap=args.colormap,
            mask=mask,
            max_words=args.max_words,
            dest=dest,
            titulo=titulo,
        )
        if ok:
            arquivos_gerados.append(str(dest))
            stats_campos[field_key] = {
                "coluna":          col_name,
                "n_artigos":       len(textos),
                "n_tokens_unicos": len(freq),
                "top10":           sorted(freq, key=freq.get, reverse=True)[:10],
            }

    # --- stats JSON -----------------------------------------------------------
    stats_path = output / f"wordcloud_stats_{ts}.json"
    stats_data = {
        "versao_script":    __version__,
        "gerado_em":        datetime.now().isoformat(),
        "input":            str(input_path.resolve()),
        "corpus":           args.corpus,
        "n_total":          n_total,
        "n_corpus":         n_corpus,
        "lang":             args.lang,
        "n_stopwords":      len(stopwords),
        "colormap":         args.colormap,
        "width":            width,
        "height":           height,
        "max_words":        args.max_words,
        "mascara":          str(args.mask) if args.mask else None,
        "campos":           stats_campos,
        "arquivos_gerados": arquivos_gerados,
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {stats_path}")

    print(f"\nPronto. {len(arquivos_gerados)} wordcloud(s) em: {output.resolve()}")


if __name__ == "__main__":
    main()
