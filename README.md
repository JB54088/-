# 企业客户资产经营平台 V1

前后端分离的企业客户资产经营平台 Demo：Next.js + TypeScript + Tailwind CSS、FastAPI + SQLAlchemy、PostgreSQL。当前唯一数据入口是管理员上传 ABC Excel，系统不要求连接外部数据库或 Playwright 数据池。

## 一键启动

```bash
cd /Users/wzh/Desktop/观云春
cp .env.example .env
docker compose up --build
```

访问：

- 前端：http://localhost:3000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

同一局域网内的同事请访问运行 Docker 的这台电脑：`http://<当前局域网IP>:3000`（当前地址为 `http://192.168.50.80:3000`），也可以尝试局域网主机名 `http://wzhdeMac-mini.local:3000`。局域网 IP 可能因 Wi-Fi/DHCP 变化，请在运行 Docker 的电脑上执行 `ipconfig getifaddr en1` 或 `ipconfig getifaddr en0` 获取最新地址。前端 API 使用同源 `/api` 代理，不会请求同事电脑自己的 localhost。若无法打开，请确认双方连接同一 Wi-Fi，且不是访客 Wi-Fi、VPN 或开启了客户端隔离的网络。

阿里云 ECS 生产部署说明见 [`deploy/README.md`](deploy/README.md)。生产 Compose 与本机开发 Compose 分开：生产数据库不发布端口，Web 代理默认只监听本机回环地址，可按需启用临时 HTTPS Quick Tunnel。

首次启动会自动执行 Alembic 迁移，并确保 5 个系统账号、团队和基础客户标签配置存在；不会自动生成任何 Demo 客户、订单、报表或 Excel 导入记录。当前数据库清理后可直接上传真实 ABC Excel。

客户来源统一保存为 `source_category`，允许的 code 与中文名称为：`field_sales`（地推）、`online`（线上）、`offline`（线下）、`event`（活动）、`third_party_referral`（第三方转介绍）、`external`（外部来源）、`other`（其它）。旧 `source` 字段仍保留原始值，用于历史追溯，不参与业务筛选和统计。

## 重复报备处理

业务员提交客户线索时，后端按标准化手机号优先、微信号其次进行重复检测；姓名不会单独判重。手机号或微信号命中时不会创建第二个客户，而是写入 `duplicate_lead_reports`，业务员只会收到“该客户已存在，已提交管理员确认”的通用提示。管理员可从左侧“重复报备”进入处理：确认为重复会保留原客户，确认不是重复会创建新的待审核线索，驳回则只关闭本条重复报备记录。

报备接口支持 `submission_id`（也接受 `idempotency_key` 别名）。前端每次提交生成唯一值，后端数据库唯一索引和业务层检查共同保证网络重试或连续点击不会重复创建线索。手机号会去除空格、短横线并统一 `+86` / `0086` 格式。

## Demo 账号

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| admin01 | `Admin01@123` | 管理员 / 主管 |
| admin02 | `Admin02@123` | 管理员 / 主管 |
| sales01 | `Sales01@123` | 业务员 |
| sales02 | `Sales02@123` | 业务员 |
| sales03 | `Sales03@123` | 业务员 |

## 上线前清理 ABC 测试导入

`backend/scripts/cleanup_abc_test_data.py` 是仅供管理员/运维在容器内执行的一次性维护脚本，不提供 HTTP 清理接口。默认只输出预览，不修改数据库：

```bash
docker compose exec backend python scripts/cleanup_abc_test_data.py
```

确认预览范围并完成 PostgreSQL 备份后，显式增加 `--apply` 才会在单个数据库事务中清理 ABC 导入批次、导入交易、明细、待匹配记录、关联储值流水和报告快照。脚本保留人工报备客户、账号、标签配置和来源配置；只有无报备人、无归属且没有人工业务引用的 ABC 临时客户才会删除。无法确认的客户会保留并在预览中列出 ID。

如需建立不含任何客户业务档案的全新演示/上线状态，可使用 `backend/scripts/reset_customer_business_data.py`。该脚本默认只预览，确认 PostgreSQL 备份及删除范围后才显式传入 `--apply`；会清空客户、客户历史、消费/导入记录、重复报备、报告和 AI 查询日志，同时保留用户、部门、客户标签定义、来源配置及数据库结构。

## 业务员修改显示姓名

业务员可在“我的”页面修改自己的显示姓名。登录账号、角色和权限不会由此接口修改。后端接口为 `PATCH /api/auth/me/profile`，请求体只接受 `display_name`；显示姓名通过 `users.full_name` 保存，其他客户、归属历史、看板和报告页面仍按用户 ID 读取当前姓名。

## 数据链路

```text
ABC 平台导出 Excel → 管理员上传并预览 → FastAPI 解析/匹配/幂等导入 → PostgreSQL → Next.js
```

