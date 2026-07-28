# 小影CMS · AI 驱动的全能建站系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.x-green)](https://djangoproject.com)
[![License](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)

集 **AI 页面生成、SEO 优化、蜘蛛监控、安全防护**于一体的现代化 CMS 管理平台，面向建站从业者提供全流程管理能力。

---

## 目录

- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [许可证](#许可证)
- [联系方式](#联系方式)

---

## 核心功能

### AI 智能生成
借助 DeepSeek API，通过自然语言描述即可生成高质量落地页或整站。内置提示词模板库，生成风格可控，支持在线编辑与实时预览。

### SEO 优化工具
- **域名快排追踪** — 以树形结构组织根域名与子域名，时间线视图批量管理收录与排名
- **爬虫斗篷伪装** — 智能区分搜索引擎爬虫与真人访客，差异分发内容
- **智能互链生成** — 自动在站内页面间建立交叉链接，提升权重传递效率
- **域名绑定** — 将域名与生成页面绑定，支持多域名映射与泛解析

### 蜘蛛监控分析
实时记录所有爬虫与真人的访问行为，支持按小时/天维度可视化展示蜘蛛活跃时段，分析搜索引擎爬虫占比趋势，可通过忽略路径过滤减少噪音数据。

### 权重页面管理
- 独立 Django 子项目管理，支持启动/停止/重启
- 每个项目拥有独立数据库（SQLite）
- 内置控制台实时查看运行日志
- 日志自动备份与下载
- 代理访问路径（`wp-proxy/`）可选公开或需登录

### 安全防护体系
- **IP 与路径黑名单防火墙** — 拦截恶意访问
- **静态文件白名单路由** — 限制可访问的静态资源
- **登录安全日志** — 记录所有登录尝试
- **操作审计日志** — 字段级操作记录，支持自动备份与恢复

### 操作体验
顶部多标签页导航支持右键菜单操作（关闭当前/关闭其他/关闭左右侧），仪表盘集成实时数据概览与入场动效，整体采用 LayUI 风格，界面整洁统一。

---

## 快速开始

### 环境要求
- Python 3.10+
- pip 包管理工具
- （可选）MySQL 8.0 — 默认使用 SQLite

### 部署步骤

```bash
# 1. 克隆项目
git clone https://github.com/DingZhiYingCloud/XiaoYingCMS.git
cd XiaoYingCMS

# 2. 初始化数据库迁移目录
# 在 XiaoYingAdmin 目录下创建 migrations 目录和 __init__.py 文件

# 3. 创建并激活 Python 虚拟环境
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 文件中的数据库与 API 密钥

# 6. 初始化数据库
python manage.py makemigrations
python manage.py migrate

# 7. 启动开发服务器（默认端口 8003）
python manage.py runserver 8003
```

### 访问后台

启动后访问 `http://127.0.0.1:8003/xiaoying_admin/login/` 进入后台登录页面。

默认账号密码：
- 账号：`xiaoyingadmin`
- 密码：`xiaoyingadmin`

> **注意**：如需使用 AI 生成能力，需在 `.env` 中配置有效的 `API_URL`，指向 DeepSeek 兼容的 API 服务。

---

## 配置说明

### 环境变量

项目核心配置通过 `.env` 文件管理，主要参数如下：

| 配置项 | 用途说明 | 默认值 |
|--------|----------|--------|
| `SECRET_KEY` | Django 安全密钥，生产环境务必更换 | — |
| `DEBUG` | 是否开启调试模式 | `True` |
| `ALLOWED_HOSTS` | 允许访问的域名列表 | `*` |
| `SITE_NAME` | 后台站点显示名称 | `小影CMS管理系统` |
| `API_URL` | 小影API地址（浏览器搜索"小影API"即可） | `http://127.0.0.1:8000` |
| `BACKUP_DIR` | 数据备份文件存储目录 | `backups` |
| `VERSION` | 系统版本号 | `1.0.0` |

### 功能模块配置

| 模块 | 配置方式 |
|------|----------|
| AI 页面生成 | 在 `.env` 中配置 `API_URL` 指向可用的 DeepSeek 兼容 API |
| 斗篷伪装 | 登录后台后，在「黑帽SEO → 斗篷伪装」页面配置规则 |
| 蜘蛛日志 | 自动启用，可在「蜘蛛管理 → 忽略路径」中过滤噪音 |
| 防火墙 | 在「安全防护 → 防火墙管理」中维护 IP/路径黑名单 |
| 域名绑定 | 中间件自动启用，在「页面管理」中配置域名与页面的映射关系 |

### 中间件处理链路

请求进入系统后依次经过以下中间件处理：

1. **FirewallMiddleware** — 拦截黑名单 IP 与路径
2. **SpiderLogMiddleware** — 记录爬虫与真人访问日志
3. **StatisticsCodeMiddleware** — 注入统计代码
4. **StaticFileServeMiddleware** — 白名单静态文件路由
5. **SeoCloakMiddleware** — 爬虫斗篷伪装分发
6. **DomainBindMiddleware** — 域名与页面绑定解析
7. **LoginRequiredMiddleware** — 后台登录鉴权
8. **OperationLogMiddleware** — 操作审计记录
9. **LayoutMiddleware** — 页面布局渲染

---

## 项目结构

```
XiaoYingCMS/
├── XiaoYingAdmin/           # 核心业务代码
│   ├── common/              # 通用工具库
│   │   ├── base.py          # 基础模型(BaseModel)
│   │   └── http.py          # HTTP 工具函数
│   ├── middleware/           # 中间件集合
│   │   ├── auth.py          # 登录鉴权
│   │   ├── firewall.py      # 防火墙
│   │   ├── spider_log.py    # 蜘蛛日志
│   │   ├── seo_cloak.py     # SEO 斗篷
│   │   ├── layout.py        # 页面布局
│   │   ├── operation_log.py # 操作审计
│   │   └── statistics_code.py # 统计代码
│   ├── models/              # 数据模型
│   │   ├── user.py          # 用户
│   │   ├── generated_page.py # 生成页面
│   │   ├── spider_log.py    # 蜘蛛访问日志
│   │   ├── firewall.py      # 防火墙规则
│   │   ├── site_settings.py # 网站设置
│   │   ├── weight_project.py # 权重项目
│   │   └── ...              # 其他模型
│   ├── views/               # 视图层
│   │   ├── request.py       # 通用视图
│   │   ├── seo/             # SEO 模块
│   │   ├── auth.py          # 认证
│   │   ├── weight_project.py # 权重项目管理
│   │   └── ...              # 其他视图
│   ├── templates/           # 前端模板
│   ├── static/              # 静态资源
│   └── utils/               # 工具函数
│       ├── backup.py        # 数据备份
│       └── export_import.py # 导入导出
├── XiaoYingCMS/             # Django 项目配置文件
│   ├── settings/
│   ├── urls.py
│   └── wsgi.py
├── .env                     # 环境变量
├── manage.py                # Django 管理入口
└── requirements.txt         # Python 依赖清单
```

---

## 技术栈

- **后端框架** — Django 5.x
- **数据库** — MySQL 8.0（推荐）/ SQLite（默认）
- **前端** — LayUI + FontAwesome 6
- **AI 推理** — DeepSeek API（兼容 OpenAI 格式）
- **运行环境** — Python 3.10+

---

## 许可证

本项目采用 MIT 许可证，详情请查阅 [LICENSE](LICENSE) 文件。

---

## 联系方式

- 微信：duyanbz
- Telegram：[@xiaoying1216](https://t.me/xiaoying1216)

---

*用心做好每一个站点 · 小影CMS*
