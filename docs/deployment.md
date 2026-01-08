# RLCoach Deployment Guide

This guide covers deploying RLCoach to production on Hetzner with Docker.

## Architecture Overview

```
                    ┌─────────────┐
                    │ Cloudflare  │
                    │    (CDN)    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Nginx     │
                    │  (Reverse   │
                    │   Proxy)    │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌───▼───┐ ┌──────▼──────┐
       │   Next.js   │ │FastAPI│ │   Celery    │
       │  Frontend   │ │  API  │ │   Worker    │
       └─────────────┘ └───┬───┘ └──────┬──────┘
                           │            │
              ┌────────────┼────────────┘
              │            │
       ┌──────▼──────┐ ┌───▼───┐
       │ PostgreSQL  │ │ Redis │
       └─────────────┘ └───────┘
```

## Prerequisites

- Hetzner Cloud account
- Domain name configured with Cloudflare
- Docker and Docker Compose installed
- SSH access to your server

## Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
```

Required variables:

```bash
# Database
DATABASE_URL=postgresql://rlcoach:password@postgres:5432/rlcoach

# Redis
REDIS_URL=redis://redis:6379

# Auth (from NextAuth)
NEXTAUTH_URL=https://rlcoach.gg
NEXTAUTH_SECRET=<generate with: openssl rand -base64 32>

# OAuth Providers
DISCORD_CLIENT_ID=<from Discord Developer Portal>
DISCORD_CLIENT_SECRET=<from Discord Developer Portal>
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...

# AI Coach
ANTHROPIC_API_KEY=sk-ant-...

# Environment
ENVIRONMENT=production
SAAS_MODE=true
CORS_ORIGINS=https://rlcoach.gg,https://www.rlcoach.gg
```

## Server Setup

### 1. Provision Server

Recommended: Hetzner CPX31 (4 vCPU, 8GB RAM)

```bash
# SSH into server
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Create non-root user
adduser rlcoach
usermod -aG docker rlcoach
```

### 2. Clone Repository

```bash
su - rlcoach
git clone https://github.com/yourusername/rlcoach.git
cd rlcoach
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env  # Edit with production values
```

### 4. Set Up SSL

Using Cloudflare Full (Strict) SSL:
1. Generate origin certificate in Cloudflare dashboard
2. Save as `/etc/ssl/rlcoach/origin.pem` and `/etc/ssl/rlcoach/origin-key.pem`

### 5. Deploy

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 6. Run Migrations

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Docker Compose (Production)

The production compose file includes:

- **nginx**: Reverse proxy with rate limiting
- **frontend**: Next.js production build
- **backend**: FastAPI with Gunicorn
- **worker**: Celery worker for background tasks
- **beat**: Celery beat for scheduled tasks
- **postgres**: PostgreSQL 15
- **redis**: Redis 7

## Scaling

### Horizontal Scaling

```bash
# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale worker=3

# Scale backend
docker compose -f docker-compose.prod.yml up -d --scale backend=2
```

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_replays_user_created
ON uploaded_replays(user_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_coach_messages_session
ON coach_messages(session_id, created_at);
```

## Monitoring

### Health Checks

```bash
# API health
curl https://api.rlcoach.gg/health

# Container status
docker compose -f docker-compose.prod.yml ps

# Logs
docker compose -f docker-compose.prod.yml logs -f backend
```

### Metrics

Prometheus metrics available at `/metrics` (internal only):

- `rlcoach_requests_total`
- `rlcoach_request_duration_seconds`
- `rlcoach_replays_processed_total`
- `rlcoach_coach_tokens_used_total`

## Backups

### Database Backup

```bash
# Manual backup
./scripts/backup.sh

# Automated backups (add to crontab)
0 3 * * * /home/rlcoach/rlcoach/scripts/backup.sh
```

Backups are stored in Backblaze B2.

### Restore

```bash
./scripts/restore.sh <backup-file>
```

## CI/CD

### GitHub Actions

The repository includes workflows for:

1. **CI (`.github/workflows/ci.yml`)**:
   - Run tests
   - Lint code
   - Build Docker images

2. **CD (`.github/workflows/deploy.yml`)**:
   - Build and push images
   - Deploy to production
   - Run migrations

### Manual Deployment

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Run migrations if needed
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Rollback

```bash
# Rollback to previous image
docker compose -f docker-compose.prod.yml pull --policy=never
docker compose -f docker-compose.prod.yml up -d

# Database rollback
docker compose -f docker-compose.prod.yml exec backend alembic downgrade -1
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs backend

# Check configuration
docker compose -f docker-compose.prod.yml config
```

### Database Connection Issues

```bash
# Test connection
docker compose -f docker-compose.prod.yml exec backend python -c \
  "from rlcoach.db.session import create_session; s = create_session(); print('OK')"
```

### Redis Connection Issues

```bash
# Test Redis
docker compose -f docker-compose.prod.yml exec redis redis-cli ping
```

### High Memory Usage

```bash
# Check container stats
docker stats

# Restart workers
docker compose -f docker-compose.prod.yml restart worker
```

## Security Checklist

- [ ] SSL/TLS configured (Cloudflare Full Strict)
- [ ] Database not exposed publicly
- [ ] Redis not exposed publicly
- [ ] Environment variables secured
- [ ] CORS origins restricted
- [ ] Rate limiting enabled
- [ ] Secrets rotated regularly
- [ ] Firewall configured (ports 80, 443 only)
- [ ] Backups tested
- [ ] Monitoring alerts configured

## Support

For deployment issues:
- Check GitHub Issues
- Email: devops@rlcoach.gg
