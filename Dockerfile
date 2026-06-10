FROM debian:bookworm-slim

# Install necessary dependencies including Python and BIND9 utilities
RUN apt-get update && apt-get install -y \
    python3 \
    bind9 \
    bind9utils \
    bind9-doc \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Create a demo configuration directory for BIND9 inside the container
# This isolates the WebGUI from the system-level BIND9 installation
RUN mkdir -p /app/bind_config && \
    touch /app/bind_config/named.conf /app/bind_config/named.conf.local /app/bind_config/named.conf.options && \
    chmod -R 777 /app/bind_config

# Set environment variables
ENV BIND_CONFIG_DIR=/app/bind_config
ENV PORT=8080

# Expose the default port
EXPOSE 8080

# Run the Python server
CMD ["python3", "app.py"]
