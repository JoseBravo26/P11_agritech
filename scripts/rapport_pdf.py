"""Transforme le rapport métier Markdown en PDF mis en page.

Étapes : Markdown -> HTML (bibliothèque « markdown ») -> PDF A4 imprimé par le
navigateur Edge installé sur la machine (Playwright, sans téléchargement de
navigateur). Les images sont lues depuis le dossier reports/.

Lancement : python scripts/rapport_pdf.py
Sorties   : reports/rapport_metier.html et reports/rapport_metier.pdf
"""

from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOSSIER = Path(__file__).resolve().parents[1] / "reports"
SOURCE = DOSSIER / "rapport_metier.md"

# Mise en page : sobre et moderne, couleurs reprises des graphiques (vert agriculture, ardoise)
CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
:root { --vert: #15803d; --vert-clair: #f0fdf4; --ardoise: #1e293b; --gris: #64748b; --trait: #e2e8f0; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: var(--ardoise);
       font-size: 10.2pt; line-height: 1.5; margin: 0; }
h1 { font-size: 23pt; line-height: 1.2; margin: 0 0 6pt; color: var(--ardoise); letter-spacing: -0.3pt; }
h1 + p { color: var(--gris); margin-top: 0; }
h2 { font-size: 15pt; color: var(--vert); margin: 22pt 0 8pt; padding-bottom: 4pt;
     border-bottom: 2px solid var(--vert); page-break-after: avoid; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 6pt; page-break-after: avoid; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 18pt; margin: 4pt 0 8pt; }
li { margin: 2pt 0; }
strong { color: #0f172a; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #f1f5f9;
       padding: 1pt 4pt; border-radius: 3pt; }
hr { border: none; border-top: 1px solid var(--trait); margin: 16pt 0; }
a { color: var(--vert); text-decoration: none; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0 12pt; font-size: 9.2pt;
        page-break-inside: avoid; break-inside: avoid; }
thead th { background: var(--ardoise); color: white; font-weight: 600; text-align: left; padding: 5pt 7pt; }
tbody td { padding: 4.5pt 7pt; border-bottom: 1px solid var(--trait); vertical-align: top; }
tbody tr:nth-child(even) td { background: #f8fafc; }
img { max-width: 100%; display: block; margin: 8pt auto 12pt; border-radius: 6pt;
      page-break-inside: avoid; break-inside: avoid; }
p > img { max-height: 118mm; }
td img { margin: 2pt 0; max-height: 70mm; border: 1px solid var(--trait); }
/* Encadré de synthèse : la première section du rapport */
.synthese { background: var(--vert-clair); border-left: 4pt solid var(--vert); padding: 4pt 14pt 8pt;
            border-radius: 0 6pt 6pt 0; margin-bottom: 8pt; }
.synthese h2 { border: none; margin-top: 10pt; }
.saut { page-break-before: always; break-before: page; }
"""


def construire_html() -> str:
    texte = SOURCE.read_text(encoding="utf-8")
    corps = markdown.markdown(texte, extensions=["tables", "sane_lists"])
    # Met la synthèse (jusqu'à la section 1) en valeur dans un encadré
    debut, fin = corps.find("<h2>Synthèse</h2>"), corps.find("<h2>1. ")
    if debut != -1 and fin != -1:
        corps = corps[:debut] + '<div class="synthese">' + corps[debut:fin] + "</div>" + corps[fin:]
    # Le corps du rapport s'enchaîne sans page à moitié vide ; seules les annexes partent d'une nouvelle page
    for titre in ("<h2>Annexe A",):
        corps = corps.replace(titre, titre.replace("<h2>", '<h2 class="saut">'), 1)
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f"<title>Rapport métier · Agritech Answers</title><style>{CSS}</style></head>"
            f"<body>{corps}</body></html>")


def main() -> None:
    html = DOSSIER / "rapport_metier.html"
    html.write_text(construire_html(), encoding="utf-8")
    pied = ('<div style="font-size:8pt;color:#64748b;width:100%;padding:0 16mm;display:flex;'
            'justify-content:space-between;font-family:Segoe UI,Arial">'
            '<span>Agritech Answers · Rapport métier</span>'
            '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    with sync_playwright() as p:
        navigateur = p.chromium.launch(channel="msedge", headless=True)
        page = navigateur.new_page()
        page.goto(html.as_uri(), wait_until="networkidle")
        page.pdf(path=DOSSIER / "rapport_metier.pdf", format="A4", print_background=True,
                 display_header_footer=True, header_template="<span></span>", footer_template=pied,
                 margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
        navigateur.close()
    print(f"PDF : {DOSSIER / 'rapport_metier.pdf'}")


if __name__ == "__main__":
    main()
