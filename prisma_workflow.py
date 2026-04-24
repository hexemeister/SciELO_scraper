"""
prisma_workflow.py — Gera formulário PDF preenchível PRISMA 2020.

Propósito: criar um PDF A4 com o fluxograma PRISMA 2020 onde os dados
automáticos (fase de Identificação) já vêm pré-preenchidos a partir do
results_report.json, e os campos das fases humanas (Triagem e Inclusão)
são campos AcroForm editáveis no próprio PDF.

Referência: Page MJ et al. PRISMA 2020 Statement. BMJ 2021;372:n71.
            https://www.prisma-statement.org/prisma-2020-flow-diagram

Fases cobertas pelo pipeline SciELO Scraper:
  IDENTIFICATION (Identificação) — AUTOMÁTICO:
    • Records identified from databases   ← total_buscado
    • Duplicate records removed           ← 0 (SciELO não duplica — editável)
    • Records marked ineligible by automation tools ← nada_encontrado + ok_parcial sem campos mínimos
    • Records removed for other reasons   ← erro_extracao + erro_pid_invalido
    • Records screened                    ← calculado automaticamente

  SCREENING (Triagem) — HUMANO:
    • Records excluded (title/abstract screening)
    • Reports sought for retrieval
    • Reports not retrieved
    • Reports assessed for eligibility
    • Reports excluded + reasons

  INCLUDED (Inclusão) — HUMANO:
    • Studies included in review
    • Reports of included studies

Uso:
    uv run python prisma_workflow.py results_report.json
    uv run python prisma_workflow.py results_report.json --interactive
    uv run python prisma_workflow.py results_report.json --human-data humano.json
    uv run python prisma_workflow.py results_report.json --screened 96 --excluded-screening 83
    uv run python prisma_workflow.py results_report.json --included 13 --lang en
    uv run python prisma_workflow.py results_report.json --dry-run
    uv run python prisma_workflow.py -?
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Verificação de dependências (antes de qualquer import externo)
# ---------------------------------------------------------------------------

def _verificar_deps():
    ausentes = [pkg for mod, pkg in {"reportlab": "reportlab"}.items()
                if importlib.util.find_spec(mod) is None]
    if ausentes:
        print("❌  Dependências ausentes. Execute:")
        print(f"    uv pip install {' '.join(ausentes)}")
        sys.exit(1)

_verificar_deps()

__version__ = "1.1"

# ---------------------------------------------------------------------------
# Strings i18n
# ---------------------------------------------------------------------------

STRINGS = {
    # Fases
    "fase_identificacao":  {"pt": "IDENTIFICAÇÃO",  "en": "IDENTIFICATION"},
    "fase_triagem":        {"pt": "TRIAGEM",         "en": "SCREENING"},
    "fase_inclusao":       {"pt": "INCLUSÃO",        "en": "INCLUDED"},

    # Labels (sem número) — Identificação
    "id_databases_label":     {"pt": "Registros identificados nas bases de dados",
                               "en": "Records identified from databases"},
    "id_removed_label":       {"pt": "Registros removidos antes da triagem:",
                               "en": "Records removed before screening:"},
    "id_duplicates_label":    {"pt": "Registros duplicados removidos",
                               "en": "Duplicate records removed"},
    "id_automation_label":    {"pt": "Marcados inelegíveis por automação",
                               "en": "Marked ineligible by automation tools"},
    "id_other_label":         {"pt": "Removidos por outros motivos (erros, PID inválido)",
                               "en": "Removed for other reasons (errors, invalid PID)"},
    "id_screened_label":      {"pt": "Registros selecionados para triagem",
                               "en": "Records screened"},

    # Labels — Triagem
    "scr_excluded_label":     {"pt": "Registros excluídos na triagem (título/resumo)",
                               "en": "Records excluded (title/abstract screening)"},
    "scr_sought_label":       {"pt": "Relatórios buscados para recuperação",
                               "en": "Reports sought for retrieval"},
    "scr_not_retrieved_label":{"pt": "Relatórios não recuperados",
                               "en": "Reports not retrieved"},
    "scr_assessed_label":     {"pt": "Relatórios avaliados para elegibilidade",
                               "en": "Reports assessed for eligibility"},
    "scr_excl_reasons_label": {"pt": "Relatórios excluídos — razões:",
                               "en": "Reports excluded — reasons:"},

    # Labels — Inclusão
    "inc_studies_label":      {"pt": "Estudos incluídos na revisão",
                               "en": "Studies included in review"},
    "inc_reports_label":      {"pt": "Relatórios dos estudos incluídos",
                               "en": "Reports of included studies"},

    # Rótulos de campos editáveis
    "campo_editavel":      {"pt": "Campo a preencher após curadoria humana",
                            "en": "Field to fill after human curation"},
    "nota_automatico":     {"pt": "Preenchido automaticamente pelo SciELO Scraper",
                            "en": "Automatically filled by SciELO Scraper"},
    "nota_humanizado":     {"pt": "A preencher — curadoria humana necessária",
                            "en": "To fill — human curation required"},
    "nota_prisma":         {
        "pt": (
            "Gerado por prisma_workflow.py v{ver} em {data}. "
            "Referência: Page MJ et al. PRISMA 2020. BMJ 2021;372:n71. "
            "O pipeline SciELO Scraper automatiza apenas a fase de Identificação. "
            "As fases de Triagem e Inclusão requerem curadoria humana."
        ),
        "en": (
            "Generated by prisma_workflow.py v{ver} on {data}. "
            "Reference: Page MJ et al. PRISMA 2020. BMJ 2021;372:n71. "
            "The SciELO Scraper pipeline automates only the Identification phase. "
            "The Screening and Included phases require human curation."
        ),
    },
    "titulo_doc":          {"pt": "Diagrama de Fluxo PRISMA 2020",
                            "en": "PRISMA 2020 Flow Diagram"},
    "aviso_parcial":       {
        "pt": (
            "⚠  DIAGRAMA PARCIAL: os campos das fases de Triagem e Inclusão "
            "estão em branco e devem ser preenchidos após a curadoria humana."
        ),
        "en": (
            "⚠  PARTIAL DIAGRAM: fields for the Screening and Included phases "
            "are blank and must be filled after human curation."
        ),
    },
}


def s(chave: str, lang: str, **kwargs) -> str:
    texto = STRINGS[chave].get(lang, STRINGS[chave]["pt"])
    if kwargs:
        try:
            texto = texto.format(**kwargs)
        except KeyError:
            pass
    return texto


# ---------------------------------------------------------------------------
# Extração de dados do results_report.json
# ---------------------------------------------------------------------------

def carregar_dados_automaticos(json_path: Path) -> dict:
    """
    Lê results_report.json e extrai os dados automáticos para o PRISMA.
    Agrega múltiplos anos em totais globais.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    por_ano = data.get("por_ano", {})
    totais  = data.get("totais", {})

    # Totais automáticos globais
    total_buscado   = totais.get("total_buscado", 0)
    total_scrapeado = totais.get("total_scrapeado", 0)

    # Erros de acesso (removidos por outros motivos)
    erros_outros = 0
    for v in por_ano.values():
        erros = v.get("erros_extracao", {})
        for k, n in erros.items():
            erros_outros += int(n) if str(n).isdigit() else 0

    # Artigos sem dados úteis (automation tools)
    # = total_scrapeado - ok_completo - ok_parcial (sem erros)
    ok_completo_total = sum(v.get("ok_completo", 0) for v in por_ano.values())
    ok_parcial_total  = sum(v.get("ok_parcial", 0)  for v in por_ano.values())
    criterio_ok_total = totais.get("criterio_ok", 0)

    # automation = artigos onde não foi possível extrair dados
    automation_removed = total_scrapeado - ok_completo_total - ok_parcial_total - erros_outros
    automation_removed = max(0, automation_removed)

    # Records screened = total_buscado - duplicados - automation - outros
    # (duplicados = 0 por default no SciELO)
    duplicates = 0
    screened   = total_buscado - duplicates - automation_removed - erros_outros
    screened   = max(0, screened)

    # Metadata
    anos       = data.get("anos", [])
    termos     = data.get("termos", [])
    data_busca = ""
    colecao    = ""
    versao_scraper  = ""
    versao_searcher = ""
    for v in por_ano.values():
        if v.get("data_busca"):
            data_busca = v["data_busca"][:10]
        if v.get("colecao"):
            colecao = v["colecao"]
        if v.get("versao_scraper"):
            versao_scraper = v["versao_scraper"]
        if v.get("versao_searcher"):
            versao_searcher = v["versao_searcher"]

    return {
        # Campos automáticos
        "total_buscado":       total_buscado,
        "duplicates":          duplicates,         # 0 por padrão — editável no PDF
        "automation_removed":  automation_removed,
        "erros_outros":        erros_outros,
        "screened":            screened,
        "criterio_ok":         criterio_ok_total,
        # Metadata
        "anos":                anos,
        "termos":              termos,
        "colecao":             colecao,
        "data_busca":          data_busca,
        "versao_scraper":      versao_scraper,
        "versao_searcher":     versao_searcher,
        "json_path":           str(json_path.resolve()),
    }


