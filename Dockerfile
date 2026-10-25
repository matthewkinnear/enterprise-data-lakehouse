
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYSPARK_PYTHON=python \
    PYSPARK_DRIVER_PYTHON=python \
    SPARK_LOCAL_IP=127.0.0.1 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

WORKDIR /workspace

# Install Java and required system utilities.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        procps \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Install project dependencies before copying source.
# This allows Docker to cache the dependency installation.
COPY pyproject.toml ./

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        "pyspark==4.0.1" \
        "jupyterlab" \
        "ipykernel" \
        "pytest" \
        "ruff" \
        "pandas" \
        "pyarrow"

# Copy the Python package and install it in editable mode.
COPY src/ ./src/

RUN python -m pip install --no-cache-dir --no-deps -e .

EXPOSE 8888 4040

ENTRYPOINT ["tini", "--"]

CMD ["python", "-m", "jupyter", "lab", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--ServerApp.root_dir=/workspace"]
