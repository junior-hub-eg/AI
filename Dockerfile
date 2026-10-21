FROM python:3.12-slim

# The model provider package, for example langchain-openai or langchain-google-genai (see requirements.txt).
ARG PROVIDER_PACKAGE=langchain-cohere

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt ${PROVIDER_PACKAGE}

COPY app ./app
COPY data ./data

RUN useradd --create-home assistant
USER assistant

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
