"""
prisma_workflow.py — Gera formulário PDF preenchível PRISMA 2020.

Layout pixel-perfect baseado em assets/PRISMAdiagram.json, extraído do
documento oficial PRISMA_2020_flow_diagram_new_SRs_v1.docx.

Os campos numéricos são AcroForm editáveis. Os que o pipeline consegue
calcular automaticamente vêm pré-preenchidos; os que exigem curadoria
humana ficam em branco.

Referência: Page MJ et al. PRISMA 2020 Statement. BMJ 2021;372:n71.
            https://www.prisma-statement.org/prisma-2020-flow-diagram

Fases cobertas pelo pipeline SciELO Scraper:
  IDENTIFICATION (Identificação) — AUTOMÁTICO:
    • Records identified from databases   ← total_buscado
    • Registers                           ← 0 (SciELO não tem registers)
    • Duplicate records removed           ← 0 (SciELO não duplica)
    • Records marked ineligible by automation tools ← calculado
    • Records removed for other reasons   ← erros de extração
    • Records screened                    ← calculado automaticamente

  SCREENING (Triagem) — HUMANO (campos em branco no PDF):
    • Records excluded
    • Reports sought for retrieval
    • Reports not retrieved
    • Reports assessed for eligibility
    • Reports excluded + reasons

  INCLUDED (Inclusão) — HUMANO:
    • Studies included in review          ← criterio_ok como sugestão
    • Reports of included studies

Uso:
    uv run python prisma_workflow.py [results_report.json]
    uv run python prisma_workflow.py results_report.json -i
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
# Verificação de dependências
# ---------------------------------------------------------------------------

def _verificar_deps():
    ausentes = [pkg for mod, pkg in {"reportlab": "reportlab"}.items()
                if importlib.util.find_spec(mod) is None]
    if ausentes:
        print("❌  Dependências ausentes. Execute:")
        print(f"    uv pip install {' '.join(ausentes)}")
        sys.exit(1)

_verificar_deps()

__version__ = "2.0"

# ---------------------------------------------------------------------------
# Localização do JSON de layout
# ---------------------------------------------------------------------------

_ASSETS_DIR = Path(__file__).parent / "assets"
_DIAGRAM_JSON = _ASSETS_DIR / "PRISMAdiagram.json"


def _carregar_diagrama() -> dict:
    if not _DIAGRAM_JSON.exists():
        print(f"❌  Layout não encontrado: {_DIAGRAM_JSON}", file=sys.stderr)
        sys.exit(1)
    with open(_DIAGRAM_JSON, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Carregamento dos dados automáticos do results_report.json
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

    total_buscado   = totais.get("total_buscado", 0)
    total_scrapeado = totais.get("total_scrapeado", 0)

    erros_outros = 0
    for v in por_ano.values():
        erros = v.get("erros_extracao", {})
        for k, n in erros.items():
            erros_outros += int(n) if str(n).isdigit() else 0

    ok_completo_total = sum(v.get("ok_completo", 0) for v in por_ano.values())
    ok_parcial_total  = sum(v.get("ok_parcial", 0)  for v in por_ano.values())
    criterio_ok_total = totais.get("criterio_ok", 0)

    automation_removed = total_scrapeado - ok_completo_total - ok_parcial_total - erros_outros
    automation_removed = max(0, automation_removed)

    duplicates = 0
    screened   = total_buscado - duplicates - automation_removed - erros_outros
    screened   = max(0, screened)

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
        "total_buscado":       total_buscado,
        "duplicates":          duplicates,
        "automation_removed":  automation_removed,
        "erros_outros":        erros_outros,
        "screened":            screened,
        "criterio_ok":         criterio_ok_total,
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
    "duplicates",
    "excluded_screening",
    "sought",
    "not_retrieved",
    "assessed",
    "excluded_eligibility",
    "excluded_reasons",
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
            merged[campo] = file_map.get("excluded_reasons", [])
            continue
        cli_val  = _int_or_none(cli_map.get(campo))
        file_val = _int_or_none(file_map.get(campo))
        merged[campo] = cli_val if cli_val is not None else file_val

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
# Geração do PDF — pixel-perfect baseado em PRISMAdiagram.json
# ---------------------------------------------------------------------------

def _hex_to_rl(hex_color: str):
    """Converte #RRGGBB para Color do ReportLab."""
    from reportlab.lib.colors import Color
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return Color(r, g, b)


