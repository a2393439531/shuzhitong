# 数治通 · 数据治理与智能问数一体化平台

![四期·全部完工](https://img.shields.io/badge/阶段-四期·全部完工-brightgreen) ![后端-FastAPI](https://img.shields.io/badge/后端-FastAPI-009688) ![数据库-SQLite](https://img.shields.io/badge/数据库-SQLite-003B57) ![前端-Vue3](https://img.shields.io/badge/前端-Vue3-42b883) ![UI-Element_Plus](https://img.shields.io/badge/UI-Element_Plus-409EFF) ![图表-ECharts](https://img.shields.io/badge/图表-ECharts-AA344D) ![许可证-MIT](https://img.shields.io/badge/许可证-MIT-green)

**一句话介绍：** 数治通是面向企事业单位的数据治理与智能问数一体化平台——先把数据的"家底"盘清楚（业务对象、数据目录、数据标准、认责矩阵、审批流程），再让业务人员用自然语言问数、用数据做决策。

---

## 总体功能矩阵（四期全部完工）

| 阶段 | 模块 | 一句话说明 | 设计文档 |
|---|---|---|---|
| 一期·治理基础 | 业务对象管理 | 领域/能力/流程/对象梳理，"业务对象卡"+流程节点数据挂载 | [一期产品设计](docs/一期产品设计.md) |
| 一期·治理基础 | 数据资源目录 | 业务/技术双视图；登记→发布状态机；下架依赖检查 | [一期产品设计](docs/一期产品设计.md) |
| 一期·治理基础 | 数据标准管理 | 五类标准+版本；系统落标情况可查 | [一期产品设计](docs/一期产品设计.md) |
| 一期·治理基础 | 数据认责与流程管理 | "字段—流程—责任"矩阵；任职有效期与代理；质量问题派发 | [一期产品设计](docs/一期产品设计.md) |
| 一期·治理基础 | 审批流程 | 标准/目录/认责三类审批；统一待办 | [一期产品设计](docs/一期产品设计.md) |
| 二期·治理执行 | 主数据管理 | 申请→审核→统一编码→分发；三码关系带有效时间 | — |
| 二期·治理执行 | 字段映射 | 源系统字段↔标准↔主数据属性三方映射 | — |
| 二期·治理执行 | 质量规则引擎 | 六类规则可配置；手动/定时执行 | — |
| 二期·治理执行 | 落标检查 | 标准符合性检查；差异清单 | — |
| 二期·治理执行 | 整改闭环 | 发现→派发→整改→重检→复核关闭 | — |
| 三期·服务应用 | 统一数据服务 | 服务发布/订阅/授权/调用/通知 | — |
| 三期·服务应用 | 指标标准管理 | 统一口径+版本；计算/趋势/版本对比 | — |
| 三期·服务应用 | 智能问数 | 中文问数→口径→图表+五要素回答 | — |
| 四期·推广运营 | 多基地配置 | 基地档案；共性/差异两层；有效口径查询 | [四期产品设计](docs/四期产品设计.md) |
| 四期·推广运营 | 变更中心 | 影响分析→责任人确认→生效通知→回退 | [四期产品设计](docs/四期产品设计.md) |
| 四期·推广运营 | 运营评价 | 运营大盘（治理/质量/服务/问数/变更）；审计聚合 | [四期产品设计](docs/四期产品设计.md) |

**试点领域：** 核电"设备—维修工单—备件"链路贯穿四期。种子数据覆盖：设备三码关系（带有效时间）、辅助给水泵、维修工单、备件物料、「设备核安全分级」标准、BASE-A/B 双基地差异。

> 环境搭建与启动见 [docs/实施步骤.md](docs/实施步骤.md)。全栈可配置（服务器/数据库/大模型）见下方「配置指南」。

---

## 快速启动

### 方式一：本地启动

```bash
# 后端（FastAPI + SQLite）
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（Vue3 + Element Plus）
cd frontend
npm install
npm run dev
```

- 前端：http://localhost:8080
- 后端 API：http://localhost:8000（接口文档：http://localhost:8000/docs）

### 方式二：Docker Compose 一键启动

```bash
docker compose up --build -d
```

- 前端：http://localhost:8080
- 后端 API：http://localhost:8000

环境要求：Python 3.12、Node 20。完整步骤与常见问题见 [docs/实施步骤.md](docs/实施步骤.md)。

> 换服务器 / 换数据库 / 换大模型都不用改代码：复制 `.env.example` 为 `.env` 后修改对应项即可，详见下方「配置指南」。


---

## 配置指南

所有配置都走**环境变量**（或项目根 `.env` 文件），改配置不改代码。
复制模板后按需修改：`cp .env.example .env`。

### Server

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SZT_HOST` | `0.0.0.0` | 后端监听地址 |
| `SZT_PORT` | `8000` | 后端监听端口 |
| `SZT_WORKERS` | `1` | uvicorn worker 数 |
| `SZT_CORS_ORIGINS` | `*` | 允许跨域的前端地址，逗号分隔 |
| `SZT_LOG_LEVEL` | `info` | 日志级别 |

### Database

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SZT_DB_URL` | （空） | 为空用 SQLite；PostgreSQL 示例 `postgresql://szt:szt123@shuzhitong-db:5432/shuzhitong` |
| `SZT_DATA_DIR` | （空） | SQLite 数据目录，为空则用 `<项目根>/backend/data` |

> PostgreSQL 一键启动：`.env` 中设置 `SZT_DB_URL` 指向上方示例，再执行
> `docker compose --profile pg up -d --build`（会自动拉起 `shuzhitong-db` 容器）。
> 启动时控制台会打印实际使用的数据库类型（密码脱敏）。

### LLM（大模型，三期智能问数用）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SZT_LLM_PROVIDER` | `disabled` | `deepseek` \| `qwen` \| `openai_compatible` \| `disabled` |
| `SZT_LLM_BASE_URL` | （空） | 接口地址（deepseek/qwen 有默认值；openai_compatible 必填） |
| `SZT_LLM_API_KEY` | （空） | API Key，妥善保管 |
| `SZT_LLM_MODEL` | （空） | 模型名（deepseek/qwen 有默认值） |
| `SZT_LLM_TIMEOUT` | `60` | 调用超时（秒） |

> 未配置或调用失败时自动降级为本地规则并返回明确原因，不影响其他功能。
> 当前生效状态可在前端「系统配置」页查看（管理员可见）。

### Auth

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SZT_JWT_SECRET` | `dev-insecure-secret-change-me` | JWT 签名密钥，**生产必须更换**（用默认值启动会有 WARNING） |
| `SZT_TOKEN_EXPIRE_MINUTES` | `720` | token 有效期（分钟） |

### 其他

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SZT_SEED_DEMO_DATA` | `true` | 是否灌入演示数据；生产建议 `false` |
| `SZT_API_BASE` | `/api` | 前端 API 基地址（docker 容器环境变量；分离部署填绝对地址） |
| `SZT_API_UPSTREAM` | `http://shuzhitong-api:8000` | 前端 nginx 反代后端目标（docker 容器环境变量） |

> 敏感配置（JWT 密钥、LLM Key、数据库密码）不会出现在日志与任何前端接口中。

---

## 演示账号

| 用户名 | 密码 | 角色 | 权限说明 |
|---|---|---|---|
| `admin` | `Admin@123` | super_admin | 超级管理员，全部权限 |
| `heping` | `Heping@123` | admin | 管理员，发布类操作需走审批 |
| `weixiu` | `Weixiu@123` | operator | 操作员，可登记目录、处理派给自己的质量问题 |
| `audit` | `Audit@123` | readonly | 只读，可查看已发布资产 |

> 演示账号仅用于联调与验收演示，生产部署前请删除或重置密码。

---

## 目录结构

```
shuzhitong/
├── README.md                 # 本文件
├── LICENSE                   # MIT 许可证
├── .gitignore
├── docker-compose.yml        # 一键启动：api + web
├── docs/
│   ├── 一期产品设计.md        # 定位、五大模块、对象卡/状态机/标准/认责/审批、权限矩阵、IA、验收标准
│   └── 实施步骤.md            # 环境、启动、测试、Docker、常见问题
├── backend/                  # FastAPI + SQLite 后端（API 前缀 /api，端口 8000）
│   ├── app/
│   ├── requirements.txt
│   └── data/                 # SQLite 数据文件（git 忽略）
├── frontend/                 # Vue3 + Element Plus + ECharts 前端（dev/容器端口 8080）
│   ├── src/
│   └── package.json
└── data/                     # Docker 数据卷挂载目录（SQLite 持久化，git 忽略）
```

---

## API 概览（前缀 `/api`）

| 方法 | 端点 | 说明 | 主要角色 |
|---|---|---|---|
| POST | `/api/auth/login` | 用户登录，返回 JWT | 全部 |
| GET/POST | `/api/objects` | 业务对象卡列表/新增 | admin+ |
| GET | `/api/objects/{id}` | 对象卡详情（含关联目录/标准/责任/服务/指标） | 全部 |
| GET/POST | `/api/catalog` | 数据目录列表/登记 | operator+ |
| PUT | `/api/catalog/{id}/submit` | 提交发布（进入状态机） | operator+ |
| POST | `/api/catalog/{id}/offline` | 下架（含依赖检查） | admin+ |
| GET/POST | `/api/standards` | 数据标准列表/新增 | admin+ |
| GET | `/api/standards/{code}/compliance` | 标准落标情况（已落标/有差异/未接入） | 全部 |
| GET/PUT | `/api/responsibility/matrix` | 认责矩阵查询/配置 | admin+ |
| POST | `/api/approvals` | 发起审批（标准发布/目录发布/认责确认） | operator+ |
| GET | `/api/approvals/todo` | 待办列表（待我审批/我发起的/我已审批） | 全部 |
| POST | `/api/approvals/{id}/decide` | 审批决定（同意/退回/撤回） | 审批人 |
| GET | `/api/audit-logs` | 审计日志查询 | admin+ |

> 端点为一期约定的主要接口，具体以 `http://localhost:8000/docs` 的 Swagger 文档为准。

---

## 四期规划

| 阶段 | 主题 | 内容概要 | 状态 |
|---|---|---|---|
| 一期 | 治理基础 | 业务对象、数据目录、数据标准、认责矩阵、审批流程 | ✅ 已完成 |
| 二期 | 治理执行 | 主数据管理、字段映射、质量规则引擎、落标检查、整改闭环；全栈可配置化 | ✅ 已完成 |
| 三期 | 服务应用 | 统一数据服务（6 类服务/申请授权/限流/监测）、指标标准管理与计算引擎（版本化口径）、智能问数（五要素回答） | ✅ 已完成（详见 `docs/三期产品设计.md`） |
| 四期 | 推广运营 | 多基地配置、变更影响分析、运营评价 | 📋 规划中 |

### 与 askdata 的关系

- **askdata**（GitHub：`a2393439531/askdata`）是已独立发布运行的"智能问数"模块（自然语言→SQL→图表+解读）。
- 它是**第三期**的数据应用工作台集成对象：三期启动时，askdata 作为"智能问数"能力接入数治通，复用一期沉淀的业务对象、数据目录与数据标准作为问数的语义层。
- **本期（一期）不动 askdata**：不改它的代码、不迁它的仓库，两者通过规划文档保持对齐即可。

---

## 后续计划

- [x] 一期：治理基础五大模块 + 试点链路验收
- [x] 二期：主数据/字段映射/质量规则/落标检查/整改闭环 + 全栈可配置化
- [x] 三期：统一数据服务 + 指标计算引擎 + 智能问数（pytest 113/113，前端 build 通过）
- [ ] 四期启动：多基地配置、变更影响分析、运营评价

---

## 许可证

MIT License，详见 [LICENSE](LICENSE)。Copyright (c) 2026 shuzhitong contributors。
