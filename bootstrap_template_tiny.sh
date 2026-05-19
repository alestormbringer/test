#!/bin/bash
# Bootstrap script — crea la struttura completa di template_tiny
# Esegui nella directory dove hai clonato alestormbringer/template_tiny
# Uso: bash bootstrap_template_tiny.sh

set -e

echo "Creazione struttura template_tiny..."

mkdir -p docker scripts config data logs

# ---------- docker/Dockerfile ----------
cat > docker/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "tinyagi"]
EOF

# ---------- docker-compose.yml ----------
cat > docker-compose.yml << 'EOF'
version: "3.9"

services:
  tinyagi:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: tinyagi
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    ports:
      - "${TINYAGI_PORT:-8090}:8090"
    networks:
      - tinyagi-net

networks:
  tinyagi-net:
    driver: bridge
EOF

# ---------- .env.example ----------
cat > .env.example << 'EOF'
# tinyAGI configuration
# Copia questo file in .env e inserisci i tuoi valori

# Porta esposta sul VPS (NON usare 8080 — riservata al trading bot)
TINYAGI_PORT=8090

# API key del provider LLM
OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Impostazioni agente
AGENT_NAME=tinyagi
AGENT_MAX_ITERATIONS=10
AGENT_VERBOSE=true

# Logging
LOG_LEVEL=INFO
EOF

# ---------- requirements.txt ----------
cat > requirements.txt << 'EOF'
tinyagi>=0.1.0
python-dotenv>=1.0.0
EOF

# ---------- config/tinyagi_config.yaml ----------
cat > config/tinyagi_config.yaml << 'EOF'
agent:
  name: tinyagi
  max_iterations: 10
  verbose: true

llm:
  provider: openai        # openai | anthropic
  model: gpt-4o-mini      # cambia con il modello che preferisci
  temperature: 0.7
  max_tokens: 2048

server:
  host: 0.0.0.0
  port: 8090

logging:
  level: INFO
  file: logs/tinyagi.log
EOF

# ---------- scripts/setup.sh ----------
cat > scripts/setup.sh << 'EOF'
#!/bin/bash
# OVHcloud VPS — setup iniziale per tinyAGI
# Esegui una sola volta come root o con sudo: bash scripts/setup.sh

set -e

echo "[1/4] Aggiornamento sistema..."
apt-get update && apt-get upgrade -y

echo "[2/4] Installazione Docker..."
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
else
  echo "Docker già installato, skip."
fi

echo "[3/4] Installazione Docker Compose plugin..."
apt-get install -y docker-compose-plugin

echo "[4/4] Creazione .env da esempio..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> .env creato. Inserisci le tue API key prima di avviare."
else
  echo ">> .env già presente, non sovrascrivo."
fi

echo ""
echo "Setup completato. Prossimi passi:"
echo "  1. Modifica .env con le tue API key"
echo "  2. Esegui: docker compose up -d"
echo "  3. Controlla i log: docker compose logs -f"
EOF
chmod +x scripts/setup.sh

# ---------- scripts/start.sh ----------
cat > scripts/start.sh << 'EOF'
#!/bin/bash
# Avvia tinyAGI (o riavvia se già in esecuzione)
set -e

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "ERRORE: file .env non trovato. Copia .env.example in .env e inserisci i tuoi valori."
  exit 1
fi

echo "Avvio tinyAGI..."
docker compose up -d --build
docker compose logs -f
EOF
chmod +x scripts/start.sh

# ---------- placeholder per cartelle git-ignorate ----------
touch logs/.gitkeep
touch data/.gitkeep

# ---------- .gitignore ----------
cat > .gitignore << 'EOF'
.env
logs/*.log
data/
__pycache__/
*.py[cod]
.venv/
EOF

# ---------- README.md ----------
cat > README.md << 'EOF'
# template_tiny — tinyAGI su OVHcloud VPS

Setup standalone per [tinyAGI](https://github.com/agi-now/tinyagi) su VPS OVHcloud.
Completamente indipendente dal trading bot — directory diversa, rete Docker diversa, porta diversa.

## Struttura

```
template_tiny/
├── docker/
│   └── Dockerfile
├── scripts/
│   ├── setup.sh        # Setup iniziale VPS (installa Docker, ecc.)
│   └── start.sh        # Avvia / riavvia tinyAGI
├── config/
│   └── tinyagi_config.yaml
├── data/               # Dati persistenti agente (git-ignored)
├── logs/               # File di log (git-ignored)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Quick Start sul VPS OVHcloud

### 1. Clona la repo sul VPS

```bash
git clone https://github.com/alestormbringer/template_tiny.git
cd template_tiny
```

### 2. Setup iniziale (installa Docker se non presente)

```bash
bash scripts/setup.sh
```

### 3. Configura le API key

```bash
cp .env.example .env
nano .env   # inserisci OPENAI_API_KEY (o ANTHROPIC_API_KEY)
```

### 4. Avvia tinyAGI

```bash
docker compose up -d
```

Dashboard disponibile su `http://<ip-vps>:8090`

## Porte (nessun conflitto con il trading bot)

| Servizio     | Porta |
|---|---|
| Trading bot  | 8080  |
| tinyAGI      | 8090  |

## Comandi utili

```bash
# Log in tempo reale
docker compose logs -f

# Stop
docker compose down

# Riavvio dopo modifica config
docker compose up -d --build
```

## Note

- tinyAGI gira sulla sua rete Docker (`tinyagi-net`) — isolato dal trading bot.
- Le cartelle `data/` e `logs/` sono montate come volumi e ignorate da git.
- Non usare mai la stessa porta per i due servizi.
EOF

echo ""
echo "Struttura creata con successo!"
echo ""
echo "Ora esegui:"
echo "  git add ."
echo "  git commit -m 'feat: initial tinyAGI OVHcloud VPS setup'"
echo "  git push origin main"