# ---------------------------------------------------------------------------
# Merge de dados humanos (arquivo + CLI)
# ---------------------------------------------------------------------------

_CAMPOS_HUMANOS = [
    "duplicates",          # editável (default 0, mas pode haver)
    "excluded_screening",
    "sought",
    "not_retrieved",
    "assessed",
    "excluded_eligibility",
    "excluded_reasons",    # lista de "Razão: n"
    "included_studies",
    "included_reports",
]


def carregar_human_data(path: Path) -> dict:
    """Lê arquivo JSON/CSV com dados humanos."""
    if not path.exists():
        print(f"  ⚠  Arquivo --human-data não encontrado: {path}", file=sys.stderr)
        return {}
    try:
        if path.suffix.lower() == ".json":
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        else:
            # CSV: key,value
            import csv
            result = {}
            with open(path, encoding="utf-8") as f:
                for row in csv.reader(f):
                    if len(row) >= 2:
                        result[row[0].strip()] = row[1].strip()
            return result
    except Exception as e:
        print(f"  ⚠  Erro ao ler --human-data: {e}", file=sys.stderr)
        return {}


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def merge_human(auto: dict, human_file: dict, args) -> dict:
    """
    Mescla dados humanos. Prioridade: CLI > arquivo > None (campo em branco).
    """
    merged = dict(auto)

    # Campos que podem vir do arquivo
    file_map = {
        "duplicates":          human_file.get("duplicates"),
        "excluded_screening":  human_file.get("excluded_screening"),
        "sought":              human_file.get("sought"),
        "not_retrieved":       human_file.get("not_retrieved"),
        "assessed":            human_file.get("assessed"),
        "excluded_eligibility":human_file.get("excluded_eligibility"),
        "excluded_reasons":    human_file.get("excluded_reasons", []),
        "included_studies":    human_file.get("included_studies"),
        "included_reports":    human_file.get("included_reports"),
    }

    # CLI sobrepõe arquivo
    cli_map = {
        "duplicates":          getattr(args, "duplicates", None),
        "excluded_screening":  getattr(args, "excluded_screening", None),
        "sought":              getattr(args, "sought", None),
        "not_retrieved":       getattr(args, "not_retrieved", None),
        "assessed":            getattr(args, "assessed", None),
        "excluded_eligibility":getattr(args, "excluded_eligibility", None),
        "included_studies":    getattr(args, "included", None),
        "included_reports":    getattr(args, "included_reports", None),
    }

    for campo in _CAMPOS_HUMANOS:
        if campo == "excluded_reasons":
            # Razões: vêm só do arquivo (muito complexo via CLI)
            merged[campo] = file_map.get("excluded_reasons", [])
            continue
        cli_val  = _int_or_none(cli_map.get(campo))
        file_val = _int_or_none(file_map.get(campo))
        merged[campo] = cli_val if cli_val is not None else file_val

    # Recalcular duplicates no auto se sobrescrito
    if merged.get("duplicates") is not None:
        d = merged["duplicates"]
        merged["screened"] = max(0,
            merged["total_buscado"] - d
            - merged["automation_removed"]
            - merged["erros_outros"]
        )

    return merged


# ---------------------------------------------------------------------------
# Modo interativo
# ---------------------------------------------------------------------------

def _input_int(prompt: str, default=None) -> int | None:
    """Lê inteiro do terminal com valor padrão."""
    if default is not None:
        prompt_full = f"  {prompt} [default: {default}]: "
    else:
        prompt_full = f"  {prompt} [deixe vazio para preencher depois]: "

    val = input(prompt_full).strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        print("    ⚠  Valor inválido — ignorado.")
        return default


def modo_interativo(merged: dict, lang: str) -> dict:
    """Pergunta campo a campo os dados humanos ausentes."""
    print("\n" + "=" * 60)
    print("  MODO INTERATIVO — Dados das fases humanas (PRISMA 2020)")
    print("  Pressione Enter para deixar o campo em branco no PDF.")
    print("=" * 60 + "\n")

    print("  [Dados automáticos já preenchidos]")
    print(f"    Registros identificados : {merged['total_buscado']}")
    print(f"    Duplicatas removidas    : {merged['duplicates'] or 0}")
    print(f"    Removidos por automação : {merged['automation_removed']}")
    print(f"    Removidos por erros     : {merged['erros_outros']}")
    print(f"    Selecionados p/ triagem : {merged['screened']}")
    print()

    print("  [Fase de Triagem — preencha após curadoria humana]\n")

    if merged.get("excluded_screening") is None:
        merged["excluded_screening"] = _input_int(
            "Registros excluídos na triagem (título/resumo)")

    if merged.get("sought") is None:
        merged["sought"] = _input_int(
            "Relatórios buscados para recuperação")

    if merged.get("not_retrieved") is None:
        merged["not_retrieved"] = _input_int(
            "Relatórios não recuperados")

    if merged.get("assessed") is None:
        merged["assessed"] = _input_int(
            "Relatórios avaliados para elegibilidade")

    if merged.get("excluded_eligibility") is None:
        merged["excluded_eligibility"] = _input_int(
            "Relatórios excluídos por elegibilidade (total)")

    # Razões de exclusão
    if not merged.get("excluded_reasons"):
        print("\n  Razões de exclusão por elegibilidade:")
        print("  (Digite uma razão por linha. Pressione Enter em branco para terminar.)")
        reasons = []
        while True:
            razao = input("    Razão (texto: n): ").strip()
            if not razao:
                break
            reasons.append(razao)
        merged["excluded_reasons"] = reasons

    print("\n  [Fase de Inclusão — preencha após curadoria humana]\n")

    if merged.get("included_studies") is None:
        merged["included_studies"] = _input_int(
            "Estudos incluídos na revisão")

    if merged.get("included_reports") is None:
        merged["included_reports"] = _input_int(
            "Relatórios dos estudos incluídos")

    print()
    return merged


# ---------------------------------------------------------------------------
# Geração do PDF (reportlab)
# ---------------------------------------------------------------------------

# Cores do diagrama
_COR_AUTO    = (0.18, 0.49, 0.72)   # azul — campo automático
_COR_HUMANO  = (0.95, 0.95, 0.95)   # cinza claro — campo humano editável
_COR_FASE    = (0.13, 0.55, 0.13)   # verde escuro — cabeçalho de fase
_COR_BORDA   = (0.40, 0.40, 0.40)   # cinza médio — bordas
_COR_TEXTO_AUTO   = (1.0, 1.0, 1.0)  # branco — texto em caixa azul
_COR_TEXTO_HUMANO = (0.2, 0.2, 0.2)  # quase preto — texto em caixa cinza


def _rgb(t: tuple) -> tuple:
    """Converte tupla 0-1 para objeto Color do reportlab."""
    from reportlab.lib.colors import Color
    return Color(*t)


