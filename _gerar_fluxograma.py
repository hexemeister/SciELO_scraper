"""
Gera flowchart_extracao_ptbr.svg
Estratégia híbrida:
  1. dot -Tplain para obter posições X,Y relativas dos nós e roteamento das setas
  2. Redesenho completo no estilo manual (header #222222, containers, etc.)
  3. Alturas calculadas pelo conteúdo real, não pelo Graphviz
"""
import subprocess, re, os

os.environ["PATH"] += r";C:\Program Files\Graphviz\bin"
DOT = r"C:\Program Files\Graphviz\bin\dot.exe"

# ─── Definição de conteúdo de cada nó ────────────────────────────────────────
# tipo: terminal | proc | fase | diamond | err | ok | resultado
NODE_DEF = {
    "start":     {"tipo": "terminal",
                  "header": "process_article(row)"},
    "clean":     {"tipo": "proc",
                  "header": "clean_pid(raw_id)",
                  "body": ["Strip · remove sufixo -scl / -oai",
                           r"Valida regex: [A-Z]\d{4}-\d{3}[\dA-Z]\d{13} (23 car.)"]},
    "pid_ok":    {"tipo": "diamond", "label": ["PID válido?"]},
    "err_pid":   {"tipo": "err",
                  "lines": ["erro_pid_invalido", "(encerra)"]},
    "fase1":     {"tipo": "fase", "fill": "#f5f5f5",
                  "header": "Fase 1 — ArticleMeta API",
                  "sub":    "saltada com --only-html",
                  "body":   ["GET api/v1/article?code={pid}&amp;collection={col}&amp;format=json",
                             'extract_pt_from_isis() · filtra lang=="pt"']},
    "api_ok":    {"tipo": "diamond", "label": ["Dados PT", "na API?"]},
    "ok_api":    {"tipo": "ok",
                  "lines": ["ok_completo", "(via API — encerra)"]},
    "fase2":     {"tipo": "fase", "fill": "#e8e8e8",
                  "header": "Fase 2 — Fallback HTML",
                  "sub":    "saltada com --only-api  OU  todos os campos já preenchidos",
                  "body":   ["Etapa 1: GET scielo.br?script=sci_arttext&amp;pid={pid}&amp;lang=pt",
                             "segue redirect automático · campos em falta: need_t · need_r · need_k"]},
    "err_http":  {"tipo": "diamond", "label": ["Erro HTTP?"]},
    "err_ext":   {"tipo": "err",
                  "lines": ["erro_extracao", "(return None)"]},
    "is_art":    {"tipo": "diamond",
                  "label": ["is_article_page(soup)?",
                             "citation_title · og:title+Resumo · articleText · data-anchor"]},
    "apply":     {"tipo": "proc",
                  "header": "apply_missing(meta, body)",
                  "body":   ["Para cada campo em falta (T · R · KW):",
                             "1.ª: meta tags (citation_title · citation_abstract · citation_keywords)",
                             "2.ª: corpo HTML (h1.article-title · div[data-anchor=Resumo] · .keywords)"]},
    "is_aop":    {"tipo": "diamond",
                  "label": ['is_aop(pid)? — pid[14:17]=="005"']},
    "etapa4":    {"tipo": "proc",
                  "header": "Etapa 4 — AoP",
                  "body":   ["Extrair og:url da página home · forçar lang=pt",
                             "GET og:url → is_article_page? → apply_missing()"]},
    "lang_pt":   {"tipo": "diamond",
                  "label": ["Língua ≠ PT", "e faltam campos?"]},
    "etapa3":    {"tipo": "proc",
                  "header": "Etapa 3 — Link PT",
                  "body":   ["_find_pt_link(soup) · procura href com ?lang=pt",
                             "GET link PT → apply_missing()"]},
    "resultado": {"tipo": "resultado",
                  "lines": ["T ∧ R ∧ KW  →  ok_completo",
                            "T ∨ R ∨ KW  →  ok_parcial",
                            "URL tentada, sem dados  →  nada_encontrado",
                            "Falha de rede / HTTP  →  erro_extracao"]},
}

EDGE_LABELS = {
    ("pid_ok","err_pid"): "Não", ("pid_ok","fase1"): "Sim",
    ("api_ok","ok_api"):  "Completo", ("api_ok","fase2"): "Parcial/Não",
    ("err_http","err_ext"): "Sim", ("err_http","is_art"): "Não",
    ("is_art","apply"):   "Sim", ("is_art","is_aop"): "Não",
    ("is_aop","etapa4"):  "Sim", ("is_aop","lang_pt"): "Não",
    ("lang_pt","etapa3"): "Sim", ("lang_pt","resultado"): "Não",
}

