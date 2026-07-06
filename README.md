# 小影CMS · AI 驱动的全能建站系统

![小影CMS 仪表盘](https://xiaoyingapi.com/media/uploads/files/a4fd4e23_20260706134423.png)

集 AI 页面生成、SEO 优化、蜘蛛监控、安全防护于一体的现代化 CMS 管理平台

[功能特性](#功能特性) · [界面预览](#界面预览) · [快速开始](#快速开始) · [配置说明](#配置说明)

**Python 3.10+** · **Django 5.x** · **MIT 许可证** · 稳定版

***

小影CMS 是一套面向建站从业者的全流程管理平台。核心能力覆盖从 AI 建站、SEO 快排、蜘蛛监控到安全防护的完整链路，帮助用户在一个后台完成网站管理的大部分日常工作。

***

## 功能特性

**AI 智能生成** — 借助 DeepSeek API，通过自然语言描述即可生成高质量落地页或整站。内置提示词模板库，生成风格可控，支持在线编辑与实时预览。

**SEO 优化工具** — 提供域名快排时间线追踪，以树形结构组织根域名与子域名，方便批量管理。爬虫斗篷伪装能智能区分搜索引擎爬虫与真人访客，差异分发内容。智能互链生成功能自动在站内页面间建立交叉链接，提升权重传递效率。

**蜘蛛监控分析** — 实时记录所有爬虫与真人的访问行为，支持按小时/天维度可视化展示蜘蛛活跃时段，分析搜索引擎爬虫占比趋势，并可通过忽略路径过滤减少噪音数据。

**安全防护体系** — 包含 IP 与页面路径黑名单防火墙、静态文件白名单路由、登录安全日志、字段级操作审计日志，全方位保障站点安全。

**操作体验** — 顶部多标签页导航支持右键菜单操作（关闭当前/关闭其他/关闭左右侧），仪表盘集成实时数据概览与入场动效，整体采用 LayUI 风格，界面整洁统一。

***

## 界面预览

|                                       仪表盘                                       |                                   域名 SEO 树形管理                                   |
| :-----------------------------------------------------------------------------: | :-----------------------------------------------------------------------------: |
| ![仪表盘](https://xiaoyingapi.com/media/uploads/files/a4fd4e23_20260706134423.png) | ![域名树](https://xiaoyingapi.com/media/uploads/files/2ac94435_20260706134424.png) |

|                                      快排时间线                                      |                                     多页面项目管理                                     |
| :-----------------------------------------------------------------------------: | :-----------------------------------------------------------------------------: |
| ![时间线](https://xiaoyingapi.com/media/uploads/files/a0ae616a_20260706134425.png) | ![多页面](https://xiaoyingapi.com/media/uploads/files/eddc8f60_20260706134427.png) |

|                                      蜘蛛访问日志                                      |                                      防火墙管理                                      |                                      站点设置                                      |
| :------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------: | :----------------------------------------------------------------------------: |
| ![蜘蛛日志](https://xiaoyingapi.com/media/uploads/files/dad6f526_20260706134428.png) | ![防火墙](https://xiaoyingapi.com/media/uploads/files/bde3c13d_20260706134429.png) | ![设置](https://xiaoyingapi.com/media/uploads/files/12bc49d9_20260706134431.png) |

***

## 快速开始

### 环境要求

- Python 3.10 以上版本
- MySQL 8.0 （默认使用 SQLite）
- pip 包管理工具

### 部署步骤

```bash
# 克隆代码并进入项目目录
git clone https://github.com/DingZhiYingCloud/XiaoYingCMS.git
cd XiaoYingCMS

# 创建并激活 Python 虚拟环境
python -m venv venv
# Windows 系统执行: venv\Scripts\activate
# Linux / macOS 系统执行: source venv/bin/activate

# 安装项目依赖
pip install -r requirements.txt

# 配置环境变量（编辑 .env 文件中的数据库与 API 密钥）
cp .env.example .env

# 初始化数据库
python manage.py makemigrations
python manage.py migrate


# 启动开发服务器（默认端口 8003）
python manage.py runserver 8003
```

启动后访问 `http://127.0.0.1:8003/xiaoying_admin/login/` 进入后台登录页面。

默认的账号密码是: \
账号: `xiaoyingadmin`

密码: `xiaoyingadmin`

<br />

> 如需使用 AI 生成能力，需在 `.env` 中配置有效的 `API_URL`，指向 DeepSeek 兼容的 API 服务。

***

## 配置说明

### 环境变量

项目核心配置通过 `.env` 文件管理，主要参数如下：

| 配置项             | 用途说明                  | 默认值                     |
| --------------- | --------------------- | ----------------------- |
| `SECRET_KEY`    | Django 安全密钥，生产环境务必更换  | —                       |
| `DEBUG`         | 是否开启调试模式              | `True`                  |
| `ALLOWED_HOSTS` | 允许访问的域名列表             | `*`                     |
| `SITE_NAME`     | 后台站点显示名称              | `小影CMS管理系统`             |
| `API_URL`       | 小影API地址(浏览器搜索小影API即可) | `http://127.0.0.1:8000` |
| `BACKUP_DIR`    | 数据备份文件存储目录            | `backups`               |
| `VERSION`       | 系统版本号                 | `1.0.0`                 |

### 功能模块配置

| 模块      | 配置方式                                         |
| ------- | -------------------------------------------- |
| AI 页面生成 | 在 `.env` 中配置 `API_URL` 指向可用的 DeepSeek 兼容 API |
| 斗篷伪装    | 登录后台后，在「黑帽SEO → 斗篷伪装」页面配置规则                  |
| 蜘蛛日志    | 自动启用，可在「蜘蛛管理 → 忽略路径」中过滤噪音                    |
| 防火墙     | 在「安全防护 → 防火墙管理」中维护 IP/路径黑名单                  |
| 域名绑定    | 中间件自动启用，在「页面管理」中配置域名与页面的映射关系                 |

### 中间件处理链路

请求进入系统后会依次经过以下中间件处理：

- **FirewallMiddleware** — 拦截黑名单 IP 与路径
- **SpiderLogMiddleware** — 记录爬虫与真人访问日志
- **StatisticsCodeMiddleware** — 注入统计代码
- **StaticFileServeMiddleware** — 白名单静态文件路由
- **SeoCloakMiddleware** — 爬虫斗篷伪装分发
- **DomainBindMiddleware** — 域名与页面绑定解析
- **LoginRequiredMiddleware** — 后台登录鉴权
- **OperationLogMiddleware** — 操作审计记录
- **LayoutMiddleware** — 页面布局渲染

***

## 项目构成

```
XiaoYingCMS/
├── XiaoYingAdmin/        核心业务代码
│   ├── models/           数据模型（域名/页面/蜘蛛日志/防火墙等）
│   ├── views/            视图层（SEO/蜘蛛/多页面/AI生成等模块）
│   ├── templates/        前端模板
│   ├── static/           静态资源
│   ├── middleware/       中间件集合
│   ├── common/           通用工具库
│   └── utils/            工具函数
├── XiaoYingCMS/          Django 项目配置文件
├── .env                  环境变量
└── requirements.txt      Python 依赖清单
```

***

## 技术栈

后端采用 Django 5.x 框架，数据库支持 MySQL（推荐）与 SQLite。前端使用 LayUI + FontAwesome 6 构建后台界面。AI 推理对接 DeepSeek API（兼容 OpenAI 格式），支持自然语言生成页面内容。

***

## 许可证

本项目采用 MIT 许可证，详情请查阅 [LICENSE](LICENSE) 文件。

***

## 联系方式

- 微信: duyanbz
- Telegram: [@xiaoying1216](https://t.me/xiaoying1216)

***

用心做好每一个站点 · 小影CMS

Made with ❤️
