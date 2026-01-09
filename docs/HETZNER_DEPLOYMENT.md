# Hetzner Deployment Guide

## Server Requirements

**Recommended:** CX31 or higher (4 vCPU, 8GB RAM, 80GB SSD) - ~€10/month
- Handles replay parsing (CPU-intensive)
- Room for 2 worker replicas
- PostgreSQL + Redis

**OS:** Ubuntu 22.04 LTS

---

## 1. Server Setup

```bash
# SSH in
ssh root@YOUR_HETZNER_IP

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# Install Docker Compose v2
apt install docker-compose-plugin -y

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
```

---

## 2. Clone & Configure

```bash
# Switch to deploy user
su - deploy

# Clone repo
git clone https://github.com/YOUR_USER/rlcoach.git
cd rlcoach

# Create production env file
cp .env.example .env.prod
nano .env.prod
```

**Required `.env.prod` values:**

```bash
# Database
POSTGRES_USER=rlcoach
POSTGRES_PASSWORD=<generate-strong-password>
POSTGRES_DB=rlcoach

# Auth
NEXTAUTH_URL=https://yourdomain.com
NEXTAUTH_SECRET=<openssl rand -base64 32>
BOOTSTRAP_SECRET=<openssl rand -base64 32>

# OAuth (get from Discord/Google dev consoles)
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Stripe (optional, for billing)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

# AI Coach
ANTHROPIC_API_KEY=
```

---

## 3. SSL Setup (Cloudflare or Let's Encrypt)

### Option A: Cloudflare (recommended)
1. Point domain to Hetzner IP in Cloudflare
2. Set SSL mode to "Full (strict)"
3. Download Origin Certificate to `nginx/ssl/`

### Option B: Let's Encrypt
```bash
# Install certbot
apt install certbot -y

# Get cert (stop nginx first if running)
certbot certonly --standalone -d yourdomain.com

# Copy certs
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
```

---

## 4. Deploy

```bash
# Build and start (first time takes ~5-10 min)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Run migrations (if needed)
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## 5. Verify

```bash
# Health checks
curl http://localhost:8000/health   # Backend
curl http://localhost:3000          # Frontend

# From outside
curl https://yourdomain.com/api/health
```

---

## 6. Maintenance

### Updates
```bash
cd ~/rlcoach
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

### Backups
```bash
# Database backup
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U rlcoach rlcoach > backups/backup-$(date +%Y%m%d).sql

# Add to crontab
0 3 * * * /home/deploy/rlcoach/scripts/backup.sh
```

### Logs
```bash
# All logs
docker compose -f docker-compose.prod.yml logs --tail=100

# Specific service
docker compose -f docker-compose.prod.yml logs -f worker
```

---

## Architecture on Hetzner

```
                    ┌─────────────┐
                    │  Cloudflare │
                    │   (DNS/SSL) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    nginx    │ :80/:443
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌───▼───┐ ┌──────▼──────┐
       │  frontend   │ │  API  │ │   static    │
       │  (Next.js)  │ │ proxy │ │   assets    │
       └─────────────┘ └───┬───┘ └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   backend   │ :8000
                    │  (FastAPI)  │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌───▼───┐ ┌──────▼──────┐
       │  PostgreSQL │ │ Redis │ │   Workers   │
       │   :5432     │ │ :6379 │ │  (Celery)   │
       └─────────────┘ └───────┘ └─────────────┘
```

---

## Quick Commands

| Action | Command |
|--------|---------|
| Start | `docker compose -f docker-compose.prod.yml up -d` |
| Stop | `docker compose -f docker-compose.prod.yml down` |
| Rebuild | `docker compose -f docker-compose.prod.yml up -d --build` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f` |
| Shell | `docker compose -f docker-compose.prod.yml exec backend bash` |
| DB Shell | `docker compose -f docker-compose.prod.yml exec postgres psql -U rlcoach` |

---

## Troubleshooting

**Container won't start:**
```bash
docker compose -f docker-compose.prod.yml logs <service>
```

**Database connection issues:**
```bash
docker compose -f docker-compose.prod.yml exec backend python -c "from rlcoach.db import engine; print(engine.url)"
```

**Worker not processing:**
```bash
docker compose -f docker-compose.prod.yml logs worker
docker compose -f docker-compose.prod.yml exec backend celery -A rlcoach.worker inspect active
```
