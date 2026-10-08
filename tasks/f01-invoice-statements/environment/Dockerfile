FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# terminus-2 normally installs its terminal tools at trial startup. Bake them in
# so evaluation can run with network_mode = "no-network" and a stable toolchain.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git tmux \
    && rm -rf /var/lib/apt/lists/* \
    && pip install asciinema==2.4.0 pytest==8.4.1 iniconfig==2.3.0 packaging==26.3 pluggy==1.6.0 pygments==2.21.0

WORKDIR /app
COPY app/ /app/
RUN chmod +x workloads/run_visible.sh \
    && python workloads/gen_data.py --seed 20260801 --customers 5000 --out data/visible.db \
    && mkdir -p out
