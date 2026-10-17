"""Compile a resume and check it, trimming until it fits one page.

pdfLaTeX comes from the PATH when it's installed, otherwise from the Docker image in
latex/ (docker build -t shortlist-latex latex). The same image runs in CI.
"""
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from . import select, template

IMAGE = "shortlist-latex"


class CompileError(RuntimeError):
    pass


def compile_pdf(tex_source: str, workdir: Path) -> Path:
    (workdir / "resume.tex").write_text(tex_source, encoding="utf-8")
    if shutil.which("pdflatex"):
        cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"]
    elif shutil.which("docker"):
        cmd = ["docker", "run", "--rm", "-v", f"{workdir.resolve()}:/work", IMAGE, "resume.tex"]
    else:
        raise CompileError("no pdflatex and no docker: install one (see latex/Dockerfile)")
    run = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=180)
    pdf = workdir / "resume.pdf"
    if run.returncode or not pdf.exists():
        log = (workdir / "resume.log").read_text(encoding="utf-8", errors="replace") if (workdir / "resume.log").exists() else run.stdout
        errors = [line for line in log.splitlines() if line.startswith("!")]
        raise CompileError("LaTeX failed: " + ("; ".join(errors[:3]) or run.stderr[-300:]))
    return pdf


@dataclass
class Result:
    tex: str
    pdf: bytes
    pages: int
    problems: list[str]
    trimmed: int


def check(pdf_path: Path, selection: dict, profile: dict, phone: str | None) -> tuple[int, list[str]]:
    """What an applicant-tracking system would see, and whether the rules hold."""
    reader = PdfReader(str(pdf_path))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    flat = re.sub(r"\s+", "", text).lower()
    problems = []
    if len(reader.pages) > 1:
        problems.append(f"{len(reader.pages)} pages")
    for needed in [profile["profile"]["name"], profile["profile"].get("email"), phone]:
        if needed and re.sub(r"\s+", "", needed).lower() not in flat:
            problems.append(f"'{needed}' doesn't come out of the PDF as text")
    bullets = [b for e in selection["experience"] + selection["projects"] for b in e.bullets]
    for b in bullets:
        start = re.sub(r"\s+", "", re.sub(r"\*\*", "", b.text))[:40].lower()
        if start not in flat:
            problems.append(f"bullet doesn't extract cleanly: {b.text[:50]}")
    verbs = [b.verb for b in bullets]
    repeated = sorted({v for v in verbs if verbs.count(v) > 1})
    if repeated:
        problems.append("verbs used twice: " + ", ".join(repeated))
    return len(reader.pages), problems


def build(profile: dict, scores: dict[str, float] | None = None, job_text: str = "",
          phone: str | None = None, max_rounds: int = 12) -> Result:
    selection = select.choose(profile, scores, job_text)
    trimmed = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for _ in range(max_rounds):
            source = template.render(profile, selection, phone)
            pdf = compile_pdf(source, work)
            pages, problems = check(pdf, selection, profile, phone)
            if pages == 1 or not select.trim(selection):
                return Result(source, pdf.read_bytes(), pages, problems, trimmed)
            trimmed += 1
    return Result(source, pdf.read_bytes(), pages, problems + ["still too long after trimming"], trimmed)
