# A small pdfLaTeX: TinyTeX plus the packages the resume template uses.
# pdfLaTeX (not XeTeX or Tectonic) because \pdfgentounicode, which makes the PDF's
# text readable to applicant-tracking systems, is a pdfTeX feature.
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget perl ca-certificates fontconfig xz-utils poppler-utils \
 && rm -rf /var/lib/apt/lists/*
RUN wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh
ENV PATH=/root/bin:$PATH
RUN tlmgr install fontawesome5 accsupp cm-super titlesec enumitem fancyhdr babel-english preprint tools \
    hyperref xcolor graphics etoolbox kvoptions pdftexcmds infwarerr ltxcmds kvsetkeys \
 && tlmgr path add
WORKDIR /work
ENTRYPOINT ["pdflatex", "-interaction=nonstopmode", "-halt-on-error"]
