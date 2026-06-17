"""Assemble drafted sections into a downloadable .tex file.

We use a minimal article template -- the goal is "this opens in Overleaf"
not "this is camera-ready for NeurIPS". Real submission would use the
venue's official LaTeX class; we cite the venue in the title block.
"""

from __future__ import annotations

import re
from datetime import datetime
from textwrap import dedent

from paperpilot.arxiv_lookup import bibtex_for
from paperpilot.cfp_match import VenueMatch
from paperpilot.draft import CITATION_RE, DraftSection
from paperpilot.llm_ingest import ResearchSummary


TEMPLATE = dedent(
    r"""
    \documentclass[11pt]{article}
    \usepackage[utf8]{inputenc}
    \usepackage[margin=1in]{geometry}
    \usepackage{authblk}
    \usepackage{cite}

    \title{<<TITLE>>}
    \author{<<AUTHORS>>}
    \date{Drafted by Merit for \emph{<<VENUE>>} on <<DATE>>}

    \begin{document}
    \maketitle

    \begin{abstract}
    <<ABSTRACT>>
    \end{abstract}

    \section{Introduction}
    <<INTRO>>

    \section{Related Work}
    <<RELATED>>

    \section{Method}
    <<METHOD>>

    \section{Results}
    \emph{Results section drafted from the repository's reported numbers and qualitative findings:}

    <<RESULTS>>

    \section{Discussion and Limitations}
    \emph{Limitations the repository acknowledges or that follow from the method:}

    <<LIMITATIONS>>

    \bibliographystyle{plain}
    \bibliography{references}

    \end{document}
    """
).strip()


def _convert_citations(text: str) -> str:
    """Convert our `[arxiv:id]` markers into LaTeX `\cite{key}` calls.

    Citation keys follow the bibtex_for() convention so they resolve against
    the references.bib emitted by export_paper().
    """

    def sub(m: re.Match[str]) -> str:
        aid = m.group(1).strip()
        key = f"arxiv_{aid.replace('.', '_')}"
        return f"\\cite{{{key}}}"

    return CITATION_RE.sub(sub, text)


def _suggest_title(summary: ResearchSummary) -> str:
    # Use the contribution as a working title; LLM-generated titles tend to be
    # generic, and the contribution is at least specific to the work.
    raw = summary.contribution.split(".")[0].strip()
    return raw or f"Notes from a {datetime.now():%Y} hackathon"


def export_paper(
    summary: ResearchSummary,
    venue: VenueMatch,
    sections: dict[str, DraftSection],
    authors: str = "Merit",
) -> tuple[str, str]:
    """Return (tex_source, bibtex_source) ready to write to disk."""
    abstract = _convert_citations(sections.get("abstract", DraftSection("abstract", "")).text)
    intro = _convert_citations(sections.get("intro", DraftSection("intro", "")).text)
    related = _convert_citations(sections.get("related", DraftSection("related", "")).text)
    method = _convert_citations(sections.get("method", DraftSection("method", "")).text)

    body = (
        TEMPLATE.replace("<<TITLE>>", _suggest_title(summary))
        .replace("<<AUTHORS>>", authors)
        .replace("<<VENUE>>", venue.name)
        .replace("<<DATE>>", datetime.now().strftime("%Y-%m-%d"))
        .replace("<<ABSTRACT>>", abstract or "(abstract pending)")
        .replace("<<INTRO>>", intro or "(introduction pending)")
        .replace("<<RELATED>>", related or "(related work pending)")
        .replace("<<METHOD>>", method or "(method section pending)")
        .replace("<<RESULTS>>", summary.results.replace("&", r"\&"))
        .replace("<<LIMITATIONS>>", summary.limitations.replace("&", r"\&"))
    )

    bib_entries = []
    for section in sections.values():
        for cite in section.citations:
            bib_entries.append(bibtex_for(cite))

    bibtex = "\n".join(bib_entries)
    return body, bibtex
