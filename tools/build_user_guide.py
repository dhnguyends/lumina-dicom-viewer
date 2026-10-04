"""Authoring only: render guide HTML and a figure from a purely synthetic phantom.

Requires matplotlib and mistune in the notebook environment; not needed to run Lumina.
"""
from pathlib import Path
import html
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mistune
import numpy as np
import server
from generate_demo import phantom


def main():
    assets = ROOT / 'static' / 'guide-assets'
    assets.mkdir(exist_ok=True)
    index = 24
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 5.0), facecolor='#11191d')
    for ax, (label, center, width) in zip(axes, [('Poumon', -600, 1500), ('Tissus mous', 40, 400), ('Os', 400, 1800)]):
        image = (server.window_pixels(phantom(index), center, width) * 255).astype(np.uint8)
        ax.imshow(image, cmap='gray', vmin=0, vmax=255)
        ax.set_title(f'{label}\nCentre {center} HU · Largeur {width} HU', color='#e1ebe6', fontsize=13, pad=16)
        ax.axis('off')
    fig.text(.5, .055, f'Fantôme synthétique · Trois fenêtres · Aucune donnée patient', ha='center', color='#abc1b7', fontsize=11)
    fig.subplots_adjust(left=.025, right=.975, top=.81, bottom=.12, wspace=.06)
    fig.savefig(assets / 'fenetres-ct.png', dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)

    source = (ROOT / 'GUIDE_UTILISATEUR.md').read_text(encoding='utf-8')
    source = source.replace('static/guide-assets/', '/guide-assets/').replace('screenshots/', '/guide-assets/')
    renderer = mistune.create_markdown(escape=True, plugins=['table'])
    body = renderer(source)
    toc = []
    def heading(match):
        level, text = match.groups()
        plain = re.sub('<[^>]+>', '', text)
        normalized = unicodedata.normalize('NFKD', html.unescape(plain))
        slug = re.sub(r'[^a-z0-9]+', '-', normalized.encode('ascii', 'ignore').decode().lower()).strip('-')
        if level == '2':
            toc.append(f'<a href="#{slug}">{text}</a>')
        return f'<h{level} id="{slug}">{text}</h{level}>'
    body = re.sub(r'<h([12])>(.*?)</h\1>', heading, body)
    body = body.replace('<table>', '<div class="table-scroll"><table>').replace('</table>', '</table></div>')
    document = '''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lumina — Guide utilisateur</title><link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/guide.css"></head>
<body><header><a class="brand" href="/"><img src="/favicon.svg" alt="">Lumina<span>LE GUIDE</span></a>
<div><a class="back" href="/">Retour à la bibliothèque</a><a class="download" href="/guide.md" download="GUIDE_UTILISATEUR.md">Télécharger le guide</a></div></header>
<div class="guide-layout"><nav aria-label="Sommaire"><span class="nav-title">DANS CE GUIDE</span>TOC</nav>
<main><article>BODY</article><footer>Lumina · Guide utilisateur · 4 octobre 2026<br>Pour une version PDF, utilisez la commande Imprimer de votre navigateur, puis « Enregistrer au format PDF ».</footer></main></div></body></html>'''
    document = document.replace('TOC', '\n'.join(toc)).replace('BODY', body)
    (ROOT / 'static' / 'guide.html').write_text(document, encoding='utf-8')
    print(f'Guide généré : {len(toc)} sections ; figure synthétique de la coupe {index + 1}.')


if __name__ == '__main__':
    main()
