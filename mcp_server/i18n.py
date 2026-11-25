"""Dutch versions of the messages the customer sees in the Studio panel.

The checks write English (that is also what Claude reads). For the panel we match each
English message against a pattern and fill the same numbers into a Dutch sentence.
A message without a pattern stays English: it is never dropped or guessed.
"""

from __future__ import annotations

import re
from collections.abc import Callable

SIDES = {"left": "links", "right": "rechts", "top": "boven", "bottom": "onder"}

Template = str | Callable[[re.Match], str]

_NL: list[tuple[str, Template]] = [
    # bleed
    (r"Your file has room for bleed, but the design stops at the cut line \((?P<s>[a-z, ]+)\)\. After cutting, "
     r"a thin white line may show\. Extend the background (?P<r>[\d.]+) mm past the cut line\.",
     lambda m: "Je bestand heeft ruimte voor afloop, maar het ontwerp stopt bij de snijlijn ("
               + ", ".join(SIDES.get(x.strip(), x.strip()) for x in m["s"].split(","))
               + f"). Na het snijden kan er een dun wit randje zichtbaar zijn. Laat de achtergrond {m['r']} mm "
                 "over de snijlijn doorlopen."),
    (r"Your design has no bleed, but colour or images reach the edge\. After cutting, a thin white line may show\. "
     r"Extend the design (?P<r>[\d.]+) mm past each edge\.",
     "Je ontwerp heeft geen afloop, maar kleur of beeld loopt tot de rand. Na het snijden kan er een dun wit "
     "randje zichtbaar zijn. Laat het ontwerp aan elke kant {r} mm doorlopen."),
    (r"Bleed is only (?P<b>[\d.]+) mm; (?P<r>[\d.]+) mm is needed\.",
     "De afloop is maar {b} mm; er is {r} mm nodig."),
    # size
    (r"Your page is (?P<w>\d+) x (?P<h>\d+) mm, but the product is (?P<a>[\d.]+) x (?P<b>[\d.]+) mm\. "
     r"The shape is right, so it can be scaled to fit\.",
     "Je pagina is {w} x {h} mm, maar het product is {a} x {b} mm. De vorm klopt, dus het kan op maat "
     "worden geschaald."),
    (r"Your page is (?P<w>\d+) x (?P<h>\d+) mm, but the product is (?P<a>[\d.]+) x (?P<b>[\d.]+) mm with a "
     r"different shape\. Printing it would crop or stretch your design\.",
     "Je pagina is {w} x {h} mm, maar het product is {a} x {b} mm en heeft een andere vorm. Bij het drukken "
     "wordt je ontwerp bijgesneden of uitgerekt."),
    # pages
    (r"Your file has (?P<n>\d+) pages, but this product has at most (?P<m>\d+) printed sides?\. "
     r"Please remove the extra pages\.",
     lambda m: f"Je bestand heeft {m['n']} pagina's, maar dit product heeft maximaal {m['m']} bedrukte "
               f"{'kant' if m['m'] == '1' else 'kanten'}. Verwijder de extra pagina's."),
    # resolution
    (r"A picture \((?P<w>\d+) x (?P<h>\d+) px printed (?P<W>\d+) x (?P<H>\d+) mm\) has only (?P<d>\d+) dpi and "
     r"will look blurry\. Use a larger image or a vector logo \(at least (?P<m>[\d.]+) dpi\)\.",
     "Een afbeelding ({w} x {h} px, gedrukt op {W} x {H} mm) heeft maar {d} dpi en wordt wazig. Gebruik een "
     "grotere afbeelding of een vectorlogo (minstens {m} dpi)."),
    (r"A picture has (?P<d>\d+) dpi; (?P<m>[\d.]+) dpi is recommended\. It may look slightly soft in print\.",
     "Een afbeelding heeft {d} dpi; {m} dpi wordt aangeraden. In druk kan hij iets onscherp ogen."),
    # colour
    (r"(?P<n>\d+) picture\(s\) use RGB \(screen colours\) instead of CMYK \(print colours\)\. "
     r"Very bright colours may print duller than on your screen\.",
     "{n} afbeelding(en) in RGB (schermkleuren) in plaats van CMYK (drukkleuren). Heel felle kleuren kunnen "
     "doffer worden gedrukt dan op je scherm."),
    (r"Your file uses spot colour\(s\) \((?P<n>.+)\)\. Standard printing uses CMYK, so they will be converted "
     r"and may look slightly different\. Ask your designer if the exact colour matters\.",
     "Je bestand gebruikt steunkleur(en) ({n}). Standaard drukwerk is CMYK, dus ze worden omgezet en kunnen er "
     "iets anders uitzien. Vraag je ontwerper om advies als de exacte kleur belangrijk is."),
    # fonts
    (r"Font\(s\) not embedded: (?P<n>.+)\. The printer may swap them for another font\. Export the PDF with "
     r"fonts embedded, or convert text to outlines\.",
     "Lettertype(s) niet ingesloten: {n}. De drukker kan ze vervangen door een ander lettertype. Exporteer de "
     "pdf met ingesloten lettertypen of zet de tekst om naar contouren."),
    # safe zone
    (r"\"(?P<t>.+)\" is (?P<d>[\d.]+) mm from the cut line and may be cut off\. Move it at least (?P<s>[\d.]+) mm "
     r"inside\.",
     "\"{t}\" staat {d} mm van de snijlijn en kan worden weggesneden. Zet het minstens {s} mm naar binnen."),
    (r"\"(?P<t>.+)\" is (?P<d>[\d.]+) mm from the cut line; (?P<s>[\d.]+) mm is safer\.",
     "\"{t}\" staat {d} mm van de snijlijn; {s} mm is veiliger."),
    # text and contact details
    (r"\"(?P<t>.+)\" does not look like a valid email address\. Please check it\.",
     "\"{t}\" lijkt geen geldig e-mailadres. Controleer het even."),
    (r"\"(?P<t>.+)\" does not look like a complete web address\. Please check it\.",
     "\"{t}\" lijkt geen volledig webadres. Controleer het even."),
    (r"Phone number \"(?P<p>.+)\" has (?P<k>\d+) digits after \+31; Dutch numbers have 9\. Please check it\.",
     "Telefoonnummer \"{p}\" heeft {k} cijfers na +31; Nederlandse nummers hebben er 9. Controleer het even."),
    (r"Phone number \"(?P<p>.+)\" has (?P<k>\d+) digits; Dutch mobile numbers have 10\. Please check it\.",
     "Telefoonnummer \"{p}\" heeft {k} cijfers; Nederlandse mobiele nummers hebben er 10. Controleer het even."),
    (r"Phone number \"(?P<p>.+)\" has (?P<k>\d+) digits; international numbers have 8 to 15\. Please check it\.",
     "Telefoonnummer \"{p}\" heeft {k} cijfers; internationale nummers hebben er 8 tot 15. Controleer het even."),
    (r"Possible typo: \"(?P<w>[^\"]+)\"\. Did you mean \"(?P<s>[^\"]+)\"\?",
     "Mogelijke typfout: \"{w}\". Bedoel je \"{s}\"?"),
    (r"Possible typo: \"(?P<w>[^\"]+)\"\.", "Mogelijke typfout: \"{w}\"."),
    # files that cannot be checked
    (r"This PDF could not be opened\. It may be damaged\.",
     "Deze pdf kan niet worden geopend. Misschien is het bestand beschadigd."),
    (r"This image could not be opened\. It may be damaged\.",
     "Deze afbeelding kan niet worden geopend. Misschien is het bestand beschadigd."),
    (r"This PDF is password-protected\. Please upload an unlocked file\.",
     "Deze pdf is beveiligd met een wachtwoord. Upload een bestand zonder wachtwoord."),
    (r"This PDF has no pages\.", "Deze pdf heeft geen pagina's."),
    (r"'(?P<s>.+)' files are not supported here\. Please upload a PDF, PNG or JPG\.",
     "'{s}'-bestanden worden hier niet ondersteund. Upload een pdf, png of jpg."),
    (r"This looks like a camera photo \((?P<c>.+)\), not a design file\. A photo of a printed card can't be "
     r"checked reliably\. Please upload the file you designed \(PDF, or a PNG/JPG export\)\.",
     "Dit lijkt een foto van een camera ({c}), geen ontwerpbestand. Een foto van een gedrukt kaartje kan niet "
     "betrouwbaar worden gecontroleerd. Upload het bestand dat je hebt ontworpen (pdf, of een png/jpg-export)."),
    # automatic fix
    (r"Page (?P<p>\d+): added (?P<b>[\d.]+) mm bleed by extending the edge colours\.",
     "Pagina {p}: {b} mm afloop toegevoegd door de randkleuren door te trekken."),
    (r"Page (?P<p>\d+): converted to CMYK \(colour-managed, no printer profile\)\.",
     "Pagina {p}: kleuren omgezet naar drukkleuren (CMYK)."),
    (r"Page (?P<p>\d+): scaled to (?P<w>[\d.]+) x (?P<h>[\d.]+) mm\.",
     "Pagina {p}: geschaald naar {w} x {h} mm."),
    (r"Page (?P<p>\d+): wrong shape for this product, cannot fix safely\.",
     "Pagina {p}: verkeerde vorm voor dit product, dit kunnen we niet veilig herstellen."),
    (r"Pages are now (?P<d>\d+)-dpi images: text is no longer editable in this file\.",
     "Pagina's zijn nu afbeeldingen van {d} dpi: de tekst is in dit bestand niet meer bewerkbaar."),
]

_COMPILED = [(re.compile(p), t) for p, t in _NL]


def translate(message: str, lang: str) -> str:
    """The message in `lang` ("en" or "nl"); English when there is no Dutch pattern for it."""
    if lang != "nl":
        return message
    for pattern, template in _COMPILED:
        m = pattern.fullmatch(message)
        if m:
            return template(m) if callable(template) else template.format(**m.groupdict())
    return message


def is_translated(message: str) -> bool:
    return any(p.fullmatch(message) for p, _ in _COMPILED)
