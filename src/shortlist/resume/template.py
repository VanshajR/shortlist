"""The resume as LaTeX, in the layout I use on Overleaf (Jake's resume), icons and all,
with fixes that don't change how it looks:

- each icon carries empty "actual text" (accsupp), so it still shows but no longer comes
  out of the PDF as "♂phone-alt" or "/gl⌢be" glued to the phone number and links, which
  is what an applicant-tracking system reads
- \\pdfgentounicode, so every other character extracts as the character it looks like
- the skills are a proper list: bare \\item lines there are a LaTeX error that Overleaf
  quietly tolerates
"""
import re

PREAMBLE = r"""\documentclass[letterpaper,11pt]{article}
\input{glyphtounicode}
% the contact icons read as spaces to anything extracting text, whether or not it honours
% ActualText (pdftotext does, some parsers don't)
\pdfglyphtounicode{phone-alt}{0020}\pdfglyphtounicode{envelope}{0020}\pdfglyphtounicode{linkedin}{0020}
\pdfglyphtounicode{github}{0020}\pdfglyphtounicode{globe}{0020}
\pdfgentounicode=1

\usepackage{fontawesome5}
\usepackage{accsupp}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage[usenames,dvipsnames]{color}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}

\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\textwidth}{0.8in}
\addtolength{\topmargin}{-0.8in}
\addtolength{\textheight}{1.0in}

\titleformat{\section}{\vspace{-4pt}\scshape\raggedright\large}{}{0em}{}[\color{red}\titlerule \vspace{-5pt}]

\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-4pt}}}
\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}
\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}
\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in,label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}
% an icon you see but a text extractor doesn't
\newcommand{\icon}[1]{\BeginAccSupp{method=escape,ActualText={}}\faIcon{#1}\EndAccSupp{}}
"""

# "|" too: in the default font encoding a typed | prints as an em dash
_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
            "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "|": r"\textbar{}"}


def tex(text: str) -> str:
    """Plain text made safe for LaTeX, keeping **bold** as \\textbf."""
    out = "".join(_SPECIAL.get(c, c) for c in str(text))
    out = out.replace("–", "--").replace("—", "---")
    return re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", out)


def _month(yyyymm: str | None) -> str:
    months = "Jan Feb Mar Apr May June July Aug Sep Oct Nov Dec".split()
    if not yyyymm:
        return "Present"
    year, _, month = yyyymm.partition("-")
    return f"{months[int(month) - 1]} {year}" if month else year


