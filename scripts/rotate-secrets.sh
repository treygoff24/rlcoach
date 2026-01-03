#!/bin/bash
# Secret rotation script for rlcoach
# Run quarterly or on suspected compromise

set -euo pipefail

echo "=== rlcoach Secret Rotation Script ==="
echo "This script helps you rotate secrets safely."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Run from project root directory"
    exit 1
fi

# Backup current .env
BACKUP_FILE=".env.backup.$(date +%Y%m%d_%H%M%S)"
cp .env "$BACKUP_FILE"
echo -e "${GREEN}Backed up current .env to $BACKUP_FILE${NC}"

echo ""
echo "=== Secrets to Rotate ==="
echo ""

# 1. NEXTAUTH_SECRET
echo -e "${YELLOW}1. NEXTAUTH_SECRET${NC}"
NEW_NEXTAUTH_SECRET=$(openssl rand -base64 32)
echo "   New value: $NEW_NEXTAUTH_SECRET"
echo "   Action: Update NEXTAUTH_SECRET in .env"
echo "   Impact: All users will be logged out"
echo ""

# 2. Database Password
echo -e "${YELLOW}2. POSTGRES_PASSWORD${NC}"
NEW_DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/' | head -c 32)
echo "   New value: $NEW_DB_PASSWORD"
echo "   Action:"
echo "   1. Connect to PostgreSQL: docker exec -it rlcoach-postgres psql -U rlcoach"
echo "   2. Run: ALTER USER rlcoach WITH PASSWORD 'NEW_PASSWORD';"
echo "   3. Update POSTGRES_PASSWORD and DATABASE_URL in .env"
echo "   4. Restart all services"
echo ""

# 3. Stripe Webhook Secret
echo -e "${YELLOW}3. STRIPE_WEBHOOK_SECRET${NC}"
echo "   Action:"
echo "   1. Go to Stripe Dashboard > Webhooks"
echo "   2. Delete old webhook endpoint"
echo "   3. Create new webhook endpoint"
echo "   4. Copy new webhook secret to .env"
echo ""

# 4. API Keys (manual rotation)
echo -e "${YELLOW}4. API Keys (manual rotation required)${NC}"
echo "   - ANTHROPIC_API_KEY: Generate new key at console.anthropic.com"
echo "   - DISCORD_CLIENT_SECRET: Regenerate at discord.com/developers"
echo "   - GOOGLE_CLIENT_SECRET: Regenerate at console.cloud.google.com"
echo "   - BACKBLAZE keys: Generate new keys at backblaze.com"
echo ""

# 5. Deployment steps
echo "=== Post-Rotation Steps ==="
echo ""
echo "1. Update .env with new values"
echo "2. Update secrets in deployment environment:"
echo "   - GitHub Secrets (for CI/CD)"
echo "   - Server environment"
echo ""
echo "3. Restart services:"
echo "   docker compose down"
echo "   docker compose up -d"
echo ""
echo "4. Verify services are healthy:"
echo "   docker compose ps"
echo "   curl https://rlcoach.gg/health"
echo ""
echo "5. Update SECRETS_LAST_ROTATED in .env"
echo ""
echo "6. Delete old backup after verification:"
echo "   rm $BACKUP_FILE"
echo ""

# Update rotation date
echo "=== Updating Rotation Date ==="
TODAY=$(date +%Y-%m-%d)
if grep -q "SECRETS_LAST_ROTATED" .env 2>/dev/null; then
    sed -i.bak "s/SECRETS_LAST_ROTATED=.*/SECRETS_LAST_ROTATED=$TODAY/" .env
    rm -f .env.bak
else
    echo "SECRETS_LAST_ROTATED=$TODAY" >> .env
fi
echo -e "${GREEN}Updated SECRETS_LAST_ROTATED to $TODAY${NC}"

echo ""
echo -e "${GREEN}Secret rotation preparation complete!${NC}"
echo "Follow the steps above to complete rotation."
