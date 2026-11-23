# 阿里云 ECS + RDS + OSS 生产部署指南

生产环境（[`docker-compose.production.yml`](../docker-compose.production.yml)）采用**计算与存储分离**架构：
- **计算与入口层（ECS）**：私有 Compose 网络内仅运行 `backend`（FastAPI）、`frontend`（Next.js）和 `proxy`（Nginx）。Compose 内的 Nginx 默认绑定宿主机回环地址 `127.0.0.1:8080`（可用 `APP_PROXY_PORT` 调整），`backend`（8000）与 `frontend`（3000）不暴露宿主机端口。
- **关系型数据库层（阿里云 RDS PostgreSQL）**：不再启动本地数据库容器，后端通过内网直连阿里云 RDS，启动时自动执行 Alembic 数据库迁移与基础字典初始化。
- **原文件归档层（阿里云 OSS）**：管理员在工作台上传 ABC Excel 时，原始 `.xlsx` / `.xls` 文件即刻归档至阿里云私有 OSS Bucket，并在导入预览与导入历史页支持通过短效签名链接下载原文件。

---

## 1. 环境准备与网络连通要求

1. **ECS 实例**：建议使用 Alibaba Cloud Linux 3 x86_64，安装 Docker Engine 与 Docker Compose 插件；2 GiB 内存机型构建镜像前建议配置至少 4 GiB Swap。
2. **RDS 白名单与账号**：确保 ECS 内网 IP 已加入阿里云 RDS PostgreSQL 白名单，且已创建目标数据库（如 `customer_assets`）。若从旧环境迁移，请先将历史备份恢复至 RDS，再启动新后端（同时保留原有的 `JWT_SECRET_KEY`）。
3. **RDS SSL 根证书（可选）**：若 RDS 开启了强制 SSL 证书校验并配置了 `ALIYUN_RDS_CA_FILE`，请将证书文件（如 `ApsaraDB-CA-Chain.pem`）放入项目 `deploy/certs/` 目录（该目录已只读挂载至容器 `/app/certs/`，系统会自动按文件名匹配加载）。
4. **OSS Bucket**：保持 Bucket 为**私有读写**即可（无需开启公共读，也无需配置复杂 CORS，下载采用带 `response-content-disposition` 的公网短效签名链接）。若 ECS 与 OSS 位于同一地域（如 `cn-beijing`），可在生产环境中开启 `OSS_INTERNAL=true`，使后端上传走阿里云内网免流量通道，而浏览器下载链接仍自动走公网域名。

---

## 2. 环境变量配置

生产环境统一使用项目根目录的 `.env`。该文件包含数据库密码、JWT 密钥和 OSS 密钥，不要提交到 Git。已有部署迁移时，将原环境文件复制或移动为根目录 `.env`，保留原有 `JWT_SECRET_KEY`；不要为了改文件名重新生成密钥。首次部署且没有现成环境文件时，才运行交互脚本：

```bash
# 已有根目录 .env 时，只需确保权限安全
chmod 600 .env

# 首次部署且根目录 .env 不存在时，生成配置
bash deploy/init-production-env.sh
```

支持的阿里云配置项（后端会自动对 `ALIYUN_RDS_PWD` 中的特殊字符做 URL 编码组装连接串，也兼容显式传入完整的非本地 `DATABASE_URL`）：

```env
# 站点来源与密钥
JWT_SECRET_KEY=<高强度随机密钥，迁移旧库时保留原值>
APP_ORIGIN=https://your-domain.example.com
APP_PROXY_PORT=8080

# Aliyun ECS / OSS
ALIYUN_ECS_ADDR=xxxx
OSS_BUCKET_NAME=xxxx
ALIYUN_ACCESS_KEY_ID=xxxx
ALIYUN_ACCESS_KEY=xxxxx
ALIYUN_OSS_REGION=oss-cn-beijing
OSS_INTERNAL=true

# Aliyun RDS PostgreSQL (二选一：填写以下字段，或直接填写远程 DATABASE_URL)
ALIYUN_RDS_DB_NAME=customer_assets
ALIYUN_RDS_URL=pgm-xxxx.pg.rds.aliyuncs.com
ALIYUN_RDS_USERNAME=xxxx
ALIYUN_RDS_PWD=xxxx
ALIYUN_RDS_PORT=5432
ALIYUN_RDS_CA_FILE=/app/certs/ApsaraDB-CA-Chain.pem
```

---

## 3. 启动与离线镜像部署

### 在线构建启动

```bash
cd /opt/customer-assets
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file .env -f docker-compose.production.yml up -d --build
docker compose --env-file .env -f docker-compose.production.yml ps
curl -fsS http://127.0.0.1:8080/health
```

`APP_PROXY_PORT` 默认为 `8080`，只绑定 ECS 本机回环地址。宿主机已有 Nginx 监听 `80/443` 通常不会与它冲突；给新域名增加一个虚拟主机，并反向代理到 `127.0.0.1:8080` 即可。如果宿主机上确实已有进程占用 `8080`，在 `.env` 中设置空闲端口（例如 `APP_PROXY_PORT=18080`），并让新虚拟主机代理到 `127.0.0.1:18080`。不要覆盖现有应用的 Nginx 配置。

本机健康检查默认使用 `http://127.0.0.1:8080/health`；设置了其他 `APP_PROXY_PORT` 时，将检查地址中的端口替换为该值。

### ECS 无法访问 Docker Hub 时的离线镜像启动

在本地工作站针对 `linux/amd64` 构建镜像并导出上传至 ECS `docker load` 后，叠加 [`deploy/compose.production.ecs-amd64.yml`](../deploy/compose.production.ecs-amd64.yml)（该覆盖文件已移除本地 `db` 服务）：

```bash
docker compose --env-file .env \
  -f docker-compose.production.yml \
  -f deploy/compose.production.ecs-amd64.yml \
  up -d --no-build --pull never
```

### 按需启用临时 HTTPS Quick Tunnel（无需开放安全组入站端口）

```bash
docker compose --profile quick-tunnel --env-file .env -f docker-compose.production.yml up -d cloudflared
docker compose --env-file .env -f docker-compose.production.yml logs cloudflared
```

---

## 4. 升级、RDS 备份与恢复说明

改用阿里云 RDS 与 OSS 后，数据库与上传原表均持久化在托管云服务中：

1. **RDS 自动备份与快照（推荐）**：
   - 在阿里云 **RDS 控制台 → 备份恢复** 中开启每日自动物理备份与日志备份（支持按时间点恢复 PITR）；每次执行业务升级或数据清理脚本前，可在控制台手动创建一份临时备份。
2. **逻辑导出备份（可选，从 ECS 内网执行 `pg_dump`）**：
   ```bash
   PGPASSWORD="$ALIYUN_RDS_PWD" pg_dump \
     -h "$ALIYUN_RDS_URL" -p "${ALIYUN_RDS_PORT:-5432}" \
     -U "$ALIYUN_RDS_USERNAME" -d "$ALIYUN_RDS_DB_NAME" \
     -Fc > /opt/customer-assets-rds-$(date +%Y%m%d-%H%M%S).dump
   ```
3. **常规代码更新发布**：
   ```bash
   cd /opt/customer-assets
   git pull --ff-only
   COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file .env -f docker-compose.production.yml up -d --build
   docker compose --env-file .env -f docker-compose.production.yml logs --tail=100 backend
   ```