def render(profile: dict, selection: dict, phone: str | None = None) -> str:
    me = profile["profile"]
    links = me.get("links", {})
    contact = [("phone-alt", phone, None), ("envelope", me.get("email"), f"mailto:{me.get('email')}"),
               ("linkedin", _bare(links.get("linkedin")), links.get("linkedin")),
               ("github", _bare(links.get("github")), links.get("github")),
               ("globe", _bare(me.get("website")), me.get("website"))]
    contact_tex = " $|$ \n    ".join(
        rf"\icon{{{icon}}}~" + (rf"\href{{{url}}}{{{tex(shown)}}}" if url else tex(shown))
        for icon, shown, url in contact if shown)

    parts = [PREAMBLE, r"\begin{document}", r"\begin{center}",
             rf"    \textbf{{\Huge \scshape {tex(me['name'])}}} \\ \vspace{{2pt}}",
             rf"    \textcolor{{blue}}{{{contact_tex}}} \\ \vspace{{2pt}}",
             rf"    \textbf{{{tex(me.get('headline', ''))}}}",
             r"\end{center}", ""]

    parts += [r"\section{\textcolor{red}{Skills}}", r"\begin{itemize}[leftmargin=0.15in,label={}]"]
    for line in _skill_lines(selection["skills"]):
        parts.append(rf"\resumeItem{{{line}}}")
    parts += [r"\end{itemize}", ""]

    parts += [r"\section{\textcolor{red}{Education}}", r"\resumeSubHeadingListStart"]
    parts += _education(selection["education"])
    parts += [r"\resumeSubHeadingListEnd", ""]

    work = [e for e in selection["experience"] if e.data.get("kind") == "work"]
    lead = [e for e in selection["experience"] if e.data.get("kind") != "work"]
    if work:
        parts += [r"\section{\textcolor{red}{Work Experience}}", r"\resumeSubHeadingListStart"]
        parts += [line for e in work for line in _role(e)]
        parts += [r"\resumeSubHeadingListEnd", ""]

    if selection["projects"]:
        parts += [r"\section{\textcolor{red}{Projects}}", r"\resumeSubHeadingListStart"]
        for p in selection["projects"]:
            d = p.data
            tech = ", ".join(d.get("resume_tech") or d.get("tech", [])[:5])
            code = (d.get("links") or {}).get("code") or (d.get("links") or {}).get("live")
            link = rf"\href{{{code}}}{{\textcolor{{blue}}{{{'GitHub' if code and 'github.com' in code else 'Link'}}}}}" if code else ""
            parts.append(rf"\resumeProjectHeading{{\textbf{{{tex(d.get('resume_name') or d['name'])}}} (\textit{{{tex(tech)}}})}}{{{link}}}")
            parts += [r"\resumeItemListStart", *[rf"\resumeItem{{{tex(b.text)}}}" for b in p.bullets], r"\resumeItemListEnd"]
        parts += [r"\resumeSubHeadingListEnd", ""]

    if lead:
        parts += [r"\section{\textcolor{red}{Leadership}}", r"\resumeSubHeadingListStart"]
        parts += [line for e in lead for line in _role(e)]
        parts += [r"\resumeSubHeadingListEnd", ""]

    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def _role(entry) -> list[str]:
    d = entry.data
    return [rf"\resumeSubheading{{{tex(d['role'])}}}{{{_month(d.get('start'))} -- {_month(d.get('end'))}}}"
            rf"{{{tex(d['org'])}}}{{{tex(d.get('location', ''))}}}",
            r"\resumeItemListStart", *[rf"\resumeItem{{{tex(b.text)}}}" for b in entry.bullets],
            r"\resumeItemListEnd", r"\vspace{2pt}"]


def _education(entries: list[dict]) -> list[str]:
    """The degree on its own line; school results from one school share a line."""
    out, schools = [], {}
    for e in entries:
        if e.get("degree", "").startswith("Class"):
            schools.setdefault(e["institution"], []).append(e)
            continue
        score = f" $|$ {tex(e['score'])}" if e.get("score") else ""
        out.append(rf"\resumeSubheading{{{tex(e['institution'])}}}{{{tex(e.get('location', ''))}}}"
                   rf"{{{tex(e['degree'])}{score}}}{{{_month(e.get('end'))}}}")
    for name, rows in schools.items():
        results = " $|$ ".join(f"{tex(r['degree'].split(' (')[0])}: {tex(r.get('score', ''))}" for r in rows)
        out.append(rf"\resumeSubheading{{{tex(name)}}}{{{tex(rows[0].get('location', ''))}}}"
                   rf"{{{results}}}{{{_month(max(r.get('end', '') for r in rows))}}}")
    return out


def _skill_lines(groups) -> list[str]:
    """Short groups share a line, as on the hand-made resume."""
    cells = [(g, rf"\textbf{{{tex(g)}:}} {tex(', '.join(items))}", len(g) + len(", ".join(items))) for g, items in groups]
    lines, i = [], 0
    while i < len(cells):
        if i + 1 < len(cells) and cells[i][2] + cells[i + 1][2] < 95:  # longer pairs wrap; worse than two lines
            lines.append(cells[i][1] + r" \hfill " + cells[i + 1][1])
            i += 2
        else:
            lines.append(cells[i][1])
            i += 1
    return lines


def _bare(url: str | None) -> str | None:
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/") if url else None