def _val_to_str(v) -> str:
    """Converte valor para string limpa para AcroForm."""
    if v is None:
        return ""
    return str(v)


def _sanitize(txt: str) -> str:
    """Remove caracteres fora do latin-1 para compatibilidade AcroForm."""
    return txt.encode("latin-1", errors="replace").decode("latin-1")


def _str_width(txt: str, font: str, size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(txt, font, size)


def _wrap(txt: str, max_w: float, font: str, size: float) -> list:
    """Quebra texto em lista de linhas que cabem em max_w."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = txt.split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if stringWidth(candidate, font, size) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [""]


def gerar_pdf(dados: dict, output_path: Path, lang: str = "pt"):
    """
    Gera PDF PRISMA 2020 pixel-perfect a partir de assets/PRISMAdiagram.json.

    Todos os campos n= são AcroForm editáveis. Os que têm valor vêm
    pré-preenchidos; os sem valor ficam em branco.
    """
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth

    diag = _carregar_diagrama()
    meta = diag["meta"]

    PW = meta["page_width_pt"]   # 595.3
    PH = meta["page_height_pt"]  # 841.9

    # JSON: y cresce ↓ (top-left); ReportLab: y cresce ↑ (bottom-left)
    def rl_y(json_y_top: float, h: float) -> float:
        return PH - json_y_top - h

    # =========================================================================
    # LAYOUT — ajuste aqui para micro-tuning visual
    # =========================================================================

    # -- Tipografia -----------------------------------------------------------
    FONT      = "Helvetica"       # fonte padrão
    FONT_B    = "Helvetica-Bold"  # fonte negrito (labels principais)
    FONT_MONO = "Courier"         # fonte do campo multilinha de exclusões
    FS        = 9.0               # pt — tamanho base do texto nas caixas
    FS_MONO   = 8.0               # pt — tamanho da fonte no campo de exclusões
    FS_FOOT   = 7.0               # pt — tamanho do texto dos rodapés
    LINE_H    = FS * 1.3          # pt — altura de linha

    # -- Campos AcroForm n= ---------------------------------------------------
    ACRO_W = 32.0                 # pt — largura do campo numérico editável
    ACRO_H = 11.0                 # pt — altura do campo numérico editável
    N_PFX  = "n = "              # texto estático prefixando o campo

    # -- Padding interno das caixas -------------------------------------------
    PAD_X = 4.0                   # pt — padding horizontal (esquerda e direita)
    PAD_Y = 4.0                   # pt — padding vertical (topo)

    # -- Cores ----------------------------------------------------------------
    COR_FASE          = "#9CC2E5" # faixas laterais de fase (azul claro)
    COR_FASE_STROKE   = "#000000" # borda das faixas de fase
    COR_HEADER_FILL   = "#FFC000" # fundo do cabeçalho (amarelo)
    COR_HEADER_STROKE = "#7F5F00" # borda do cabeçalho (dourado escuro)
    COR_BOX_FILL      = "#FFFFFF" # fundo das caixas de conteúdo
    COR_BOX_STROKE    = "#000000" # borda das caixas de conteúdo
    COR_TEXTO         = "#000000" # cor padrão do texto
    COR_SETA          = "#000000" # cor das setas conectoras

    # -- Estrutura horizontal -------------------------------------------------
    # O diagrama é centralizado automaticamente na página a partir destas
    # constantes. Alterar qualquer valor recalcula tudo em cascata.
    #
    #  |<-- MARGIN_LEFT -->|<- W_FASE ->|<- GAP_FASE_TO_COL ->|<- W_BOX ->|<- GAP_COLS ->|<- W_BOX ->|<-- MARGIN_RIGHT (=MARGIN_LEFT) -->|
    #
    W_FASE          = 20.7        # pt — espessura visual da faixa de fase
    GAP_FASE_TO_COL = 55.2        # pt — faixa de fase → coluna esquerda
    W_BOX           = 148.6       # pt — largura de todas as caixas
    GAP_COLS        = 46.7        # pt — gap entre colunas (onde ficam as setas)

    # Centralização horizontal: margem esquerda = margem direita
    _diag_w   = W_FASE + GAP_FASE_TO_COL + W_BOX + GAP_COLS + W_BOX
    MARGIN_LEFT = (PW - _diag_w) / 2

    # Posições X derivadas em cascata
    X_FASE    = MARGIN_LEFT                            # borda esquerda da faixa
    X_COL_L   = MARGIN_LEFT + W_FASE + GAP_FASE_TO_COL  # coluna esquerda
    X_COL_R   = X_COL_L + W_BOX + GAP_COLS             # coluna direita
    W_HEADER  = W_BOX + GAP_COLS + W_BOX               # largura do cabeçalho

    # -- Alturas das caixas ---------------------------------------------------
    H_HEADER  = 20.71             # pt — cabeçalho amarelo
    H_BOX_ID  = 97.9              # pt — identificação e removidos (par)
    H_BOX_SM  = 41.45             # pt — caixas pequenas de triagem (5 caixas)
    H_BOX_EXCL = 89.25            # pt — exclusões por elegibilidade
    H_BOX_INCL = 57.0             # pt — estudos incluídos

    # -- Gaps verticais -------------------------------------------------------
    # Todos os Y são calculados em cascata. Aumentar um gap empurra tudo abaixo.
    MARGIN_TOP               = 36.0  # pt — topo da página ao cabeçalho
    GAP_HEADER_TO_ID         = 8.0   # pt — cabeçalho → identificação
    GAP_ID_TO_SCREENING      = 14.0  # pt — identificação → triagem
    GAP_SCREENING_BOXES      = 14.0  # pt — entre caixas dentro da triagem
    GAP_SCREENING_TO_INCLUDED = 58.0 # pt — triagem → incluídos
    GAP_INCLUDED_TO_FOOTER   = 28.0  # pt — incluídos → rodapé

    # =========================================================================
    # POSIÇÕES X E Y CALCULADAS EM CASCATA
    # =========================================================================

    # Y em cascata
    y_header    = MARGIN_TOP
    y_id        = y_header   + H_HEADER  + GAP_HEADER_TO_ID
    y_screened  = y_id       + H_BOX_ID  + GAP_ID_TO_SCREENING
    y_sought    = y_screened + H_BOX_SM  + GAP_SCREENING_BOXES
    y_assessed  = y_sought   + H_BOX_SM  + GAP_SCREENING_BOXES
    y_included  = y_assessed + H_BOX_SM  + GAP_SCREENING_TO_INCLUDED

    # Coluna direita alinhada verticalmente com sua contraparte esquerda
    y_removed   = y_id
    y_excl_scr  = y_screened
    y_not_retr  = y_sought
    y_excl_elig = y_assessed

    # Dicionário completo de geometria por caixa (sobrescreve o JSON)
    _box_by_id = {b["id"]: b for b in diag["boxes"]}
    _geom_override = {
        "header":                       {"x_pt": X_COL_L,  "y_pt": y_header,   "w_pt": W_HEADER,  "h_pt": H_HEADER},
        "box_identified":               {"x_pt": X_COL_L,  "y_pt": y_id,        "w_pt": W_BOX,     "h_pt": H_BOX_ID},
        "box_removed_before_screening": {"x_pt": X_COL_R,  "y_pt": y_removed,   "w_pt": W_BOX,     "h_pt": H_BOX_ID},
        "box_screened":                 {"x_pt": X_COL_L,  "y_pt": y_screened,  "w_pt": W_BOX,     "h_pt": H_BOX_SM},
        "box_excluded_screening":       {"x_pt": X_COL_R,  "y_pt": y_excl_scr,  "w_pt": W_BOX,     "h_pt": H_BOX_SM},
        "box_sought":                   {"x_pt": X_COL_L,  "y_pt": y_sought,    "w_pt": W_BOX,     "h_pt": H_BOX_SM},
        "box_not_retrieved":            {"x_pt": X_COL_R,  "y_pt": y_not_retr,  "w_pt": W_BOX,     "h_pt": H_BOX_SM},
        "box_assessed":                 {"x_pt": X_COL_L,  "y_pt": y_assessed,  "w_pt": W_BOX,     "h_pt": H_BOX_SM},
        "box_excluded_eligibility":     {"x_pt": X_COL_R,  "y_pt": y_excl_elig, "w_pt": W_BOX,     "h_pt": H_BOX_EXCL},
        "box_included":                 {"x_pt": X_COL_L,  "y_pt": y_included,  "w_pt": W_BOX,     "h_pt": H_BOX_INCL},
    }

    # Aplicar overrides: mescla geometria calculada sobre atributos do JSON
    for bid, geom in _geom_override.items():
        if bid in _box_by_id:
            _box_by_id[bid] = {**_box_by_id[bid], **geom}

    def _h(box_id: str) -> float:
        return _box_by_id[box_id]["h_pt"]

    # =========================================================================

    # Mapeamento campo_id → valor numérico
    campo_map = {
        "n_databases":          dados.get("total_buscado"),
        "n_registers":          0,
        "n_duplicates":         dados.get("duplicates", 0),
        "n_automation":         dados.get("automation_removed"),
        "n_other_removed":      dados.get("erros_outros"),
        "n_screened":           dados.get("screened"),
        "n_excluded_screening": dados.get("excluded_screening"),
        "n_sought":             dados.get("sought"),
        "n_not_retrieved":      dados.get("not_retrieved"),
        "n_assessed":           dados.get("assessed"),
        "n_included_studies":   dados.get("criterio_ok"),
        "n_included_reports":   dados.get("included_reports"),
    }

    # Labels bilíngues
    LABELS_PT = {
        "header":                       "Identificação de estudos via bases de dados e registros",
        "box_identified":               "Registros identificados*:",
        "n_databases":                  "Bases de dados",
        "n_registers":                  "Registros",
        "box_removed_before_screening": "Registros removidos antes da triagem:",
        "n_duplicates":                 "Duplicatas",
        "n_automation":                 "Inelegíveis por automação",
        "n_other_removed":              "Outros motivos",
        "box_screened":                 "Registros triados",
        "n_screened":                   "",
        "box_excluded_screening":       "Registros excluídos**",
        "n_excluded_screening":         "",
        "box_sought":                   "Relatórios buscados para recuperação",
        "n_sought":                     "",
        "box_not_retrieved":            "Relatórios não recuperados",
        "n_not_retrieved":              "",
        "box_assessed":                 "Relatórios avaliados para elegibilidade",
        "n_assessed":                   "",
        "box_excluded_eligibility":     "Relatórios excluídos:",
        "n_excluded_reason1":           "Motivo 1",
        "n_excluded_reason2":           "Motivo 2",
        "n_excluded_reason3":           "Motivo 3",
        "n_excluded_etc":               "etc.",
        "box_included":                 "Estudos incluídos na revisão",
        "n_included_studies":           "",
        "n_included_reports":           "Relatórios dos estudos incluídos",
        "phase_identification":         "IDENTIFICAÇÃO",
        "phase_screening":              "TRIAGEM",
        "phase_included":               "INCLUÍDOS",
        "footnote_1_sym":               "*",
        "footnote_1_txt":               "Considere, se possível, reportar o número de registros identificados em cada base de dados ou registro pesquisado. Se outros métodos foram usados para identificar registros, como contato com autores ou revisão de listas de referências, inclua-os e rotule adequadamente.",
        "footnote_2_sym":               "**",
        "footnote_2_txt":               "Se ferramentas de automação foram usadas, indique quantos registros foram excluídos por um humano e quantos foram excluídos exclusivamente por ferramentas de automação.",
        "source_credit":                "Fonte: Page MJ et al. BMJ 2021;372:n71. doi: 10.1136/bmj.n71",
        "license":                      "Este trabalho está licenciado sob CC BY 4.0.",
    }
    LABELS_EN = {
        "header":                       "Identification of studies via databases and registers",
        "box_identified":               "Records identified from*:",
        "n_databases":                  "Databases",
        "n_registers":                  "Registers",
        "box_removed_before_screening": "Records removed before screening:",
        "n_duplicates":                 "Duplicates",
        "n_automation":                 "Ineligible by automation",
        "n_other_removed":              "Other reasons",
        "box_screened":                 "Records screened",
        "n_screened":                   "",
        "box_excluded_screening":       "Records excluded**",
        "n_excluded_screening":         "",
        "box_sought":                   "Reports sought for retrieval",
        "n_sought":                     "",
        "box_not_retrieved":            "Reports not retrieved",
        "n_not_retrieved":              "",
        "box_assessed":                 "Reports assessed for eligibility",
        "n_assessed":                   "",
        "box_excluded_eligibility":     "Reports excluded:",
        "n_excluded_reason1":           "Reason 1",
        "n_excluded_reason2":           "Reason 2",
        "n_excluded_reason3":           "Reason 3",
        "n_excluded_etc":               "etc.",
        "box_included":                 "Studies included in review",
        "n_included_studies":           "",
        "n_included_reports":           "Reports of included studies",
        "phase_identification":         "IDENTIFICATION",
        "phase_screening":              "SCREENING",
        "phase_included":               "INCLUDED",
        "footnote_1_sym":               "*",
        "footnote_1_txt":               "Consider, if feasible to do so, reporting the number of records identified from each database or register searched. If other methods were used to identify records, such as contacting authors or reviewing reference lists, include these and label appropriately.",
        "footnote_2_sym":               "**",
        "footnote_2_txt":               "If automation tools were used, indicate how many records were excluded by a human and how many were excluded solely based on automation tools.",
        "source_credit":                "Source: Page MJ, et al. BMJ 2021;372:n71. doi: 10.1136/bmj.n71",
        "license":                      "This work is licensed under CC BY 4.0.",
    }
    LBL = LABELS_PT if lang == "pt" else LABELS_EN

    c = rl_canvas.Canvas(str(output_path), pagesize=(PW, PH))

    # ---- helpers ----------------------------------------------------------------

    def set_fill(hex_color):
        c.setFillColor(_hex_to_rl(hex_color))

    def set_stroke(hex_color):
        c.setStrokeColor(_hex_to_rl(hex_color))

    def draw_rounded_rect(x, y_top, w, h, fill_hex, stroke_hex, lw=0.5, r=3.0):
        set_fill(fill_hex); set_stroke(stroke_hex); c.setLineWidth(lw)
        c.roundRect(x, rl_y(y_top, h), w, h, radius=r, fill=1, stroke=1)

    def draw_rect(x, y_top, w, h, fill_hex, stroke_hex, lw=0.5):
        set_fill(fill_hex); set_stroke(stroke_hex); c.setLineWidth(lw)
        c.rect(x, rl_y(y_top, h), w, h, fill=1, stroke=1)

    def draw_text(txt, x, y_json, font=FONT, size=FS, hex_color="#000000", align="left"):
        set_fill(hex_color); c.setFont(font, size)
        rl_yy = PH - y_json
        if align == "center":
            c.drawCentredString(x, rl_yy, txt)
        elif align == "right":
            c.drawRightString(x, rl_yy, txt)
        else:
            c.drawString(x, rl_yy, txt)

    def acro_field(field_name, value, x_json, y_top_json, w=ACRO_W, h=ACRO_H):
        """Campo AcroForm. x/y_top em coordenadas JSON."""
        val_str = _sanitize(_val_to_str(value))
        c.acroForm.textfield(
            name=_sanitize(field_name),
            tooltip=_sanitize(field_name),
            x=x_json, y=rl_y(y_top_json, h),
            width=w, height=h,
            fontSize=FS,
            borderColor=_hex_to_rl("#000000"),
            fillColor=_hex_to_rl("#FFFFFF"),
            textColor=_hex_to_rl("#000000"),
            value=val_str,
            forceBorder=True, borderWidth=0.5,
        )

    def draw_n_field(fid, value, bx, bw, y_baseline_json):
        """
        Desenha 'n = ' estático + campo AcroForm alinhados à direita da caixa.
        y_baseline_json: posição JSON da linha de base do texto.
        """
        pfx_w   = stringWidth(N_PFX, FONT, FS)
        field_x = bx + bw - PAD_X - ACRO_W
        pfx_x   = field_x - pfx_w - 1
        # campo: topo = baseline - ascender (~FS*0.75)
        field_y_top = y_baseline_json - FS * 0.80
        draw_text(N_PFX, pfx_x, y_baseline_json, font=FONT, size=FS)
        acro_field(fid, value, field_x, field_y_top)

    def arrow_h(x_from, x_to, y_json):
        rl_yy = PH - y_json
        set_stroke(COR_SETA); set_fill(COR_SETA); c.setLineWidth(0.5)
        c.line(x_from, rl_yy, x_to - 5, rl_yy)
        p = c.beginPath()
        p.moveTo(x_to, rl_yy); p.lineTo(x_to - 5, rl_yy + 3); p.lineTo(x_to - 5, rl_yy - 3)
        p.close(); c.drawPath(p, fill=1, stroke=0)

    def arrow_v(x_json, y_from_json, y_to_json):
        rl_yf = PH - y_from_json; rl_yt = PH - y_to_json
        set_stroke(COR_SETA); set_fill(COR_SETA); c.setLineWidth(0.5)
        c.line(x_json, rl_yf, x_json, rl_yt + 5)
        p = c.beginPath()
        p.moveTo(x_json, rl_yt); p.lineTo(x_json - 3, rl_yt + 5); p.lineTo(x_json + 3, rl_yt + 5)
        p.close(); c.drawPath(p, fill=1, stroke=0)

    # Mapa fase_id → lista de box ids para cálculo dinâmico de comprimento e centro Y
    _PHASE_BOXES = {
        "phase_identification": ["box_identified", "box_removed_before_screening"],
        "phase_screening":      ["box_screened", "box_excluded_screening",
                                 "box_sought", "box_not_retrieved",
                                 "box_assessed", "box_excluded_eligibility"],
        "phase_included":       ["box_included"],
    }
    # _box_by_id já foi construído e populado com geometria calculada no bloco LAYOUT

    def _phase_y_center(phase_id: str) -> float:
        """Calcula o centro Y visual (coords calculados) das caixas de uma fase."""
        box_ids = _PHASE_BOXES.get(phase_id, [])
        if not box_ids:
            return 0.0
        tops    = [_box_by_id[bid]["y_pt"] for bid in box_ids if bid in _box_by_id]
        bottoms = [_box_by_id[bid]["y_pt"] + _box_by_id[bid]["h_pt"]
                   for bid in box_ids if bid in _box_by_id]
        return (min(tops) + max(bottoms)) / 2.0

    def _phase_w(phase_id: str) -> float:
        """Calcula o comprimento visual da faixa (= span Y das caixas da fase)."""
        box_ids = _PHASE_BOXES.get(phase_id, [])
        if not box_ids:
            return 0.0
        tops    = [_box_by_id[bid]["y_pt"] for bid in box_ids if bid in _box_by_id]
        bottoms = [_box_by_id[bid]["y_pt"] + _box_by_id[bid]["h_pt"]
                   for bid in box_ids if bid in _box_by_id]
        return max(bottoms) - min(tops)

    def phase_band(phase: dict, label: str):
        """Faixa lateral rotacionada -90°, centralizada e dimensionada sobre as caixas da fase."""
        h  = W_FASE                      # espessura visual da faixa (constante)
        w  = _phase_w(phase["id"])       # comprimento calculado a partir das caixas

        # Centro X da faixa: borda esquerda + metade da espessura
        cx_rl = X_FASE + W_FASE / 2

        # Centro Y calculado dinamicamente para alinhar ao bloco de caixas
        cy_json = _phase_y_center(phase["id"])
        cy_rl   = PH - cy_json

        c.saveState()
        c.translate(cx_rl, cy_rl)
        c.rotate(90)
        set_fill(COR_FASE); set_stroke(COR_FASE_STROKE)
        c.setLineWidth(phase["stroke_w_pt"])
        c.roundRect(-w/2, -h/2, w, h, radius=3.0, fill=1, stroke=1)
        c.setFont(FONT_B, FS); c.setFillColor(_hex_to_rl(COR_TEXTO))
        c.drawCentredString(0, -FS * 0.35, label)
        c.restoreState()

    # =====================================================================
    # DESENHANDO O DIAGRAMA
    # =====================================================================

    # Faixas de fase
    for ph in diag["phases"]:
        phase_band(ph, LBL.get(ph["id"], ph["label"]))

    # Caixas (usa _box_by_id que já tem geometria calculada)
    for box in [_box_by_id[b["id"]] for b in diag["boxes"]]:
        bx  = box["x_pt"]; by = box["y_pt"]
        bw  = box["w_pt"]; bh = box["h_pt"]
        bid = box["id"]

        if box["geometry"] == "flowChartAlternateProcess":
            fill   = COR_HEADER_FILL   if bid == "header" else COR_BOX_FILL
            stroke = COR_HEADER_STROKE if bid == "header" else COR_BOX_STROKE
            draw_rounded_rect(bx, by, bw, bh, fill, stroke, box["stroke_w_pt"], r=4.0)
        else:
            draw_rect(bx, by, bw, bh, COR_BOX_FILL, COR_BOX_STROKE, box["stroke_w_pt"])

        # Cursor de texto interno
        text_x  = bx + PAD_X
        text_y  = by + PAD_Y + FS   # baseline da 1ª linha em coords JSON

        # Label principal da caixa
        label_txt = LBL.get(bid, box["label"])
        font_main = FONT_B if box.get("label_bold") else FONT

        if box["text_align"] == "center":
            cx_box = bx + bw / 2
            for ln in _wrap(label_txt, bw - PAD_X * 2, font_main, FS):
                draw_text(ln, cx_box, text_y, font=font_main, size=FS, align="center")
                text_y += LINE_H
        else:
            for ln in _wrap(label_txt, bw - PAD_X * 2, font_main, FS):
                draw_text(ln, text_x, text_y, font=font_main, size=FS)
                text_y += LINE_H

        # Sub-itens n= (cada um em sua própria linha(s) + campo)
        n_fields = box.get("n_fields", [])
        pfx_w   = stringWidth(N_PFX, FONT, FS)
        n_block = pfx_w + ACRO_W + PAD_X + 2   # espaço reservado para "n = [campo]"

        # ---- Tratamento especial: box de exclusões por elegibilidade --------
        # Substituir N campos individuais por 1 textarea multilinha Courier,
        # com formato col-25: "Motivo X" + espaços até col 25 + "n = ?"
        if bid == "box_excluded_eligibility":
            COL = 25              # coluna onde "n = " começa (em chars Courier)

            # Nomes de motivo por idioma
            motivo_lbl = "Motivo" if lang == "pt" else "Reason"

            # Pré-preencher com razões fornecidas pelo pesquisador
            reasons = dados.get("excluded_reasons") or []
            lines_content = []
            for i in range(1, 4):
                if i - 1 < len(reasons):
                    r = str(reasons[i - 1])
                    # Separar "Texto: N" ou usar texto bruto como motivo
                    parts = r.rsplit(":", 1)
                    motivo_txt = parts[0].strip()
                    qty        = parts[1].strip() if len(parts) == 2 else "?"
                else:
                    motivo_txt = f"{motivo_lbl} {i}"
                    qty        = "?"
                # Truncar motivo_txt para caber antes da coluna
                motivo_txt = motivo_txt[:COL - 5] if len(motivo_txt) > COL - 5 else motivo_txt
                padding    = " " * (COL - len(motivo_txt))
                lines_content.append(f"{motivo_txt}{padding}n = {qty}")
            lines_content.append("etc.")

            field_value = "\n".join(lines_content)

            # Área disponível abaixo do label da caixa
            field_top_json = text_y - FS         # topo do campo em coords JSON
            field_h        = by + bh - field_top_json - PAD_Y
            field_w        = bw - PAD_X * 2

            val_str = _sanitize(field_value)
            c.acroForm.textfield(
                name="excluded_eligibility_reasons",
                tooltip=_sanitize("Motivos de exclusão por elegibilidade"),
                x=text_x,
                y=rl_y(field_top_json, field_h),
                width=field_w,
                height=field_h,
                fontSize=FS_MONO,
                fontName=FONT_MONO,
                borderColor=_hex_to_rl("#000000"),
                fillColor=_hex_to_rl("#FFFFFF"),
                textColor=_hex_to_rl("#000000"),
                value=val_str,
                forceBorder=True,
                borderWidth=0.5,
                fieldFlags="multiline",
            )
            continue   # pula o loop genérico de n_fields para este box
        # ---------------------------------------------------------------------

        for nf in n_fields:
            fid   = nf["id"]
            value = campo_map.get(fid)

            # Label do sub-item
            sub_lbl = LBL.get(fid, nf.get("label", "")).strip()

            if sub_lbl:
                # Linhas do label: todas cabem em largura total da caixa,
                # mas a última linha precisa deixar espaço para "n = [campo]"
                full_lines = _wrap(sub_lbl, bw - PAD_X * 2, FONT, FS)
                last_ln    = full_lines[-1]
                # Verificar se a última linha cabe junto com o n_block
                last_w = stringWidth(last_ln, FONT, FS)
                if last_w + n_block > bw - PAD_X * 2:
                    # Não cabe: quebrar novamente com largura reduzida
                    short_lines = _wrap(sub_lbl, bw - PAD_X * 2 - n_block, FONT, FS)
                    for ln in short_lines[:-1]:
                        draw_text(ln, text_x, text_y, font=FONT, size=FS)
                        text_y += LINE_H
                    last_ln = short_lines[-1]
                else:
                    for ln in full_lines[:-1]:
                        draw_text(ln, text_x, text_y, font=FONT, size=FS)
                        text_y += LINE_H
                draw_text(last_ln, text_x, text_y, font=FONT, size=FS)

            # "n = " + campo alinhados à direita, na linha corrente
            draw_n_field(fid, value, bx, bw, text_y)
            text_y += LINE_H + 1

    # Conectores — posições recalculadas a partir das bordas reais das caixas
    for conn in diag["connectors"]:
        fb = _box_by_id.get(conn["from_box"])
        tb = _box_by_id.get(conn["to_box"])
        if conn["direction"] == "horizontal":
            # seta sai da borda direita de from_box → borda esquerda de to_box
            x_start = fb["x_pt"] + fb["w_pt"] if fb else conn["x_start_pt"]
            x_end   = tb["x_pt"]               if tb else conn["x_end_pt"]
            # y = centro vertical de from_box (e to_box estão alinhadas horizontalmente)
            y_mid   = fb["y_pt"] + fb["h_pt"] / 2 if fb else conn["y_pt"]
            arrow_h(x_start, x_end, y_mid)
        else:
            # seta sai da borda inferior de from_box → borda superior de to_box
            y_start = fb["y_pt"] + fb["h_pt"] if fb else conn["y_start_pt"]
            y_end   = tb["y_pt"]               if tb else conn["y_end_pt"]
            # x = centro horizontal de from_box
            x_mid   = fb["x_pt"] + fb["w_pt"] / 2 if fb else conn["x_pt"]
            arrow_v(x_mid, y_start, y_end)

    # Rodapés — posicionados logo abaixo da última caixa
    last_box_bottom = (_box_by_id["box_included"]["y_pt"]
                       + _box_by_id["box_included"]["h_pt"])
    foot_y   = last_box_bottom + GAP_INCLUDED_TO_FOOTER
    foot_x   = X_FASE
    foot_w   = _diag_w

    footnote_data = [
        (LBL["footnote_1_sym"], LBL["footnote_1_txt"]),
        (LBL["footnote_2_sym"], LBL["footnote_2_txt"]),
        ("",                    LBL["source_credit"]),
        ("",                    LBL["license"]),
    ]
    for sym, txt in footnote_data:
        full = (sym + " " + txt).strip() if sym else txt
        for ln in _wrap(full, foot_w, FONT, FS_FOOT):
            draw_text(ln, foot_x, foot_y, font=FONT, size=FS_FOOT)
            foot_y += FS_FOOT * 1.35
        foot_y += 2.0

    c.save()


# ---------------------------------------------------------------------------
# Descoberta automática do results_report.json
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

    local = Path("results_report.json")
    if local.exists():
        _add([local])

    _add(Path(".").glob("runs/*/results_*/results_report.json"))
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

    print("\nresults_report.json encontrados:\n")
    for i, cp in enumerate(candidatos[:10], 1):
        print(f"  {i}. {cp}")
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
            "Layout pixel-perfect baseado no template oficial PRISMA 2020. "
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
    parser.add_argument("--included", metavar="N", type=int, default=None,
                        help="Estudos incluídos na revisão.")
    parser.add_argument("--included-reports", metavar="N", type=int, default=None,
                        help="Relatórios dos estudos incluídos.")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Modo interativo: pergunta os dados humanos ausentes no terminal.")
    parser.add_argument("--output-dir", metavar="DIR", default=None,
                        help="Pasta de saída (default: mesmo diretório do JSON de entrada).")
    parser.add_argument("--lang", choices=["pt", "en"], default="pt",
                        help="Idioma do PDF: pt (default) | en.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra os dados que seriam usados sem gerar o PDF.")
    parser.add_argument("--version", action="version",
                        version=f"prisma_workflow.py v{__version__}")

    args = parser.parse_args()

    json_path = _descobrir_json(args.input, args.interactive)

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

    human_file: dict = {}
    if args.human_data:
        human_file = carregar_human_data(Path(args.human_data))

    dados = merge_human(auto, human_file, args)

    if args.interactive:
        dados = modo_interativo(dados, args.lang)

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

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = json_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    stem = json_path.stem
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = output_dir / f"prisma_{stem}_{args.lang}_{ts}.pdf"

    print(f"\n  Gerando PDF...")
    gerar_pdf(dados, pdf_path, lang=args.lang)
    print(f"\nPronto. PDF em: {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