# ─── Alturas fixas por tipo (px) ──────────────────────────────────────────────
HDR_H   = 24    # altura do cabeçalho escuro
LINE_H  = 14    # altura por linha de body
PAD_V   = 10    # padding vertical total (topo + base do body)
DIA_H   = 52    # altura base do losango
DIA_LH  = 14    # altura extra por linha adicional no losango
TERM_H  = 28
ERR_H   = 40
FASE_HDR = 28   # título + subtítulo
FASE_LH  = 13
FASE_PAD = 12

def node_height(nid):
    nd = NODE_DEF[nid]
    t = nd["tipo"]
    if t == "terminal":  return TERM_H
    if t == "diamond":   return DIA_H + (len(nd["label"]) - 1) * DIA_LH
    if t in ("err","ok"): return ERR_H
    if t == "proc":      return HDR_H + PAD_V + len(nd["body"]) * LINE_H
    if t == "fase":      return FASE_HDR + FASE_PAD + len(nd["body"]) * FASE_LH
    if t == "resultado": return 28 + PAD_V + len(nd["lines"]) * LINE_H
    return 40

def node_width(nid):
    nd = NODE_DEF[nid]
    t = nd["tipo"]
    # largura fixa por tipo
    if t == "terminal":   return 240
    if t == "diamond":    return max(200, max(len(l) for l in nd["label"]) * 7 + 20)
    if t in ("err","ok"): return 180
    if t == "proc":
        maxlen = max(len(nd["header"]), max(len(l) for l in nd["body"]))
        return min(500, max(280, maxlen * 6 + 30))
    if t == "fase":
        maxlen = max(len(nd["header"]), len(nd["sub"]), max(len(l) for l in nd["body"]))
        return min(560, max(320, maxlen * 6 + 30))
    if t == "resultado":
        return max(320, max(len(l) for l in nd["lines"]) * 7 + 40)
    return 200

# ─── Layout via dot -Tplain ───────────────────────────────────────────────────
# Usa tamanhos em polegadas baseados nas alturas/larguras reais
def px2in(px): return px / 96.0

dot_nodes = ""
for nid in NODE_DEF:
    w = px2in(node_width(nid))
    h = px2in(node_height(nid))
    dot_nodes += f'  {nid} [width={w:.3f}, height={h:.3f}, fixedsize=true];\n'

DOT_SRC = f"""
digraph {{
  rankdir=TB; nodesep=0.4; ranksep=0.55;
  node [shape=box];
{dot_nodes}
  {{ rank=same; pid_ok; err_pid }}
  {{ rank=same; api_ok; ok_api }}
  {{ rank=same; err_http; err_ext }}
  {{ rank=same; is_aop; etapa4 }}
  {{ rank=same; lang_pt; etapa3 }}
  start->clean; clean->pid_ok;
  pid_ok->err_pid; pid_ok->fase1;
  fase1->api_ok;
  api_ok->ok_api; api_ok->fase2;
  fase2->err_http;
  err_http->err_ext; err_http->is_art;
  is_art->apply; is_art->is_aop;
  is_aop->etapa4; is_aop->lang_pt;
  etapa4->lang_pt; apply->lang_pt;
  lang_pt->etapa3; lang_pt->resultado;
  etapa3->resultado;
}}
"""

plain = subprocess.run([DOT, "-Tplain"], input=DOT_SRC.encode(),
                       capture_output=True).stdout.decode()

graph_line = re.search(r"^graph ([\d.]+) ([\d.]+) ([\d.]+)", plain, re.M)
GW_IN = float(graph_line.group(2))
GH_IN = float(graph_line.group(3))

nodes_pos = {}
for m in re.finditer(r"^node (\w+) ([\d.]+) ([\d.]+)", plain, re.M):
    nodes_pos[m.group(1)] = (float(m.group(2)), float(m.group(3)))

edges_pts = []
for m in re.finditer(r"^edge (\w+) (\w+) \d+ ([\d. \n-]+?)(?= \w+ \w)", plain, re.M):
    raw = m.group(3).strip().split()
    pts = [(float(raw[i]), float(raw[i+1])) for i in range(0, len(raw)-1, 2)]
    edges_pts.append((m.group(1), m.group(2), pts))

