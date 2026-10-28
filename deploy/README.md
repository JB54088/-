# Alibaba Cloud ECS deployment

Production Compose keeps PostgreSQL, FastAPI, Next.js, and Nginx on the private Compose network. Nginx binds only to `127.0.0.1:8080`; PostgreSQL, FastAPI, and Next.js have no host ports. Do not open ports 3000, 5432, or 8000 in the ECS security group. The optional Quick Tunnel profile offers a temporary HTTPS entry without opening inbound security-group ports.

## Host preparation

Use Alibaba Cloud Linux 3 x86_64 with Docker Engine and the Docker Compose plugin installed. The ECS security group should allow SSH only from a trusted source address, and HTTP/HTTPS only when intentionally enabled. A 2 GiB instance needs swap for image builds; provide at least 4 GiB swap and keep several GiB free on the system disk.

## First deployment

```bash
git clone https://github.com/JB54088/-.git /opt/customer-assets
cd /opt/customer-assets
bash deploy/init-production-env.sh
```

The script prompts for five unique initial account passwords without echoing them, generates separate database/JWT secrets, and writes `deploy/production.env` with mode 600. The seed process uses account passwords only when creating missing users. Keep the env file private. Set the origin to `http://127.0.0.1:8080` for loopback-only verification; for a temporary Quick Tunnel set it to the generated HTTPS origin, and for a customer demonstration use a domain with HTTPS.

Start in a memory-conscious, serialized build:

```bash
cd /opt/customer-assets
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file deploy/production.env -f docker-compose.production.yml up -d --build
docker compose --env-file deploy/production.env -f docker-compose.production.yml ps
curl -fsS http://127.0.0.1:8080/health
```

If ECS cannot reach Docker Hub, build the production images on a workstation for
`linux/amd64`, transfer and load them on ECS, then start Compose with the
`deploy/compose.production.ecs-amd64.yml` overlay using `--no-build --pull
never`. The overlay only changes image tags; database, app networking, health
checks, and the loopback-only Nginx binding stay the same.

The backend runs Alembic migrations and ensures the five application accounts, departments, and built-in customer tags on startup. It does not create demo customers or transactions. Production account passwords are supplied via the five `INITIAL_*_PASSWORD` variables and are not stored in the repository.

To start a temporary HTTPS Quick Tunnel without exposing inbound host ports:

```bash
docker compose --profile quick-tunnel --env-file deploy/production.env -f docker-compose.production.yml up -d cloudflared
docker compose --env-file deploy/production.env -f docker-compose.production.yml logs cloudflared
```

Use the `https://*.trycloudflare.com` URL shown in the cloudflared logs. Quick Tunnel URLs are temporary and may change if the tunnel is recreated; the service restarts automatically with Docker, but a changed URL must be read from the logs.

## Updates and recovery

```bash
cd /opt/customer-assets
git pull --ff-only
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file deploy/production.env -f docker-compose.production.yml up -d --build
docker compose --env-file deploy/production.env -f docker-compose.production.yml logs --tail=100
```

Back up before upgrades or data changes:

```bash
docker compose --env-file deploy/production.env -f docker-compose.production.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > /opt/customer-assets-backup-$(date +%Y%m%d-%H%M%S).dump
```

The Compose volume `customer-assets_postgres_data` persists database data across container recreation. Do not run `docker compose down -v` on a live system.

## HTTPS

The proxy itself uses HTTP on a loopback-only host port. For temporary demo HTTPS, use the Quick Tunnel profile. A fixed HTTPS deployment needs a domain and named tunnel or an HTTPS reverse proxy; then update `APP_ORIGIN` to that HTTPS origin. PostgreSQL remains unexposed.
