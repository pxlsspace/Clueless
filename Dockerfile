FROM python:3.9-slim
ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_VERSION=1.0.0
RUN pip3 install poetry
WORKDIR /usr/app
COPY poetry.lock pyproject.toml /usr/app/
RUN poetry config virtualenvs.create false \
  && poetry install --no-dev --no-interaction --no-ansi
COPY . .