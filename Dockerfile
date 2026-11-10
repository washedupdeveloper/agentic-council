# Plain Dockerfile for hosts without Nix. The Nix image is the canonical one;
# this recipe exists so a non-NixOS user can build the same tool.
FROM python:3.12-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir setuptools wheel
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-deps --no-build-isolation -w /dist .

FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends bubblewrap git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
WORKDIR /repo
ENTRYPOINT ["council"]