#!/bin/bash

# Create necessary directories
mkdir -p frontend/src/components
mkdir -p frontend/src/pages

# Start the development environment
docker-compose -f docker-compose.dev.yml up --build 