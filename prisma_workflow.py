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
import json
import sys
from pathlib import Path

# UTF-8 no terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

__version__ = "1.0"

# ---------------------------------------------------------------------------
# Strings i18n
# ---------------------------------------------------------------------------

STRINGS = {
    # Fases
    "fase_identificacao":  {"pt": "IDENTIFICAÇÃO",  "en": "IDENTIFICATION"},
    "fase_triagem":        {"pt": "TRIAGEM",         "en": "SCREENING"},
    "fase_inclusao":       {"pt": "INCLUSÃO",        "en": "INCLUDED"},

    # Caixas — Identificação
    "id_databases":        {"pt": "Registros identificados nas bases de dados\n(n = {n})",
                            "en": "Records identified from databases\n(n = {n})"},
    "id_duplicates":       {"pt": "Registros duplicados removidos\n(n = {n})",
                            "en": "Duplicate records removed\n(n = {n})"},
    "id_automation":       {"pt": "Registros marcados como inelegíveis\npor ferramentas de automação\n(n = {n})",
                            "en": "Records marked as ineligible\nby automation tools\n(n = {n})"},
    "id_other":            {"pt": "Registros removidos por outros motivos\n(erros de acesso, PID inválido)\n(n = {n})",
                            "en": "Records removed for other reasons\n(access errors, invalid PID)\n(n = {n})"},
    "id_screened":         {"pt": "Registros selecionados para triagem\n(n = {n})",
                            "en": "Records screened\n(n = {n})"},

    # Caixas — Triagem
    "scr_excluded":        {"pt": "Registros excluídos na triagem\n(título/resumo)\n(n = {n})",
                            "en": "Records excluded\n(title/abstract screening)\n(n = {n})"},
    "scr_sought":          {"pt": "Relatórios buscados para recuperação\n(n = {n})",
                            "en": "Reports sought for retrieval\n(n = {n})"},
    "scr_not_retrieved":   {"pt": "Relatórios não recuperados\n(n = {n})",
                            "en": "Reports not retrieved\n(n = {n})"},
    "scr_assessed":        {"pt": "Relatórios avaliados para elegibilidade\n(n = {n})",
                            "en": "Reports assessed for eligibility\n(n = {n})"},
    "scr_excl_reasons":    {"pt": "Relatórios excluídos\ncom razões:\n{reasons}",
                            "en": "Reports excluded\nwith reasons:\n{reasons}"},

    # Caixas — Inclusão
    "inc_studies":         {"pt": "Estudos incluídos na revisão\n(n = {n})",
                            "en": "Studies included in review\n(n = {n})"},
    "inc_reports":         {"pt": "Relatórios dos estudos incluídos\n(n = {n})",
                            "en": "Reports of included studies\n(n = {n})"},

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


def gerar_pdf(dados: dict, output_path: Path, lang: str = "pt"):
    """Gera o PDF PRISMA 2020 A4 com reportlab."""
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

    def draw_box(txt: str, x: float, y_top: float, w: float,
                 auto: bool, field_name: str = "") -> float:
        """
        Desenha caixa e retorna y_bottom.
        auto=True  → azul, texto branco, não editável
        auto=False → cinza claro, borda tracejada, campo AcroForm editável
                     (valor inicial = txt para guiar o usuário)
        """
        from reportlab.lib.colors import Color
        font      = "Helvetica-Bold" if auto else "Helvetica"
        cor_fundo = _rgb(_COR_AUTO    if auto else _COR_HUMANO)
        cor_texto = _rgb(_COR_TEXTO_AUTO if auto else _COR_TEXTO_HUMANO)
        cor_borda = _rgb(_COR_AUTO    if auto else _COR_BORDA)

        h = _box_h(txt, w, font)

        # --- Retângulo de fundo ---
        c.setStrokeColor(cor_borda)
        c.setFillColor(cor_fundo)
        c.setLineWidth(1.2 if auto else 0.7)
        if auto:
            c.roundRect(x, y_top - h, w, h, 4, fill=1, stroke=1)
        else:
            # Caixas humanas: borda tracejada + fundo cinza claro
            c.roundRect(x, y_top - h, w, h, 4, fill=1, stroke=0)
            c.setDash(3, 2)
            c.roundRect(x, y_top - h, w, h, 4, fill=0, stroke=1)
            c.setDash()

        if auto:
            # Texto desenhado diretamente (não editável)
            _draw_text_in_box(txt, x, y_top, w, h, font, cor_texto)
        else:
            # Campo AcroForm editável: valor inicial = label para orientar o usuário
            # O label explica o que preencher; o usuário apaga e digita o número
            _txt_safe = _sanitize_acroform(txt)
            c.acroForm.textfield(
                name=field_name,
                tooltip=_txt_safe,     # aparece ao passar o mouse
                x=x + 3,
                y=y_top - h + 3,
                width=w - 6,
                height=h - 6,
                fontSize=FONT_SIZE,
                borderColor=_rgb(_COR_BORDA),
                fillColor=_rgb((0.97, 0.97, 0.97)),
                textColor=_rgb(_COR_TEXTO_HUMANO),
                value=_txt_safe,       # texto inicial orientativo
                forceBorder=True,
                fieldFlags="multiline",
            )

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
    # =========================================================================
    y = draw_fase(s("fase_identificacao", lang), y)

    # Caixa: buscados
    txt_id = s("id_databases", lang, n=_n(dados["total_buscado"]))
    y0 = y
    y_id_bot = draw_box(txt_id, COL_L_X, y0, COL_L_W, auto=True)

    # Sub-caixas de remoção (coluna direita) — alinhadas com y0
    y_r = y0

    # duplicatas (editável se não informado)
    dup = dados.get("duplicates")
    txt_dup = s("id_duplicates", lang, n=_n(dup if dup is not None else None))
    y_dup_bot = draw_box(txt_dup, COL_R_X, y_r, COL_R_W,
                         auto=(dup is not None),
                         field_name="duplicates")
    y_r = y_dup_bot - GAP

    # automação
    txt_aut = s("id_automation", lang, n=_n(dados.get("automation_removed", 0)))
    y_aut_bot = draw_box(txt_aut, COL_R_X, y_r, COL_R_W, auto=True)
    y_r = y_aut_bot - GAP

    # outros
    txt_out = s("id_other", lang, n=_n(dados.get("erros_outros", 0)))
    y_out_bot = draw_box(txt_out, COL_R_X, y_r, COL_R_W, auto=True)

    # Seta horizontal (fluxo → exclusões)
    mid_h = (y0 + y_out_bot) / 2
    seta_h(COL_L_X + COL_L_W, COL_R_X, mid_h)

    # Colchete vertical ligando as 3 caixas de remoção
    c.setStrokeColor(_rgb(_COR_BORDA))
    c.setLineWidth(0.6)
    c.line(COL_R_X - 5, y0, COL_R_X - 5, y_out_bot)

    # Caixa screened — abaixo do mais baixo entre col_l e col_r
    y_scr_top = min(y_id_bot, y_out_bot) - GAP
    txt_scr = s("id_screened", lang, n=_n(dados.get("screened")))
    y_scr_bot = draw_box(txt_scr, COL_L_X, y_scr_top, COL_L_W, auto=True)

    # Seta vertical: buscados → screened
    seta_v(CX_L, y_id_bot, y_scr_top)

    y = y_scr_bot - GAP

    # =========================================================================
    # FASE 2 — TRIAGEM
    # =========================================================================
    y = draw_fase(s("fase_triagem", lang), y)

    # Linha 1: sought (esq) | excluded_screening (dir)
    val_excl_scr = dados.get("excluded_screening")
    val_sought   = dados.get("sought")

    txt_sought    = s("scr_sought",   lang, n=_n(val_sought))
    txt_excl_scr  = s("scr_excluded", lang, n=_n(val_excl_scr))

    y_t1 = y
    y_sought_bot   = draw_box(txt_sought,   COL_L_X, y_t1, COL_L_W,
                               auto=(val_sought is not None),
                               field_name="sought")
    y_excl_scr_bot = draw_box(txt_excl_scr, COL_R_X, y_t1, COL_R_W,
                               auto=(val_excl_scr is not None),
                               field_name="excluded_screening")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t1 + y_excl_scr_bot) / 2)
    seta_v(CX_L, y_scr_bot, y_t1)

    # Linha 2: assessed (esq) | not_retrieved (dir)
    val_nr       = dados.get("not_retrieved")
    val_assessed = dados.get("assessed")

    txt_nr       = s("scr_not_retrieved", lang, n=_n(val_nr))
    txt_assessed = s("scr_assessed",      lang, n=_n(val_assessed))

    y_t2 = min(y_sought_bot, y_excl_scr_bot) - GAP
    y_assessed_bot  = draw_box(txt_assessed, COL_L_X, y_t2, COL_L_W,
                                auto=(val_assessed is not None),
                                field_name="assessed")
    y_nr_bot        = draw_box(txt_nr, COL_R_X, y_t2, COL_R_W,
                                auto=(val_nr is not None),
                                field_name="not_retrieved")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t2 + y_nr_bot) / 2)
    seta_v(CX_L, y_sought_bot, y_t2)

    # Linha 3: excl_elig + razões (dir), abaixo de assessed
    val_excl_elig = dados.get("excluded_eligibility")
    reasons       = dados.get("excluded_reasons", [])
    reasons_txt   = "\n".join(reasons) if reasons else ""
    txt_excl_elig = s("scr_excl_reasons", lang,
                      n=_n(val_excl_elig), reasons=reasons_txt or "—")

    y_t3 = min(y_assessed_bot, y_nr_bot) - GAP
    y_excl_elig_bot = draw_box(txt_excl_elig, COL_R_X, y_t3, COL_R_W,
                                auto=(val_excl_elig is not None),
                                field_name="excluded_eligibility")
    seta_h(COL_L_X + COL_L_W, COL_R_X, (y_t3 + y_excl_elig_bot) / 2)
    seta_v(CX_L, y_assessed_bot, y_t3)

    y = min(y_t3, y_excl_elig_bot) - GAP

    # =========================================================================
    # FASE 3 — INCLUSÃO
    # =========================================================================
    y = draw_fase(s("fase_inclusao", lang), y)

    val_inc = dados.get("included_studies")
    val_rep = dados.get("included_reports")

    txt_inc = s("inc_studies",  lang, n=_n(val_inc))
    txt_rep = s("inc_reports",  lang, n=_n(val_rep))

    y_inc_bot = draw_box(txt_inc, COL_L_X, y, COL_L_W,
                         auto=(val_inc is not None),
                         field_name="included_studies")
    seta_v(CX_L, y_t3 if val_inc is None else y_t3, y)  # seta de assessed → included
    seta_v(CX_L, y_inc_bot, y_inc_bot - GAP)

    y_rep_top = y_inc_bot - GAP
    draw_box(txt_rep, COL_L_X, y_rep_top, COL_L_W,
             auto=(val_rep is not None),
             field_name="included_reports")

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

    parser.add_argument("input", metavar="JSON",
                        help="results_report.json gerado pelo results_report.py")
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
    parser.add_argument("--version", action="version",
                        version=f"prisma_workflow.py v{__version__}")

    args = parser.parse_args()

    # --- Validar input --------------------------------------------------------
    json_path = Path(args.input)
    if not json_path.exists():
        print(f"❌  Arquivo não encontrado: {json_path}", file=sys.stderr)
        sys.exit(1)

    # --- Carregar dados automáticos -------------------------------------------
    print(f"\nprisma_workflow.py v{__version__}")
    print(f"Input JSON       : {json_path.resolve()}")

    try:
        auto = carregar_dados_automaticos(json_path)
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

    print(f"\n  Gerando PDF...")
    gerar_pdf(dados, pdf_path, lang=args.lang)
    print(f"\nPronto. PDF em: {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
