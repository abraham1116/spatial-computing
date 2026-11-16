# Spatial Computing: hub, agent and account service in one image. Select the command in docker-compose.yml.
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE* ./
COPY spatial ./spatial
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 spatial && mkdir -p /data && chown spatial /data
COPY --from=build /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl
USER spatial
WORKDIR /data
VOLUME /data
EXPOSE 7700 8090
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8090/api/health', timeout=3)" || exit 1
ENTRYPOINT ["spatial"]
CMD ["--help"]