本项目不包含 Playwright 爬虫，也不暴露 ABC Webhook、ABC 客户 POST、ABC 订单 POST 或数据池实时同步接口。旧的 `backend/app/integrations/data_pool/` 代码和历史迁移保留为兼容文件，但不再被应用路由和前端调用。

## ABC Excel 导入

管理员在左侧“ABC Excel 导入”或 Dashboard 的“上传 ABC Excel”进入导入页：

```text
POST /api/excel-imports/abc/preview
POST /api/excel-imports/abc/{batch_id}/confirm
GET  /api/excel-imports/abc/history
GET  /api/excel-imports/abc/unmatched
POST /api/excel-imports/abc/unmatched/{record_id}/bind
POST /api/excel-imports/abc/unmatched/{record_id}/ignore
```

支持 `.xlsx` 和 `.xls`，默认单文件不超过 20MB、最多 50000 行。解析支持流水、分类、明细等 Sheet；可选 Sheet 缺失不会让整个文件失败。上传后必须先预览，再由管理员确认写入数据库。

客户匹配优先使用患者档案号/患者 ID（`external_customer_id`），其次使用标准化手机号；姓名不会作为唯一自动匹配条件。没有匹配或手机号命中多个客户的交易会进入待匹配列表，不会创建未归属的正式客户，也不会随机分配业务员。绑定待匹配记录时会继续导入其历史交易。

消费交易优先使用收费单号/结算单号/交易流水号等稳定外部交易 ID 去重；没有稳定交易号时使用患者身份、就诊号、收费时间、支付方式和实收金额生成指纹。重复上传只会 update/skip，不会重复生成订单。Excel 原始行、解析错误、支付金额不一致和批次统计均保留在 PostgreSQL。

外部 Excel 数据只更新客户外部资料、订单和消费快照，绝不覆盖 `reported_by`、`assigned_to`、来源归档分类、客户标签、客户状态、管理员备注或归属历史。支付金额保存为 `total_amount`、`insurance_amount`、`self_pay_amount`；不做医保/自费比例估算，金额不一致会写入 `integration_logs` 的 `payment_amount_mismatch`。

消费金额保存为 `total_amount`、`insurance_amount`、`self_pay_amount`。如果 ABC Excel 直接提供三项金额，系统原样导入；如果只提供订单/明细支付类型，则按 `insurance` 和 `self_pay` 归类。没有足够外部事实时，医保和自费字段保持空值，不做比例估算。每笔订单的 `payment_split_status` 为 `verified`、`unknown` 或 `mismatch`；金额不一致会保留原始数据并额外写入 `integration_logs` 的 `payment_amount_mismatch` 事件。

## 权限规则

- `admin` 可以查看全部客户、订单、同步日志和经营数据，审核线索、维护标签、调整当前归属、查看周报/月报。
- `salesperson` 只能查看 `customers.assigned_to = 当前用户` 的客户和消费记录，可以提交线索和查看个人 Dashboard。
- 客户详情、订单列表、订单导出、Dashboard 和报告接口均由 FastAPI 后端执行权限过滤；修改 URL 或 customer_id 不会绕过权限。
- `reported_by` 是首次线索报备人，永不因重新分配改变；`assigned_to` 是当前实际负责业务员。

## 数据库迁移

后端启动时自动执行：

```bash
alembic upgrade head
```

也可以手动执行：

```bash
docker compose exec backend alembic upgrade head
```

历史字段迁移依次位于 `backend/alembic/versions/003_data_pool_sync.py` 至 `008_payment_split.py`；本次 Excel 导入字段、批次和待匹配记录迁移位于 `backend/alembic/versions/009_excel_import.py`。来源迁移会把可识别的旧来源映射到七类，无法判断的值归为 `other`，并保留原 `source` 原始值。008 迁移只把历史 `amount` 复制为 `total_amount`，不会为历史订单虚构医保/自费金额。

## 保留的接口

- `POST /api/auth/login`
- `GET /api/dashboard`
- `GET/POST /api/leads`
- `GET /api/duplicate-reports`（管理员查看重复报备）
- `POST /api/duplicate-reports/{report_id}/review`（管理员确认重复 / 确认不是重复 / 驳回）
- `GET /api/customers`、`GET /api/customers/{customer_id}`
- `PATCH /api/customers/{customer_id}/assignment`
- `PUT /api/customers/{customer_id}/tags`
- `GET/POST/PATCH/DELETE /api/tags`
- `GET /api/orders`、`GET /api/orders/export`
- `GET /api/reports`（管理员）
- `POST /api/excel-imports/abc/preview`、`POST /api/excel-imports/abc/{batch_id}/confirm`（管理员）
- `GET /api/excel-imports/abc/history`、`GET /api/excel-imports/abc/unmatched`（管理员）

企业微信适配层仍预留在 `backend/app/integration/wecom_service.py`，但当前未接入真实 OAuth。