# ─── Escala para A4 ───────────────────────────────────────────────────────────
SVG_W, SVG_H = 794, 1123
MARGIN_L, MARGIN_T = 30, 60   # espaço para título
MARGIN_B = 80                  # espaço para rodapé
AVAIL_W = SVG_W - MARGIN_L * 2
AVAIL_H = SVG_H - MARGIN_T - MARGIN_B

SX = AVAIL_W / GW_IN
SY = AVAIL_H / GH_IN

def to_px(gx, gy):
    return (MARGIN_L + gx * SX,
            MARGIN_T + (GH_IN - gy) * SY)

# ─── SVG builders ─────────────────────────────────────────────────────────────
out_lines = []
A = out_lines.append

def esc(s):
    """Escapa & soltos (não entidades) para XML."""
    return re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', s)

def svgtxt(x, y, s, anchor="middle", size="10px", weight="normal",
           fill="#111111", style=""):
    st = f' font-style="{style}"' if style else ""
    A(f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial,Helvetica,sans-serif"'
      f' font-size="{size}" font-weight="{weight}" fill="{fill}"'
      f' text-anchor="{anchor}"{st}>{esc(s)}</text>')

def draw_node(nid):
    if nid not in nodes_pos:
        return
    gx, gy = nodes_pos[nid]
    cx, cy = to_px(gx, gy)
    nd  = NODE_DEF[nid]
    t   = nd["tipo"]
    nw  = node_width(nid)
    nh  = node_height(nid)
    x0  = cx - nw / 2
    y0  = cy - nh / 2

    if t == "terminal":
        r = nh / 2
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="{r:.1f}" fill="#111111" stroke="#111111" stroke-width="1.5"/>')
        svgtxt(cx, cy + 5, nd["header"], size="11px", weight="bold", fill="white")

    elif t == "proc":
        # caixa externa
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="6" fill="white" stroke="#222222" stroke-width="1.2"/>')
        # cabeçalho escuro
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{HDR_H}"'
          f' rx="6" fill="#222222" stroke="none"/>')
        A(f'<rect x="{x0:.1f}" y="{y0+HDR_H-6:.1f}" width="{nw:.1f}" height="8"'
          f' fill="#222222" stroke="none"/>')
        svgtxt(cx, y0 + 16, nd["header"], size="11px", weight="bold", fill="white")
        # body
        n = len(nd["body"])
        body_h = nh - HDR_H - PAD_V
        for i, line in enumerate(nd["body"]):
            ty = y0 + HDR_H + PAD_V/2 + (i + 0.5) * (body_h / n)
            svgtxt(cx, ty + 4, line, size="9.5px", fill="#555555")

    elif t == "fase":
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="10" fill="{nd["fill"]}" stroke="#222222" stroke-width="1.5"/>')
        svgtxt(cx, y0 + 16, nd["header"], size="12px", weight="bold")
        svgtxt(cx, y0 + 29, nd["sub"], size="9.5px", fill="#555555", style="italic")
        n = len(nd["body"])
        body_h = nh - FASE_HDR - FASE_PAD
        for i, line in enumerate(nd["body"]):
            ty = y0 + FASE_HDR + FASE_PAD/2 + (i + 0.5) * (body_h / n)
            svgtxt(cx, ty + 2, line, size="9.5px", fill="#444444")

    elif t == "diamond":
        hw, hh = nw / 2, nh / 2
        A(f'<polygon points="{cx:.1f},{y0:.1f} {cx+hw:.1f},{cy:.1f}'
          f' {cx:.1f},{y0+nh:.1f} {cx-hw:.1f},{cy:.1f}"'
          f' fill="white" stroke="#222222" stroke-width="1.3"/>')
        lns = nd["label"]
        for i, ln in enumerate(lns):
            offset = (i - (len(lns)-1)/2) * 14
            svgtxt(cx, cy + offset + 4, ln, size="10.5px", weight="bold")

    elif t == "err":
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="5" fill="white" stroke="#222222" stroke-width="1"/>')
        lns = nd["lines"]
        for i, ln in enumerate(lns):
            offset = (i - (len(lns)-1)/2) * 14
            svgtxt(cx, cy + offset + 4, ln, size="9.5px")

    elif t == "ok":
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="5" fill="#111111" stroke="#111111" stroke-width="1"/>')
        lns = nd["lines"]
        for i, ln in enumerate(lns):
            offset = (i - (len(lns)-1)/2) * 14
            col = "white" if i == 0 else "#cccccc"
            fw  = "bold"  if i == 0 else "normal"
            svgtxt(cx, cy + offset + 4, ln, size="9.5px", fill=col, weight=fw)

    elif t == "resultado":
        A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{nw:.1f}" height="{nh:.1f}"'
          f' rx="10" fill="#d0d0d0" stroke="#222222" stroke-width="1.5"/>')
        svgtxt(cx, y0 + 17, "Resultado Final", size="12px", weight="bold")
        A(f'<line x1="{x0+12:.1f}" y1="{y0+24:.1f}"'
          f' x2="{x0+nw-12:.1f}" y2="{y0+24:.1f}"'
          f' stroke="#aaaaaa" stroke-width="0.8"/>')
        n = len(nd["lines"])
        body_h = nh - 30
        for i, ln in enumerate(nd["lines"]):
            ty = y0 + 30 + (i + 0.5) * (body_h / n)
            svgtxt(cx, ty + 2, ln, size="10px")

