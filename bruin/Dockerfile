# Bruin pipeline task for ECS Fargate (ARM64). Build from the bruin/ folder:
#   docker build -t firefighter-bruin bruin/
FROM ghcr.io/bruin-data/bruin:v0.11.832

WORKDIR /project
COPY --chown=1000:1000 pipeline.yml config.production.yml ./
COPY --chown=1000:1000 assets ./assets

# Bruin looks for a git repository root, so make /project one.
USER root
RUN git init -q /project && chown -R 1000:1000 /project
USER 1000

ENV PGPORT=5432 PGSSLMODE=require PGDATABASE=firefighter

CMD ["bruin", "run", "--config-file", "/project/config.production.yml", "--environment", "production", "--force", "/project"]
