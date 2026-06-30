"""
蜘蛛访问日志中间件 — 记录每个 HTTP 请求到 SpiderAccessLog 表。

工作流程：
  1. 读取 SpiderLogConfig.log_mode：
       - "disabled"     → 直接放行，不记录
       - "all"          → 记录所有（爬虫 + 真人）
       - "spider_only"  → 只记录被识别为爬虫的
  2. 跳过 /xiaoying_admin/ 后台路径
  3. 跳过 SeoCloakRule 白名单路径（与斗篷共享）
  4. 收集请求元数据：IP / UA / path / method / referer
  5. 复用 SeoCloakRule.is_spider() 识别爬虫 + 提取爬虫名
  6. 调用下游 get_response(request) 拿到 response
  7. 收集 status_code / response_size 后 try/except 写 DB
  8. 写 DB 异常被捕获，不影响主响应返回

放置位置：MIDDLEWARE 列表靠前（在 SeoCloakMiddleware / DomainBindMiddleware 之前）。
这样即便斗篷/域名中间件直接 return HttpResponse 短路 view，本中间件的
response 阶段仍会执行（洋葱外层最后处理 response），确保所有访问被记录。
"""

import logging

from django.db import DatabaseError

from XiaoYingAdmin.models.seo_cloak import SeoCloakRule
from XiaoYingAdmin.models.spider_log import SpiderAccessLog, SpiderLogConfig


logger = logging.getLogger(__name__)


def _get_client_ip(meta) -> str:
    """从 request.META 提取客户端真实 IP（优先 X-Forwarded-For）。"""
    xff = meta.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        # 多层代理时取第一个
        return xff.split(',')[0].strip()
    return meta.get('REMOTE_ADDR', '0.0.0.0')


def _extract_spider_name(user_agent: str, keywords: list) -> str:
    """从 UA 中找第一个匹配的爬虫关键字（小写匹配），返回原始大小写的 keyword。

    如果没匹配到返回空串。SpiderAccessLog.spider_name 留空表示"真人"。
    """
    if not user_agent or not keywords:
        return ''
    ua_lower = user_agent.lower()
    for kw in keywords:
        if kw and kw in ua_lower:
            return kw
    return ''


class SpiderLogMiddleware:
    """蜘蛛 / 真人访问日志中间件。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # === 1. 读取配置 ===
        config = SpiderLogConfig.get_singleton()
        log_mode = config.log_mode

        # === 2. 关闭模式 → 直接放行 ===
        if log_mode == 'disabled':
            return self.get_response(request)

        # === 3. 跳过后台路径（与 SeoCloak 一致） ===
        if request.path.startswith('/xiaoying_admin/'):
            return self.get_response(request)

        # === 4. 跳过白名单（与 SeoCloak 共享） ===
        cloak_rule = SeoCloakRule.get_singleton()
        if cloak_rule.is_whitelisted(request.path):
            return self.get_response(request)

        # === 5. 收集请求元数据 ===
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        is_spider = cloak_rule.is_spider(user_agent)
        spider_name = _extract_spider_name(user_agent, cloak_rule.get_spider_keywords()) if is_spider else ''

        # === 6. 根据 log_mode 决定是否记录 ===
        if log_mode == 'spider_only' and not is_spider:
            return self.get_response(request)

        # === 7. 调用下游，拿到 response ===
        response = self.get_response(request)

        # === 8. 收集响应数据后写 DB（异常隔离） ===
        try:
            status_code = response.status_code
            response_size = len(response.content) if hasattr(response, 'content') else None
            SpiderAccessLog.objects.create(
                ip=_get_client_ip(request.META)[:45],  # GenericIPAddressField 上限 45 字符
                user_agent=user_agent[:5000],  # 避免极端长 UA 撑爆 DB
                spider_name=spider_name[:64],
                path=request.path[:500],
                method=request.method[:10],
                referer=request.META.get('HTTP_REFERER', '')[:500],
                status_code=status_code,
                response_size=response_size,
            )
        except (DatabaseError, ValueError, TypeError, Exception) as e:  # noqa: BLE001 — 故意捕获所有异常，避免日志写入影响主响应
            logger.warning('SpiderLogMiddleware 写日志失败: %s', e)

        return response