def _wrap_text(c, txt: str, x: float, y: float, max_w: float,
               font: str, size: float, color, line_h: float):
    """Desenha texto com quebra de linha simples em `c` (canvas reportlab)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    c.setFont(font, size)
    c.setFillColor(color)
    lines = txt.split("\n")
    for line in lines:
        # Quebra automática se a linha for longa
        words = line.split()
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if stringWidth(test, font, size) <= max_w:
                current = test
            else:
                if current:
                    c.drawCentredString(x, y, current)
                    y -= line_h
                current = word
        if current:
            c.drawCentredString(x, y, current)
            y -= line_h
    return y  # retorna y após a última linha


def gerar_pdf(dados: dict, output_path: Path, lang: str = "pt"):  # noqa: C901
    """
    Gera o PDF PRISMA 2020 A4.

    Design de campos:
      - Campos automáticos (auto=True): caixa azul sólida, texto branco no canvas, não editável.
      - Campos humanos (auto=False): caixa cinza com borda tracejada.
        O label (descrição) é desenhado no canvas (não editável).
        Um campo AcroForm pequeno é criado APENAS para o número (n = ?).
        O usuário vê o texto descritivo sempre e edita apenas o número.
    """
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
    except ImportError:
        print("❌  reportlab não instalado. Execute: uv pip install reportlab",
              file=sys.stderr)
        sys.exit(1)

    from datetime import datetime as DT
    from reportlab.pdfbase.pdfmetrics import stringWidth

    W, H = A4   # 595.28 × 841.89 pts

    # Layout constants — tudo proporcional ao A4
    MARGEM       = 32.0
    GAP          = 9.0      # espaço entre caixas
    GAP_FASE     = 6.0      # espaço após cabeçalho de fase
    PAD_V        = 7.0      # padding interno vertical caixa
    PAD_H        = 8.0      # padding interno horizontal caixa
    FONT_SIZE    = 7.0
    LINE_H       = 8.5
    FASE_H       = 16.0     # altura do cabeçalho de fase
    COL_GAP      = 14.0     # gap horizontal entre col_l e col_r

    AREA_W  = W - 2 * MARGEM
    COL_L_W = AREA_W * 0.52          # coluna esquerda (fluxo principal)
    COL_R_W = AREA_W - COL_L_W - COL_GAP  # coluna direita (exclusões)
    COL_L_X = MARGEM
    COL_R_X = MARGEM + COL_L_W + COL_GAP
    CX_L    = COL_L_X + COL_L_W / 2  # centro horizontal coluna esq

    c = rl_canvas.Canvas(str(output_path), pagesize=A4)

    # ---- helpers internos ---------------------------------------------------

    def _n(val) -> str:
        return str(val) if val is not None else "?"

    def _count_lines(txt: str, max_w: float, font: str = "Helvetica",
                     size: float = FONT_SIZE) -> int:
        """Conta linhas necessárias para caber txt em max_w."""
        n = 0
        for line in txt.split("\n"):
            words = line.split()
            if not words:
                n += 1
                continue
            cur = ""
            for word in words:
                test = (cur + " " + word).strip()
                if stringWidth(test, font, size) <= max_w - 2 * PAD_H:
                    cur = test
                else:
                    if cur:
                        n += 1
                    cur = word
            if cur:
                n += 1
        return max(1, n)

    def _box_h(txt: str, w: float, font: str = "Helvetica") -> float:
        n = _count_lines(txt, w, font)
        return max(26.0, n * LINE_H + 2 * PAD_V)

    def _draw_text_in_box(txt: str, x: float, y_top: float, w: float,
                           h: float, font: str, cor_texto):
        """Desenha texto centrado verticalmente dentro da caixa."""
        lines_raw = txt.split("\n")
        # Expande quebras automáticas
        all_lines = []
        for line in lines_raw:
            words = line.split()
            if not words:
                all_lines.append("")
                continue
            cur = ""
            for word in words:
                test = (cur + " " + word).strip()
                if stringWidth(test, font, FONT_SIZE) <= w - 2 * PAD_H:
                    cur = test
                else:
                    if cur:
                        all_lines.append(cur)
                    cur = word
            if cur:
                all_lines.append(cur)

        total_text_h = len(all_lines) * LINE_H
        # Centraliza verticalmente
        y_start = y_top - (h - total_text_h) / 2 - FONT_SIZE + 1

        c.setFont(font, FONT_SIZE)
        c.setFillColor(cor_texto)
        for i, line in enumerate(all_lines):
            c.drawCentredString(x + w / 2, y_start - i * LINE_H, line)

    def _sanitize_acroform(txt: str) -> str:
        """Remove/substitui caracteres fora do latin-1 que o AcroForm não aceita."""
        replacements = {
            "\u2014": "-", "\u2013": "-",  # em dash, en dash
            "\u2018": "'", "\u2019": "'",  # curly apostrophes
            "\u201c": '"', "\u201d": '"',  # curly quotes
            "\u2026": "...",               # ellipsis
        }
        for ch, rep in replacements.items():
            txt = txt.replace(ch, rep)
        # fallback: strip anything still outside latin-1
        return txt.encode("latin-1", errors="replace").decode("latin-1")

    def draw_box(label: str, n_val, x: float, y_top: float, w: float,
                 auto: bool, field_name: str = "") -> float:
        """
        Desenha caixa e retorna y_bottom.

        Parâmetros:
          label     — texto descritivo da caixa (sem o número)
          n_val     — valor numérico (int/None). None = campo humano não preenchido.
          auto      — True: caixa azul não editável. False: caixa cinza com campo numérico editável.
          field_name— nome do campo AcroForm (usado se auto=False)

        Design:
          - auto=True : texto completo "label (n = N)" em branco no canvas
          - auto=False: label descritivo em cinza no canvas (fixo) +
                        campo AcroForm pequeno apenas para o número
        """
        N_FIELD_W  = 38.0   # largura do campo numérico
        N_FIELD_H  = 14.0   # altura do campo numérico
        FONT_LABEL = "Helvetica"
        FONT_AUTO  = "Helvetica-Bold"

        # Texto completo para calcular altura
        n_str = str(n_val) if n_val is not None else "?"
        if auto:
            full_txt = f"{label}\n(n = {n_str})"
            font = FONT_AUTO
        else:
            full_txt = label  # só o label para calcular altura (número ocupa linha extra)
            font = FONT_LABEL

        h = max(34.0, _box_h(full_txt, w, font) + (0 if auto else N_FIELD_H + PAD_V))

        cor_fundo = _rgb(_COR_AUTO if auto else _COR_HUMANO)
        cor_borda = _rgb(_COR_AUTO if auto else _COR_BORDA)
        cor_texto = _rgb(_COR_TEXTO_AUTO if auto else _COR_TEXTO_HUMANO)

        # --- Retângulo de fundo ---
        c.setLineWidth(1.2 if auto else 0.7)
        c.setStrokeColor(cor_borda)
        c.setFillColor(cor_fundo)
        if auto:
            c.roundRect(x, y_top - h, w, h, 4, fill=1, stroke=1)
        else:
            c.roundRect(x, y_top - h, w, h, 4, fill=1, stroke=0)
            c.setDash(3, 2)
            c.roundRect(x, y_top - h, w, h, 4, fill=0, stroke=1)
            c.setDash()

        if auto:
            _draw_text_in_box(full_txt, x, y_top, w, h, FONT_AUTO, cor_texto)
        else:
            # Desenhar label descritivo no canvas (texto fixo, não editável)
            label_h = _box_h(label, w, FONT_LABEL)
            label_area_h = h - N_FIELD_H - PAD_V
            lines_raw = label.split("\n")
            all_lines = []
            for line in lines_raw:
                words = line.split()
                if not words:
                    all_lines.append("")
                    continue
                cur = ""
                for word in words:
                    test = (cur + " " + word).strip()
                    if stringWidth(test, FONT_LABEL, FONT_SIZE) <= w - 2 * PAD_H:
                        cur = test
                    else:
                        if cur:
                            all_lines.append(cur)
                        cur = word
                if cur:
                    all_lines.append(cur)

            c.setFont(FONT_LABEL, FONT_SIZE)
            c.setFillColor(cor_texto)
            total_lh = len(all_lines) * LINE_H
            y_txt = y_top - PAD_V - FONT_SIZE + 1
            for line in all_lines:
                c.drawCentredString(x + w / 2, y_txt, line)
                y_txt -= LINE_H

            # Campo AcroForm apenas para o número — no rodapé da caixa
            field_y = y_top - h + PAD_V
            field_x = x + (w - N_FIELD_W) / 2
            _val_safe = _sanitize_acroform(str(n_val) if n_val is not None else "")
            c.acroForm.textfield(
                name=field_name or f"field_{label[:10]}",
                tooltip=_sanitize_acroform(f"n = {n_str}"),
                x=field_x,
                y=field_y,
                width=N_FIELD_W,
                height=N_FIELD_H,
                fontSize=FONT_SIZE + 1,
                borderColor=_rgb(_COR_BORDA),
                fillColor=_rgb((1.0, 1.0, 1.0)),
                textColor=_rgb((0.1, 0.1, 0.6)),
                value=_val_safe,
                forceBorder=True,
            )
            # Label "n = " à esquerda do campo
            c.setFont(FONT_LABEL, FONT_SIZE)
            c.setFillColor(cor_texto)
            c.drawRightString(field_x - 2, field_y + 3, "n =")

        return y_top - h

    def draw_fase(txt: str, y_top: float) -> float:
        """Faixa de cabeçalho de fase. Retorna y abaixo."""
        c.setFillColor(_rgb(_COR_FASE))
        c.rect(MARGEM, y_top - FASE_H, AREA_W, FASE_H, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(_rgb((1, 1, 1)))
        c.drawCentredString(W / 2, y_top - FASE_H + 4, txt)
        return y_top - FASE_H - GAP_FASE

    def seta_v(x_c: float, y_from: float, y_to: float):
        c.setStrokeColor(_rgb(_COR_BORDA))
        c.setLineWidth(0.9)
        c.line(x_c, y_from, x_c, y_to + 4)
        c.setFillColor(_rgb(_COR_BORDA))
        p = c.beginPath()
        p.moveTo(x_c - 3.5, y_to + 4)
        p.lineTo(x_c + 3.5, y_to + 4)
        p.lineTo(x_c, y_to)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def seta_h(x_from: float, x_to: float, y: float):
        c.setStrokeColor(_rgb(_COR_BORDA))
        c.setLineWidth(0.8)
        c.line(x_from, y, x_to - 4, y)
        c.setFillColor(_rgb(_COR_BORDA))
        p = c.beginPath()
        p.moveTo(x_to - 4, y + 3)
        p.lineTo(x_to - 4, y - 3)
        p.lineTo(x_to, y)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    # =========================================================================
    # Cabeçalho do documento
    # =========================================================================
    y = H - MARGEM

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(_rgb(_COR_FASE))
    c.drawCentredString(W / 2, y, s("titulo_doc", lang))
    y -= 14

    # Aviso parcial (se há campos humanos em aberto)
    campos_humanos_vazios = any(
        dados.get(k) is None
        for k in ("sought", "assessed", "included_studies")
    )
    if campos_humanos_vazios:
        aviso = s("aviso_parcial", lang)
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(_rgb((0.7, 0.3, 0.0)))
        # Quebra em 2 linhas se necessário
        if stringWidth(aviso, "Helvetica-Oblique", 6.5) > AREA_W:
            meio = len(aviso) // 2
            espaco = aviso.rfind(" ", 0, meio)
            if espaco > 0:
                c.drawCentredString(W / 2, y, aviso[:espaco])
                y -= 9
                c.drawCentredString(W / 2, y, aviso[espaco+1:])
                y -= 10
            else:
                c.drawCentredString(W / 2, y, aviso)
                y -= 10
        else:
            c.drawCentredString(W / 2, y, aviso)
            y -= 10
    else:
        y -= 4

    # =========================================================================
    # FASE 1 — IDENTIFICAÇÃO
    # Layout oficial PRISMA 2020:
    #   Esq: "Records identified from databases (n=X)"
    #   Dir: caixa única "Records removed before screening" com 3 sub-itens:
    #        • Duplicate records removed (n=?)
    #        • Marked ineligible by automation tools (n=X)
    #        • Removed for other reasons (n=X)
    #   Seta horizontal: esq → dir (meio da esq)
    #   ↓
    #   Esq: "Records screened (n=X)"
    # =========================================================================
    y = draw_fase(s("fase_identificacao", lang), y)

    # --- Coluna esquerda: identificados ---
    lbl_id = s("id_databases_label", lang)
    y0       = y
    y_id_bot = draw_box(lbl_id, dados["total_buscado"], COL_L_X, y0, COL_L_W, auto=True)

    # --- Coluna direita: caixa multi-item "removidos antes da triagem" ---
    # Esta caixa é composta (3 sub-items com marcador); 2 são auto, 1 é editável
    # Desenhamos como uma única caixa com texto canvas e um campo AcroForm para duplicatas
    dup    = dados.get("duplicates")   # pode ser None (editável)
    n_aut  = dados.get("automation_removed", 0)
    n_out  = dados.get("erros_outros", 0)

    lbl_removed = s("id_removed_label", lang)
    lbl_dup     = s("id_duplicates_label", lang)
    lbl_aut     = s("id_automation_label", lang)
    lbl_out     = s("id_other_label", lang)

    # Calcula altura: título + 3 sub-itens (cada um ~2 linhas) + campo numérico para dup
    removed_lines = (
        f"{lbl_removed}\n"
        f"  • {lbl_dup}\n"
        f"  • {lbl_aut} (n = {_n(n_aut)})\n"
        f"  • {lbl_out} (n = {_n(n_out)})"
    )
    N_FIELD_W = 38.0
    N_FIELD_H = 14.0
    h_removed = max(60.0, _box_h(removed_lines, COL_R_W, "Helvetica") + N_FIELD_H + PAD_V * 2)

    # Desenhar fundo cinza tracejado (duplicatas é editável) ou azul (se já preenchido)
    if dup is not None:
        c.setFillColor(_rgb(_COR_AUTO))
        c.setStrokeColor(_rgb(_COR_AUTO))
        c.setLineWidth(1.2)
        c.roundRect(COL_R_X, y0 - h_removed, COL_R_W, h_removed, 4, fill=1, stroke=1)
    else:
        c.setFillColor(_rgb(_COR_HUMANO))
        c.setStrokeColor(_rgb(_COR_BORDA))
        c.setLineWidth(0.7)
        c.roundRect(COL_R_X, y0 - h_removed, COL_R_W, h_removed, 4, fill=1, stroke=0)
        c.setDash(3, 2)
        c.roundRect(COL_R_X, y0 - h_removed, COL_R_W, h_removed, 4, fill=0, stroke=1)
        c.setDash()

    # Texto canvas: título + sub-itens fixos
    cor_txt_r = _rgb(_COR_TEXTO_AUTO if dup is not None else _COR_TEXTO_HUMANO)
    c.setFont("Helvetica-Bold", FONT_SIZE)
    c.setFillColor(cor_txt_r)
    c.drawCentredString(COL_R_X + COL_R_W / 2, y0 - PAD_V - FONT_SIZE, lbl_removed)

    c.setFont("Helvetica", FONT_SIZE)
    y_sub = y0 - PAD_V - FONT_SIZE - LINE_H
    c.drawString(COL_R_X + PAD_H, y_sub, f"• {lbl_dup}")
    y_sub -= LINE_H

    # Campo AcroForm para duplicatas (pequeno, só o número)
    field_x_dup = COL_R_X + PAD_H + stringWidth(f"• {lbl_dup}  n = ", "Helvetica", FONT_SIZE)
    field_y_dup = y_sub
    c.drawString(COL_R_X + PAD_H + stringWidth(f"• {lbl_dup} ", "Helvetica", FONT_SIZE),
                 y_sub + 1, "n =")
    _dup_val_safe = _sanitize_acroform(str(dup) if dup is not None else "")
    c.acroForm.textfield(
        name="duplicates",
        tooltip="Registros duplicados removidos",
        x=COL_R_X + PAD_H + stringWidth(f"• {lbl_dup}  n =  ", "Helvetica", FONT_SIZE),
        y=field_y_dup - 2,
        width=N_FIELD_W,
        height=N_FIELD_H,
        fontSize=FONT_SIZE + 1,
        borderColor=_rgb(_COR_BORDA),
        fillColor=_rgb((1.0, 1.0, 1.0)),
        textColor=_rgb((0.1, 0.1, 0.6)),
        value=_dup_val_safe,
        forceBorder=True,
    )
    y_sub -= (LINE_H + 2)
    c.drawString(COL_R_X + PAD_H, y_sub,
                 f"• {lbl_aut} (n = {_n(n_aut)})")
    y_sub -= LINE_H
    c.drawString(COL_R_X + PAD_H, y_sub,
                 f"• {lbl_out} (n = {_n(n_out)})")

    y_removed_bot = y0 - h_removed

    # Seta horizontal: esq → dir (ao nível do meio da caixa esq)
    mid_id = (y0 + y_id_bot) / 2
    seta_h(COL_L_X + COL_L_W, COL_R_X, mid_id)

    # Caixa screened — abaixo do mais baixo
    y_scr_top = min(y_id_bot, y_removed_bot) - GAP
    lbl_scr   = s("id_screened_label", lang)
    y_scr_bot = draw_box(lbl_scr, dados.get("screened"), COL_L_X, y_scr_top, COL_L_W, auto=True)
    seta_v(CX_L, y_id_bot, y_scr_top)

    y = y_scr_bot - GAP

    # =========================================================================
    # FASE 2 — TRIAGEM
    # Layout oficial:
    #   Linha 1: "Records screened" → seta → Linha 1:
    #     Esq: "Reports sought for retrieval"  Dir: "Records excluded (n=?)"
    #   ↓
    #   Linha 2:
    #     Esq: "Reports assessed for eligibility"  Dir: "Reports not retrieved (n=?)"
    #   ↓
    #   Linha 3 (só Dir):
    #     Dir: "Reports excluded: Reason1 (n=?), ..."
    # =========================================================================
    y = draw_fase(s("fase_triagem", lang), y)

    val_excl_scr = dados.get("excluded_screening")
    val_sought   = dados.get("sought")
    val_nr       = dados.get("not_retrieved")
    val_assessed = dados.get("assessed")
    val_excl_elig = dados.get("excluded_eligibility")
    reasons       = dados.get("excluded_reasons", [])

    # Linha 1: sought (esq) | excluded_screening (dir)
    y_t1 = y
    y_sought_bot   = draw_box(s("scr_sought_label", lang),   val_sought,
                               COL_L_X, y_t1, COL_L_W,
                               auto=(val_sought is not None), field_name="sought")
    y_excl_scr_bot = draw_box(s("scr_excluded_label", lang), val_excl_scr,
                               COL_R_X, y_t1, COL_R_W,
                               auto=(val_excl_scr is not None), field_name="excluded_screening")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t1 + min(y_sought_bot, y_excl_scr_bot)) / 2)
    seta_v(CX_L, y_scr_bot, y_t1)

    # Linha 2: assessed (esq) | not_retrieved (dir)
    y_t2 = min(y_sought_bot, y_excl_scr_bot) - GAP
    y_assessed_bot = draw_box(s("scr_assessed_label", lang),     val_assessed,
                               COL_L_X, y_t2, COL_L_W,
                               auto=(val_assessed is not None), field_name="assessed")
    y_nr_bot       = draw_box(s("scr_not_retrieved_label", lang), val_nr,
                               COL_R_X, y_t2, COL_R_W,
                               auto=(val_nr is not None), field_name="not_retrieved")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t2 + min(y_assessed_bot, y_nr_bot)) / 2)
    seta_v(CX_L, y_sought_bot, y_t2)

    # Linha 3: excl_elig (dir) — razões listadas
    reasons_txt = "; ".join(reasons) if reasons else ""
    y_t3 = min(y_assessed_bot, y_nr_bot) - GAP
    lbl_excl_elig = s("scr_excl_reasons_label", lang)
    if reasons_txt:
        lbl_excl_elig += f"\n{reasons_txt}"
    y_excl_elig_bot = draw_box(lbl_excl_elig, val_excl_elig,
                                COL_R_X, y_t3, COL_R_W,
                                auto=(val_excl_elig is not None),
                                field_name="excluded_eligibility")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t3 + y_excl_elig_bot) / 2)
    seta_v(CX_L, y_assessed_bot, y_t3)

    y = min(y_t3, y_excl_elig_bot) - GAP

    # =========================================================================
    # FASE 3 — INCLUSÃO
    # Layout oficial: caixa única com "Studies included (n=X)" + "Reports of included (n=X)"
    # =========================================================================
    y = draw_fase(s("fase_inclusao", lang), y)

    val_inc = dados.get("included_studies")
    val_rep = dados.get("included_reports")

    y_inc_bot = draw_box(s("inc_studies_label", lang), val_inc,
                         COL_L_X, y, COL_L_W,
                         auto=(val_inc is not None), field_name="included_studies")
    seta_v(CX_L, y_t3, y)

    y_rep_top = y_inc_bot - GAP
    draw_box(s("inc_reports_label", lang), val_rep,
             COL_L_X, y_rep_top, COL_L_W,
             auto=(val_rep is not None), field_name="included_reports")
    seta_v(CX_L, y_inc_bot, y_rep_top)

    # =========================================================================
    # Rodapé
    # =========================================================================
    data_hoje = DT.now().strftime("%Y-%m-%d")
    nota = s("nota_prisma", lang, ver=__version__, data=data_hoje)
    c.setFont("Helvetica", 5.5)
    c.setFillColor(_rgb((0.55, 0.55, 0.55)))
    # Quebra em 2 linhas se necessário
    metade = len(nota) // 2
    espaco = nota.rfind(" ", 0, metade)
    if espaco > 0 and stringWidth(nota, "Helvetica", 5.5) > AREA_W:
        c.drawCentredString(W / 2, 20, nota[:espaco])
        c.drawCentredString(W / 2, 13, nota[espaco+1:])
    else:
        c.drawCentredString(W / 2, 16, nota)

    c.showPage()
    c.save()
    print(f"  ✓ {output_path}")


# ---------------------------------------------------------------------------
# PDF artístico — Systemic Passage
# ---------------------------------------------------------------------------

def gerar_pdf_artistico(dados: dict, output_path: Path, lang: str = "pt"):  # noqa: C901
    """
    Gera o PDF PRISMA 2020 no estilo artístico 'Systemic Passage'.

    Campos automáticos: texto fixo desenhado no canvas (não editável).
    Campos humanos: label fixo no canvas + AcroForm textfield apenas para o n=
      posicionado exatamente sobre o placeholder, fundo transparente.
    """
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white, Color
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        print("❌  reportlab não instalado. Execute: uv pip install reportlab",
              file=sys.stderr)
        sys.exit(1)

    from datetime import datetime as DT

    # ── Fontes ───────────────────────────────────────────────────────────────
    # Tenta carregar fontes do diretório canvas-design; cai em Helvetica se ausentes
    _canvas_fonts = Path(__file__).parent.parent / "AppData/Roaming/Claude/local-agent-mode-sessions"
    # Busca genérica em pastas comuns
    _font_search = [
        Path.home() / "AppData/Roaming/Claude/local-agent-mode-sessions",
        Path(__file__).parent / "canvas-fonts",
        Path.home() / ".claude/skills/canvas-design/canvas-fonts",
    ]
    # Encontra a primeira pasta com os arquivos
    _font_dir: Path | None = None
    for _fd in _font_search:
        if (_fd / "GeistMono-Regular.ttf").exists():
            _font_dir = _fd
            break
    # Se não encontrar busca recursiva mais ampla (skills-plugin)
    if _font_dir is None:
        for _base in [Path.home() / "AppData/Roaming/Claude"]:
            for _fp in _base.rglob("GeistMono-Regular.ttf"):
                _font_dir = _fp.parent
                break
            if _font_dir:
                break

    def _reg(name, fname, fallback="Helvetica"):
        if _font_dir and (_font_dir / fname).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(_font_dir / fname)))
                return name
            except Exception:
                pass
        return fallback

    F_MONO     = _reg("ArtMono",    "GeistMono-Regular.ttf")
    F_MONOB    = _reg("ArtMonoB",   "GeistMono-Bold.ttf")
    F_SERIF    = _reg("ArtSerif",   "IBMPlexSerif-Regular.ttf")
    F_SERIFIT  = _reg("ArtSerifIt", "IBMPlexSerif-Italic.ttf")
    F_SANS     = _reg("ArtSans",    "InstrumentSans-Regular.ttf")
    F_SANSB    = _reg("ArtSansB",   "InstrumentSans-Bold.ttf")
    F_JURA     = _reg("ArtJura",    "Jura-Light.ttf")
    F_JURAB    = _reg("ArtJuraB",   "Jura-Medium.ttf")

    # ── Paleta ───────────────────────────────────────────────────────────────
    C_INK      = HexColor("#18243a")
    C_KEPT     = HexColor("#1a3d6e")
    C_KEPT_LT  = HexColor("#eaf0f8")
    C_EXCL     = HexColor("#7a8fa8")
    C_EXCL_LT  = HexColor("#f2f5f9")
    C_AMBER    = HexColor("#b07d10")
    C_AMBER_LT = HexColor("#fdf6e3")
    C_LINE     = HexColor("#2c5282")
    C_RULE     = HexColor("#d0dae6")
    C_BG       = HexColor("#f8fafc")
    C_HUMAN    = HexColor("#4a7ab5")   # tint for editable number placeholder

    PAGE_W, PAGE_H = A4

    # ── Helpers de desenho ───────────────────────────────────────────────────

    def rbox(c, x, y, w, h, fill, stroke, sw=0.75, r=2.5):
        c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(sw)
        c.roundRect(x, y, w, h, r, fill=1, stroke=1)

    def vline(c, x, y1, y2, color=None, w=0.65):
        c.setStrokeColor(color or C_LINE); c.setLineWidth(w)
        c.line(x, y1, x, y2)

    def hline(c, x1, x2, y, color=None, w=0.65):
        c.setStrokeColor(color or C_EXCL); c.setLineWidth(w)
        c.line(x1, y, x2, y)

    def arrow_down(c, x, y_from, y_to, color=None):
        col = color or C_LINE
        c.setStrokeColor(col); c.setFillColor(col); c.setLineWidth(0.75)
        c.line(x, y_from, x, y_to + 5)
        aw = 3.5
        p = c.beginPath()
        p.moveTo(x, y_to); p.lineTo(x - aw, y_to + 7); p.lineTo(x + aw, y_to + 7)
        p.close(); c.drawPath(p, fill=1, stroke=0)

    def arr_right(c, x_from, x_to, y, color=None):
        col = color or C_EXCL
        c.setStrokeColor(col); c.setFillColor(col); c.setLineWidth(0.65)
        c.line(x_from, y, x_to - 5, y)
        aw = 3.2
        p = c.beginPath()
        p.moveTo(x_to, y); p.lineTo(x_to - 7, y - aw); p.lineTo(x_to - 7, y + aw)
        p.close(); c.drawPath(p, fill=1, stroke=0)

    def phase_band(c, x, y_bot, w, h, label):
        c.setFillColor(HexColor("#dce8f4"))
        c.setStrokeColor(C_RULE); c.setLineWidth(0.3)
        c.roundRect(x, y_bot, w, h, 2, fill=1, stroke=1)
        c.saveState()
        c.setFont(F_JURAB, 6.2); c.setFillColor(C_KEPT)
        c.translate(x + w / 2, y_bot + h / 2)
        c.rotate(90)
        c.drawCentredString(0, -2, label.upper())
        c.restoreState()

    # ── Campo AcroForm para número humano ────────────────────────────────────
    def acro_n(c, cx, cy, value, field_name, w=40, h=14, auto=False):
        """
        Desenha o número n= na posição (cx, cy).
        auto=True: texto fixo no canvas (azul escuro).
        auto=False: label 'n =' fixo + AcroForm textfield sobre o '?'.
        """
        if auto:
            c.setFont(F_MONOB, 9); c.setFillColor(C_KEPT)
            txt = f"n  =  {value}" if value is not None else "n  =  ?"
            c.drawCentredString(cx, cy, txt)
        else:
            # Label fixo
            c.setFont(F_MONO, 8); c.setFillColor(C_HUMAN)
            c.drawCentredString(cx - 10, cy, "n  =")
            # AcroForm field para o número — posicionado à direita do "n ="
            fx = cx - 10 + 22
            fy = cy - 3
            fw, fh = w, h
            _sanitize = lambda v: str(v).replace("\u2014", "-").replace("\u2013", "-") if v else ""
            val_str = _sanitize(value) if value is not None else ""
            try:
                c.acroForm.textfield(
                    name=field_name,
                    tooltip=f"Preencher: {field_name}",
                    x=fx, y=fy, width=fw, height=fh,
                    value=val_str,
                    fontSize=8,
                    fontName="Helvetica",
                    fillColor=Color(0, 0, 0, 0),   # transparente
                    borderColor=C_HUMAN,
                    borderWidth=0.5,
                    textColor=C_KEPT,
                )
            except Exception:
                # Fallback: só texto
                c.setFont(F_MONO, 8); c.setFillColor(C_HUMAN)
                c.drawString(fx, fy + 3, val_str or "?")

    # ── Caixa principal ──────────────────────────────────────────────────────
    def main_box(c, x, y, w, h, label_lines, value, field_name, auto=True):
        rbox(c, x, y, w, h, C_KEPT_LT, C_KEPT, 0.9)
        cx = x + w / 2
        lh = 8.5; n_h = 10
        total = len(label_lines) * lh + 5 + n_h
        top = y + h / 2 + total / 2 - lh * 0.8
        c.setFont(F_SANS, 6.6); c.setFillColor(C_INK)
        for i, txt in enumerate(label_lines):
            c.drawCentredString(cx, top - i * lh, txt)
        n_cy = top - len(label_lines) * lh - 5
        acro_n(c, cx, n_cy, value, field_name, auto=auto)

    # ── Caixa de exclusão ────────────────────────────────────────────────────
    def excl_box(c, x, y, w, h, label_lines, value, field_name, auto=False):
        rbox(c, x, y, w, h, C_EXCL_LT, C_EXCL, 0.6)
        cx = x + w / 2
        lh = 7.5
        n_lines = len(label_lines)
        label_top = y + h / 2 + (n_lines * lh) / 2
        c.setFont(F_SANS, 5.9); c.setFillColor(C_EXCL)
        for i, txt in enumerate(label_lines):
            c.drawCentredString(cx, label_top - i * lh, txt)
        n_cy = y + h / 2 - 10
        acro_n(c, cx, n_cy, value, field_name, auto=auto, w=36, h=13)

    # ── Caixa amber (outras fontes) ──────────────────────────────────────────
    def amber_box(c, x, y, w, h, label_lines, value, field_name, auto=True):
        rbox(c, x, y, w, h, C_AMBER_LT, C_AMBER, 0.75)
        cx = x + w / 2
        lh = 8; n_h = 10
        total = len(label_lines) * lh + 5 + n_h
        top = y + h / 2 + total / 2 - lh * 0.8
        c.setFont(F_SANS, 6); c.setFillColor(HexColor("#7a5800"))
        for i, txt in enumerate(label_lines):
            c.drawCentredString(cx, top - i * lh, txt)
        n_cy = top - len(label_lines) * lh - 5
        c.setFont(F_MONOB if auto else F_MONO, 8)
        c.setFillColor(C_AMBER if auto else C_HUMAN)
        txt = f"n  =  {value}" if value is not None else "n  =  ?"
        c.drawCentredString(cx, n_cy, txt)

    # ── Layout ───────────────────────────────────────────────────────────────
    ML    = 13; BW = 14.5; GAP_B = 3
    COL_X = ML + BW + GAP_B
    COL_W = 96
    CX    = COL_X + COL_W / 2
    EXCL_GAP = 7
    EXCL_X   = COL_X + COL_W + EXCL_GAP
    EXCL_W   = 53
    EXCL_CX  = EXCL_X + EXCL_W / 2

    # Converter mm → pt
    mm = 2.8346
    COL_X *= mm; COL_W *= mm; CX *= mm
    EXCL_X *= mm; EXCL_W *= mm; EXCL_CX *= mm
    ML *= mm; BW *= mm; GAP_B *= mm

    TOP_MARGIN = 14 * mm; BOT_MARGIN = 13 * mm; TITLE_H = 17 * mm
    USABLE_H = PAGE_H - TOP_MARGIN - BOT_MARGIN - TITLE_H
    BH = USABLE_H / 9.5; ARROW = BH * 0.45; BH_INC = BH * 1.5

    def _y(i):
        base = PAGE_H - TOP_MARGIN - TITLE_H
        if i == 0:
            return base - BH
        elif i < 5:
            return _y(i - 1) - ARROW - BH
        else:
            return _y(4) - ARROW - BH_INC

    # ── Dados ────────────────────────────────────────────────────────────────
    d = dados
    _n = lambda k, default=None: d.get(k, default)

    lang_lbl = {
        "pt": {
            "title":    "PRISMA 2020",
            "subtitle": "Preferential Reporting Items for Systematic Reviews and Meta-Analyses",
            "id":       "IDENTIFICAÇÃO",
            "scr":      "TRIAGEM",
            "inc":      "INCLUSÃO",
            "databases":    ["Registros identificados", "nas bases de dados"],
            "other_src":    ["Registros de", "outras fontes"],
            "deduped":      ["Registros após remoção", "de duplicatas"],
            "duplicates":   ["Duplicatas removidas"],
            "screened":     ["Registros selecionados", "para triagem"],
            "excl_scr":     ["Registros excluídos", "(título / resumo)"],
            "sought":       ["Relatórios buscados", "para recuperação"],
            "not_retr":     ["Relatórios não", "recuperados"],
            "assessed":     ["Relatórios avaliados", "para elegibilidade"],
            "excl_elig":    ["Relatórios excluídos", "por elegibilidade"],
            "included":     ["Estudos incluídos", "na revisão"],
            "colophon":     "Page & Moher et al. (2021). BMJ 372:n71  ·  prisma-statement.org",
        },
        "en": {
            "title":    "PRISMA 2020",
            "subtitle": "Preferred Reporting Items for Systematic Reviews and Meta-Analyses",
            "id":       "IDENTIFICATION",
            "scr":      "SCREENING",
            "inc":      "INCLUDED",
            "databases":    ["Records identified", "from databases"],
            "other_src":    ["Records from", "other sources"],
            "deduped":      ["Records after", "duplicates removed"],
            "duplicates":   ["Duplicates removed"],
            "screened":     ["Records screened"],
            "excl_scr":     ["Records excluded", "(title / abstract)"],
            "sought":       ["Reports sought", "for retrieval"],
            "not_retr":     ["Reports not retrieved"],
            "assessed":     ["Reports assessed", "for eligibility"],
            "excl_elig":    ["Reports excluded", "— reasons"],
            "included":     ["Studies included", "in review"],
            "colophon":     "Page & Moher et al. (2021). BMJ 372:n71  ·  prisma-statement.org",
        },
    }
    L = lang_lbl.get(lang, lang_lbl["pt"])

    # ── Canvas ───────────────────────────────────────────────────────────────
    c = rl_canvas.Canvas(str(output_path), pagesize=A4)

    # Background
    c.setFillColor(C_BG); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Grid faint
    c.setStrokeColor(C_RULE); c.setLineWidth(0.18)
    step = int(14 * mm)
    for gy in range(0, int(PAGE_H) + step, step):
        c.line(0, gy, PAGE_W, gy)

    # Watermark
    c.saveState()
    c.setFont(F_SERIFIT, 60); c.setFillColor(HexColor("#dde7f3"))
    c.translate(PAGE_W - 10 * mm, PAGE_H - 15 * mm)
    c.rotate(-12)
    c.drawRightString(0, 0, "EVIDENCE")
    c.restoreState()

    # Título
    ty = PAGE_H - TOP_MARGIN
    c.setFont(F_SERIF, 10.5); c.setFillColor(C_INK)
    c.drawString(COL_X, ty, L["title"])
    c.setFont(F_SERIFIT, 6.4); c.setFillColor(C_EXCL)
    c.drawString(COL_X, ty - 10, L["subtitle"])
    c.setStrokeColor(C_LINE); c.setLineWidth(0.85)
    c.line(COL_X, ty - 14, COL_X + COL_W, ty - 14)

    # Phase bands
    PAD = 2 * mm
    id_top  = _y(0) + BH + PAD;  id_bot  = _y(1) - PAD
    scr_top = _y(2) + BH + PAD;  scr_bot = _y(4) - PAD
    inc_top = _y(5) + BH_INC + PAD; inc_bot = _y(5) - PAD
    phase_band(c, ML, id_bot,  BW, id_top  - id_bot,  L["id"])
    phase_band(c, ML, scr_bot, BW, scr_top - scr_bot, L["scr"])
    phase_band(c, ML, inc_bot, BW, inc_top - inc_bot,  L["inc"])

    # ── BOX 0: databases ──────────────────────────────────────────────────
    b0 = _y(0)
    main_box(c, COL_X, b0, COL_W, BH, L["databases"],
             _n("total_buscado"), "total_buscado", auto=True)

    # Amber box: outras fontes (n editável se quiser, aqui fixo 0)
    amber_box(c, EXCL_X, b0, EXCL_W, BH, L["other_src"], None, "other_sources", auto=False)

    # Merge arrow
    join_y = b0 - ARROW * 0.5
    vline(c, EXCL_CX, b0, join_y, color=C_AMBER, w=0.55)
    hline(c, EXCL_CX, CX, join_y, color=C_AMBER, w=0.55)
    arrow_down(c, CX, b0, _y(0) - ARROW)

    # ── BOX 1: deduped ────────────────────────────────────────────────────
    b1 = _y(1)
    screened_auto = _n("screened")
    main_box(c, COL_X, b1, COL_W, BH, L["deduped"],
             screened_auto, "screened_auto", auto=True)

    mid1 = b1 + BH / 2
    arr_right(c, COL_X + COL_W, EXCL_X + EXCL_W, mid1)
    excl_box(c, EXCL_X, mid1 - BH / 2, EXCL_W, BH,
             L["duplicates"], _n("duplicates", 0), "duplicates", auto=False)

    arrow_down(c, CX, b1, _y(1) - ARROW)

    # ── BOX 2: screened ───────────────────────────────────────────────────
    b2 = _y(2)
    main_box(c, COL_X, b2, COL_W, BH, L["screened"],
             screened_auto, "screened_display", auto=True)

    mid2 = b2 + BH / 2
    arr_right(c, COL_X + COL_W, EXCL_X + EXCL_W, mid2)
    excl_box(c, EXCL_X, mid2 - BH / 2, EXCL_W, BH,
             L["excl_scr"], _n("excluded_screening"), "excluded_screening", auto=False)

    arrow_down(c, CX, b2, _y(2) - ARROW)

    # ── BOX 3: sought ─────────────────────────────────────────────────────
    b3 = _y(3)
    main_box(c, COL_X, b3, COL_W, BH, L["sought"],
             _n("sought"), "sought", auto=False)

    mid3 = b3 + BH / 2
    arr_right(c, COL_X + COL_W, EXCL_X + EXCL_W, mid3)
    excl_box(c, EXCL_X, mid3 - BH / 2, EXCL_W, BH,
             L["not_retr"], _n("not_retrieved"), "not_retrieved", auto=False)

    arrow_down(c, CX, b3, _y(3) - ARROW)

    # ── BOX 4: assessed ───────────────────────────────────────────────────
    b4 = _y(4)
    main_box(c, COL_X, b4, COL_W, BH, L["assessed"],
             _n("assessed"), "assessed", auto=False)

    mid4 = b4 + BH / 2
    EXCL_H4 = BH * 2.1
    arr_right(c, COL_X + COL_W, EXCL_X + EXCL_W, mid4)
    rbox(c, EXCL_X, mid4 - EXCL_H4 / 2, EXCL_W, EXCL_H4, C_EXCL_LT, C_EXCL, 0.6)
    # Label "excluídos — razões" fixo + campo único para n total
    c.setFont(F_SANSB, 5.8); c.setFillColor(C_EXCL)
    c.drawCentredString(EXCL_CX, mid4 + EXCL_H4 / 2 - 9, L["excl_elig"][0])
    # Sub-itens: 4 razões editáveis individualmente
    reasons_labels = [
        ("excl_wrong_population",  "  Pop. inadequada"),
        ("excl_wrong_intervention","  Interv. inadequada"),
        ("excl_wrong_outcome",     "  Desfecho inadequado"),
        ("excl_other",             "  Outros motivos"),
    ]
    ry0 = mid4 + EXCL_H4 / 2 - 18
    for i, (fname, lbl) in enumerate(reasons_labels):
        ry = ry0 - i * 13
        c.setFont(F_MONO, 5); c.setFillColor(C_EXCL)
        c.drawString(EXCL_X + 4, ry + 3, lbl)
        # Campo AcroForm inline
        try:
            c.acroForm.textfield(
                name=fname, tooltip=lbl,
                x=EXCL_X + EXCL_W - 26, y=ry,
                width=22, height=11,
                value="", fontSize=7, fontName="Helvetica",
                fillColor=Color(0, 0, 0, 0),
                borderColor=C_HUMAN, borderWidth=0.4,
                textColor=C_KEPT,
            )
        except Exception:
            pass

    arrow_down(c, CX, b4, _y(4) - ARROW)

    # ── BOX 5: included ───────────────────────────────────────────────────
    b5 = _y(5)
    rbox(c, COL_X, b5, COL_W, BH_INC, C_KEPT_LT, C_KEPT, 1.1)
    c.setFont(F_SANSB, 8.5); c.setFillColor(C_KEPT)
    inc_label = " ".join(L["included"])
    c.drawCentredString(CX, b5 + BH_INC / 2 + 6, inc_label)
    acro_n(c, CX, b5 + BH_INC / 2 - 8, _n("included_studies"), "included_studies",
           auto=False, w=50, h=14)

    # ── Colophon ──────────────────────────────────────────────────────────
    FOOT = BOT_MARGIN - 3 * mm
    c.setStrokeColor(C_RULE); c.setLineWidth(0.4)
    c.line(ML, FOOT + 7, PAGE_W - ML, FOOT + 7)
    c.setFont(F_JURA, 4.8); c.setFillColor(C_EXCL)
    c.drawString(ML, FOOT, L["colophon"])
    c.setFont(F_MONO, 4.8)
    c.drawRightString(PAGE_W - ML, FOOT, f"Systemic Passage  v{__version__}  {lang.upper()}")

    c.showPage()
    c.save()
    print(f"  ✓ {output_path}")


# ---------------------------------------------------------------------------
# Descoberta automática de JSON
# ---------------------------------------------------------------------------

def _descobrir_json(input_arg: str | None, interativo: bool) -> Path:
    """
    Resolve o caminho para results_report.json.
    Ordem de busca (se não passado):
      1. results_report.json no diretório corrente
      2. Mais recente em runs/*/results_*/results_report.json
      3. Mais recente em results_*/results_report.json
    Em modo interativo, lista as opções e pergunta ao usuário.
    """
    if input_arg is not None:
        p = Path(input_arg)
        if not p.exists():
            print(f"❌  Arquivo não encontrado: {p}", file=sys.stderr)
            print(f"    Este script precisa do results_report.json gerado pelo results_report.py.",
                  file=sys.stderr)
            print(f"    Gere-o com:", file=sys.stderr)
            print(f"      uv run python results_report.py --scrape-dir <pasta_scraping>/",
                  file=sys.stderr)
            print(f"    O arquivo fica em: <pasta_scraping>/results_<stem>/results_report.json",
                  file=sys.stderr)
            sys.exit(1)
        return p

    # Auto-descoberta — ordena por data de modificação (mais recente primeiro)
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    vistos: set[Path] = set()
    candidatos: list[Path] = []

    def _add(paths):
        for p in sorted(paths, key=_mtime, reverse=True):
            rp = p.resolve()
            if rp not in vistos:
                vistos.add(rp)
                candidatos.append(p)

    # 1. Diretório corrente
    local = Path("results_report.json")
    if local.exists():
        _add([local])

    # 2. runs/*/results_*/  (mais recente por mtime)
    _add(Path(".").glob("runs/*/results_*/results_report.json"))

    # 3. results_*/  (pastas ao lado do diretório corrente)
    _add(Path(".").glob("results_*/results_report.json"))

    if not candidatos:
        print("❌  Nenhum results_report.json encontrado.", file=sys.stderr)
        print(f"    Gere-o primeiro com:", file=sys.stderr)
        print(f"      uv run python results_report.py --scrape-dir <pasta_scraping>/",
              file=sys.stderr)
        print(f"    O arquivo fica em: <pasta_scraping>/results_<stem>/results_report.json",
              file=sys.stderr)
        print(f"    Ou passe o caminho diretamente: prisma_workflow.py <caminho/results_report.json>",
              file=sys.stderr)
        sys.exit(1)

    if len(candidatos) == 1 and not interativo:
        print(f"  JSON descoberto: {candidatos[0]}")
        return candidatos[0]

    # Múltiplos candidatos ou modo interativo: pergunta ao usuário
    print("\nresults_report.json encontrados:\n")
    for i, c in enumerate(candidatos[:10], 1):
        print(f"  {i}. {c}")
    print()
    while True:
        resp = input("  Qual usar? (número, ou Enter para o mais recente [1]): ").strip()
        if not resp:
            return candidatos[0]
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(candidatos):
                return candidatos[idx]
        except ValueError:
            pass
        print("  Opção inválida.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "-?" in sys.argv:
        sys.argv[sys.argv.index("-?")] = "--help"

    parser = argparse.ArgumentParser(
        prog="prisma_workflow.py",
        description=(
            "Gera formulário PDF preenchível PRISMA 2020 a partir do results_report.json. "
            "Os campos da fase de Identificação são pré-preenchidos automaticamente. "
            "Os campos das fases de Triagem e Inclusão são editáveis no PDF."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  uv run python prisma_workflow.py results_report.json\n"
            "  uv run python prisma_workflow.py results_report.json -i\n"
            "  uv run python prisma_workflow.py results_report.json --human-data humano.json\n"
            "  uv run python prisma_workflow.py results_report.json --included 13 --lang en\n"
            "  uv run python prisma_workflow.py results_report.json --dry-run\n"
        ),
    )

    parser.add_argument("input", metavar="JSON", nargs="?", default=None,
                        help="results_report.json gerado pelo results_report.py. "
                             "Se omitido, busca automaticamente no diretório atual e em runs/.")
    parser.add_argument(
        "--human-data", metavar="ARQUIVO", default=None,
        help="JSON ou CSV com dados das fases humanas (key=campo, value=n). "
             "CLI tem prioridade sobre o arquivo.",
    )
    # Fase triagem
    parser.add_argument("--excluded-screening", metavar="N", type=int, default=None,
                        help="Registros excluídos na triagem (título/resumo).")
    parser.add_argument("--sought", metavar="N", type=int, default=None,
                        help="Relatórios buscados para recuperação.")
    parser.add_argument("--not-retrieved", metavar="N", type=int, default=None,
                        help="Relatórios não recuperados.")
    parser.add_argument("--assessed", metavar="N", type=int, default=None,
                        help="Relatórios avaliados para elegibilidade.")
    parser.add_argument("--excluded-eligibility", metavar="N", type=int, default=None,
                        help="Relatórios excluídos por elegibilidade.")
    parser.add_argument("--duplicates", metavar="N", type=int, default=None,
                        help="Registros duplicados removidos (default: 0).")
    # Fase inclusão
    parser.add_argument("--included", metavar="N", type=int, default=None,
                        help="Estudos incluídos na revisão.")
    parser.add_argument("--included-reports", metavar="N", type=int, default=None,
                        help="Relatórios dos estudos incluídos.")
    # Modo interativo
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Modo interativo: pergunta os dados humanos ausentes no terminal.")
    # Saída
    parser.add_argument("--output-dir", metavar="DIR", default=None,
                        help="Pasta de saída (default: mesmo diretório do JSON de entrada).")
    parser.add_argument("--lang", choices=["pt", "en"], default="pt",
                        help="Idioma do PDF: pt (default) | en.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra os dados que seriam usados sem gerar o PDF.")
    parser.add_argument(
        "--style", choices=["default", "artistic"], default="default",
        help=(
            "Estilo visual do PDF: "
            "'default' (diagrama funcional clássico, padrão) | "
            "'artistic' (layout Systemic Passage — tipografia refinada, paleta institucional, "
            "campos editáveis apenas nos números n=)."
        ),
    )
    parser.add_argument("--version", action="version",
                        version=f"prisma_workflow.py v{__version__}")

    args = parser.parse_args()

    # --- Descoberta automática do JSON ----------------------------------------
    json_path = _descobrir_json(args.input, args.interactive)

    # --- Carregar dados automáticos -------------------------------------------
    print(f"\nprisma_workflow.py v{__version__}")
    print(f"Input JSON       : {json_path.resolve()}")

    try:
        auto = carregar_dados_automaticos(json_path)
    except KeyError as e:
        print(f"❌  JSON inválido ou incompleto: chave ausente {e}", file=sys.stderr)
        print(f"    Verifique se o arquivo é um results_report.json gerado pelo results_report.py.",
              file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌  Erro ao ler JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Dados humanos do arquivo ---------------------------------------------
    human_file: dict = {}
    if args.human_data:
        human_file = carregar_human_data(Path(args.human_data))

    # --- Merge (arquivo + CLI) ------------------------------------------------
    dados = merge_human(auto, human_file, args)

    # --- Modo interativo ------------------------------------------------------
    if args.interactive:
        dados = modo_interativo(dados, args.lang)

    # --- Dry run --------------------------------------------------------------
    print(f"\nDados para o PDF:")
    print(f"  Anos             : {dados.get('anos')}")
    print(f"  Termos           : {dados.get('termos')}")
    print(f"  Buscados         : {dados.get('total_buscado')}")
    print(f"  Duplicatas       : {dados.get('duplicates', 0)}")
    print(f"  Automação        : {dados.get('automation_removed')}")
    print(f"  Erros/outros     : {dados.get('erros_outros')}")
    print(f"  Triagem          : {dados.get('screened')}")
    print(f"  Excl. triagem    : {dados.get('excluded_screening') or '(a preencher)'}")
    print(f"  Buscados recup.  : {dados.get('sought') or '(a preencher)'}")
    print(f"  Não recuperados  : {dados.get('not_retrieved') or '(a preencher)'}")
    print(f"  Avaliados elig.  : {dados.get('assessed') or '(a preencher)'}")
    print(f"  Excl. elig.      : {dados.get('excluded_eligibility') or '(a preencher)'}")
    print(f"  Razões excl.     : {dados.get('excluded_reasons') or '(a preencher)'}")
    print(f"  Incluídos        : {dados.get('included_studies') or '(a preencher)'}")
    print(f"  Relatórios inc.  : {dados.get('included_reports') or '(a preencher)'}")
    print(f"  Idioma           : {args.lang}")

    if args.dry_run:
        print("\n[dry-run] PDF não gerado.")
        return

    # --- Pasta de saída -------------------------------------------------------
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = json_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    stem = json_path.stem  # ex: results_report
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = output_dir / f"prisma_{stem}_{args.lang}_{ts}.pdf"

    print(f"\n  Gerando PDF... (estilo: {args.style})")
    if args.style == "artistic":
        gerar_pdf_artistico(dados, pdf_path, lang=args.lang)
    else:
        gerar_pdf(dados, pdf_path, lang=args.lang)
    print(f"\nPronto. PDF em: {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
