FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
# Keys are passed at runtime: docker run --env-file .env -v "$PWD/results:/app/results" serpbench run -y
ENTRYPOINT ["serpbench"]
CMD ["--help"]