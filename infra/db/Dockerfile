# PostGIS 3.4 on Postgres 16, plus pgvector. pg_trgm ships with Postgres contrib.
FROM postgis/postgis:16-3.4
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-16-pgvector && rm -rf /var/lib/apt/lists/*
