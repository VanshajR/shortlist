# Hugging Face Docker Space: runs as uid 1000 and expects port 7860
FROM python:3.12-slim

RUN useradd -m -u 1000 app
WORKDIR /home/app/shortlist

COPY --chown=app pyproject.toml README.md ./
COPY --chown=app src ./src
RUN pip install --no-cache-dir .

COPY --chown=app data/companies.toml ./data/companies.toml

USER app
ENV SHORTLIST_DB=/home/app/shortlist/data/shortlist.db
EXPOSE 7860
CMD ["uvicorn", "shortlist.app:app", "--host", "0.0.0.0", "--port", "7860"]
