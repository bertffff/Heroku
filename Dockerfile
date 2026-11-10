FROM python:3.14

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    DOCKER=true \
    GIT_PYTHON_REFRESH=quiet

# Runtime libraries the core and optional modules shell out to.
# Node is only for the opt-in eval module. No SSH server, no third-party
# install scripts, and no clone of a different GitHub remote: the image is
# the checkout you build (docker build from this tree).
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    ffmpeg \
    git \
    libcairo2 \
    libmagic1 \
    nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && useradd --system --create-home --uid 1000 --shell /bin/bash kanjo \
    && mkdir -p /data/sessions /data/loaded_modules \
    && chown -R kanjo:kanjo /data

WORKDIR /opt/kanjo

COPY --chown=kanjo:kanjo . /opt/kanjo

RUN pip install --no-cache-dir --upgrade -r /opt/kanjo/requirements.txt \
    && python -c "import hashlib; from pathlib import Path; p=Path('/opt/kanjo/requirements.txt'); Path('/opt/kanjo/.requirements_hash').write_text(hashlib.sha256(p.read_bytes()).hexdigest())" \
    && if [ -d /opt/kanjo/.git ]; then chown -R kanjo:kanjo /opt/kanjo/.git; fi \
    && chown kanjo:kanjo /opt/kanjo/.requirements_hash \
    && rm -rf /root/.cache/pip

USER kanjo
# Drop the builder's hooks path. Git refuses that config when it is not the
# repo owner, so this runs as the runtime user.
RUN if [ -d /opt/kanjo/.git ]; then git -C /opt/kanjo config --unset-all core.hooksPath || true; fi
# Runtime pip (startup hash check and `.update`) cannot write the system
# site-packages. User-site installs stay on this account's sys.path.
ENV PIP_USER=1 \
    PATH="/home/kanjo/.local/bin:${PATH}"
VOLUME /data

CMD ["python", "-m", "kanjo"]
