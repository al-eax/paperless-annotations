FROM nikolaik/python-nodejs:python3.13-nodejs25-slim

WORKDIR /app

# Install git (required to install Python packages from git URLs) and certificates
RUN apt-get update \
	&& apt-get install -y --no-install-recommends git ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

RUN npm install

RUN chmod +x ./docker-entrypoint.sh

# Install Python dependencies using uv (will create its venv)
RUN uv sync

# Collect static files at build time so they are baked into the image
RUN uv run python manage.py collectstatic --no-input || true

# Expose application port
EXPOSE 8000

# Run the app through uv so commands execute in uv-managed environment
ENTRYPOINT ["./docker-entrypoint.sh"]
