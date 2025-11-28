# Deployment Guide - Cloudflare Tunnel + Docker

This guide explains how to deploy the FastAPI backend using Docker with Cloudflare Tunnel.

## Prerequisites

- A server/VPS with Docker and Docker Compose installed
- A Cloudflare account with a domain
- GitHub repository with Actions enabled

## Setup Steps

### 1. Create Cloudflare Tunnel

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Access** → **Tunnels**
3. Click **Create a tunnel**
4. Name your tunnel (e.g., `amartha-backend`)
5. Copy the tunnel token (starts with `eyJ...`)

### 2. Configure Tunnel Public Hostname

In the Cloudflare dashboard, add a public hostname:
- **Subdomain**: `api` (or your choice)
- **Domain**: Your domain
- **Service**: `http://backend:8000`

### 3. Server Setup

On your server:

```bash
# Create app directory
mkdir -p /opt/amartha-backend
cd /opt/amartha-backend

# Create .env file
cat > .env << EOF
GEMINI_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_SERVICE_ROLE_KEY=your_key
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token
EOF

# Set permissions
chmod 600 .env
```

### 4. GitHub Secrets Configuration

Add these secrets to your GitHub repository (**Settings** → **Secrets and variables** → **Actions**):

| Secret | Description |
|--------|-------------|
| `SERVER_HOST` | Your server's IP or hostname |
| `SERVER_USER` | SSH username |
| `SERVER_SSH_KEY` | Private SSH key for authentication |
| `APP_PATH` | Path to app directory (e.g., `/opt/amartha-backend`) |

### 5. Deploy

**Option A: Manual Deploy with Docker Compose**

```bash
# On your server
cd /opt/amartha-backend

# Clone or copy files
git clone https://github.com/your-username/your-repo.git .

# Start services
docker-compose up -d

# View logs
docker-compose logs -f
```

**Option B: Automatic Deploy via CI/CD**

Push to the `main` branch and the GitHub Actions workflow will:
1. Run tests and linting
2. Build and push Docker image to GitHub Container Registry
3. SSH into your server and deploy the new image

## Useful Commands

```bash
# View running containers
docker ps

# View logs
docker-compose logs -f backend
docker-compose logs -f cloudflared

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Update and restart
docker-compose pull
docker-compose up -d
```

## Architecture

```
Internet → Cloudflare CDN → Cloudflare Tunnel → Docker (cloudflared) → Docker (backend:8000)
```

Benefits:
- No exposed ports on your server
- Free SSL/TLS from Cloudflare
- DDoS protection
- Cloudflare's global CDN

## Troubleshooting

**Tunnel not connecting:**
- Verify `CLOUDFLARE_TUNNEL_TOKEN` is correct
- Check cloudflared logs: `docker-compose logs cloudflared`

**Backend not responding:**
- Check backend logs: `docker-compose logs backend`
- Verify environment variables are set
- Test health endpoint: `curl http://localhost:8000/health`

**GitHub Actions failing:**
- Verify all secrets are configured
- Check SSH key has access to server
- Ensure Docker is running on server