# ─── Constrói SVG ─────────────────────────────────────────────────────────────
A('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
A('<svg width="794" height="1123" viewBox="0 0 794 1123"'
  ' xmlns="http://www.w3.org/2000/svg">')
A('<defs><marker id="arr" markerWidth="8" markerHeight="6"'
  ' refX="7" refY="3" orient="auto">'
  '<polygon points="0 0,8 3,0 6" fill="#222222"/></marker></defs>')
A('<rect width="794" height="1123" fill="#ffffff"/>')

# Título
svgtxt(397, 36, "Algoritmo de Extração — SciELO Scraper",
       size="14px", weight="bold", fill="#111111")
svgtxt(397, 52, "Lógica de decisão: ArticleMeta API e fallback por raspagem HTML",
       size="10.5px", fill="#555555")

# Legenda
A('<rect x="10" y="8" width="196" height="108" rx="6"'
  ' fill="#f5f5f5" stroke="#222222" stroke-width="1"/>')
svgtxt(108, 25, "Legenda", size="10px", weight="bold")
A('<line x1="16" y1="30" x2="200" y2="30" stroke="#cccccc" stroke-width="0.8"/>')
A('<rect x="18" y="37" width="44" height="16" rx="3"'
  ' fill="white" stroke="#222222" stroke-width="1"/>')
svgtxt(70, 49, "Processo / Ação", size="9px", fill="#444444", anchor="start")
A('<polygon points="40,71 58,62 76,71 58,80"'
  ' fill="white" stroke="#222222" stroke-width="1"/>')
svgtxt(84, 75, "Decisão", size="9px", fill="#444444", anchor="start")
A('<rect x="18" y="88" width="44" height="16" rx="8"'
  ' fill="#111111" stroke="#111111" stroke-width="1"/>')
svgtxt(70, 100, "Início / Resultado", size="9px", fill="#444444", anchor="start")

# Nós
for nid in NODE_DEF:
    draw_node(nid)

# Setas
for src, dst, pts in edges_pts:
    px_pts = [to_px(gx, gy) for gx, gy in pts]
    if len(px_pts) >= 2:
        pt_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in px_pts)
        A(f'<polyline points="{pt_str}" fill="none" stroke="#222222"'
          f' stroke-width="1.4" marker-end="url(#arr)"/>')
    lbl = EDGE_LABELS.get((src, dst))
    if lbl and len(px_pts) >= 2:
        # Ponto médio da seta
        mid = px_pts[len(px_pts) // 2]
        svgtxt(mid[0] + 5, mid[1] - 4, lbl,
               size="9px", fill="#444444", anchor="start", style="italic")

# Rodapé
svgtxt(397, 1064,
       'T = Título · R = Resumo · KW = Palavras-chave · AoP = Ahead of Print (pid[14:17]=="005")',
       size="8.5px", fill="#888888")
svgtxt(397, 1078,
       "Figura 1 — Algoritmo de extração SciELO Scraper v2.4."
       " Fase 1: ArticleMeta API (ISIS-JSON). Fase 2: fallback HTML.",
       size="8.5px", fill="#888888")

A('</svg>')

# ─── Salva ────────────────────────────────────────────────────────────────────
out_path = r"C:\Users\hexem\dev\python\SciELO_scraper\flowchart_extracao_ptbr.svg"
with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out_lines))
print(f"SVG gerado: {out_path}  ({len(out_lines)} linhas)")
