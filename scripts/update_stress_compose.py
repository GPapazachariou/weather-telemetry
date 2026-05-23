#!/usr/bin/env python3
"""Ensure docker-compose.stress.yml has PYTHONUNBUFFERED=1 for all station services."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.stress.yml"

content = COMPOSE_FILE.read_text()

pattern = r"(      - WEATHER_STATION_MAX_RETRIES=3)\n(?!      - PYTHONUNBUFFERED=1\n)(    depends_on:)"
replacement = r"\1\n      - PYTHONUNBUFFERED=1\n\2"
updated_content = re.sub(pattern, replacement, content)

COMPOSE_FILE.write_text(updated_content)

print(f"Updated {COMPOSE_FILE} with PYTHONUNBUFFERED=1 where needed")
