"""
认证中间件 — 未登录用户自动跳转到登录页。

白名单路径（无需登录即可访问）:
  - /xiaoying_admin/login/
  - /xiaoying_admin/logout/  （已登录时主动退出用）
  - 静态资源路径

IP 白名单（在网站设置中配置）:
  - 只允许指定的 IP 访问登录页和后台
  - 非白名单 IP 返回 403

注意: 此中间件必须放在 AuthenticationMiddleware 之后,
      确保 request.user 已可用。
"""

import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from XiaoYingAdmin.models.user import User

logger = logging.getLogger(__name__)


# 无需登录的白名单路径（支持正则）
LOGIN_WHITELIST = [
    r'^/xiaoying_admin/login/.*$',
    r'^/xiaoying_admin/logout/.*$',
    r'^/xiaoying_admin/register/.*$',
    r'^/xiaoying_admin/forgot_password/.*$',
    r'^/static/.*$',
    r'^/media/.*$',
]


class LoginRequiredMiddleware(MiddlewareMixin):
    """确保后台页面必须登录才能访问"""

    # ------------------------------------------------------------------
    # 权重页面项目 - 域名匹配
    # ------------------------------------------------------------------

    @staticmethod
    def _match_domain(host: str, domain_pattern: str) -> bool:
        """判断 host 是否匹配 domain_pattern。支持精确匹配和 *. 通配符。"""
        if domain_pattern == host:
            return True
        if domain_pattern.startswith('*.') and host.endswith(domain_pattern[1:]):
            return '.' in host and host != domain_pattern[1:]
        return False

    @staticmethod
    def _find_weight_project_by_domain(host: str):
        """查找域名匹配的权重页面项目。"""
        from XiaoYingAdmin.models.weight_project import WeightProject
        for project in WeightProject.objects.exclude(domain='').iterator():
            if LoginRequiredMiddleware._match_domain(host, project.domain):
                return project
        return None

    # ------------------------------------------------------------------
    # 权重页面项目 - 代理转发
    # ------------------------------------------------------------------

    @staticmethod
    def _proxy_headers(source_meta: dict) -> dict:
        """从 request.META 提取需要转发的 HTTP 头。"""
        headers = {}
        for key, value in source_meta.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').title()
                if header_name in ('Host', 'X-Forwarded-For', 'X-Forwarded-Proto',
                                   'X-Forwarded-Host', 'Connection', 'Proxy-Connection',
                                   'Transfer-Encoding', 'Content-Length'):
                    continue
                headers[header_name] = value
        xff = source_meta.get('HTTP_X_FORWARDED_FOR', '')
        remote_addr = source_meta.get('REMOTE_ADDR', '')
        if xff:
            headers['X-Forwarded-For'] = f'{xff}, {remote_addr}'
        elif remote_addr:
            headers['X-Forwarded-For'] = remote_addr
        return headers

    @staticmethod
    def _proxy_to_weight_project(request, project) -> HttpResponse:
        """将请求代理转发到权重页面项目的 Django 服务器。"""
        if project.status != 'running':
            return HttpResponse(
                f'<h1 style="text-align:center;margin-top:15%;color:#999;">'
                f'项目「{project.name}」未运行<br>'
                f'<span style="font-size:14px;">请先在后台启动该项目</span></h1>',
                status=502, content_type='text/html; charset=utf-8',
            )

        target_url = f'http://127.0.0.1:{project.port}{request.path}'
        if request.META.get('QUERY_STRING'):
            target_url += f'?{request.META["QUERY_STRING"]}'

        headers = LoginRequiredMiddleware._proxy_headers(request.META)
        headers['Host'] = f'127.0.0.1:{project.port}'

        body = request.body if request.method in ('POST', 'PUT', 'PATCH') else None

        try:
            req = urllib.request.Request(
                target_url, data=body if body else None,
                headers=headers, method=request.method,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read()
                resp_headers = dict(resp.headers)
                content_type = resp_headers.get('Content-Type', 'text/html; charset=utf-8')
                return HttpResponse(
                    content=resp_body,
                    status=resp.status,
                    content_type=content_type,
                )
        except urllib.error.HTTPError as e:
            return HttpResponse(
                content=e.read(),
                status=e.code,
                content_type=dict(e.headers).get('Content-Type', 'text/plain'),
            )
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f'代理请求失败: {target_url} → {e}')
            return HttpResponse(
                f'<h1 style="text-align:center;margin-top:15%;color:#999;">'
                f'代理请求失败<br><span style="font-size:14px;">请检查子项目是否运行正常</span></h1>',
                status=502, content_type='text/html; charset=utf-8',
            )

    # ------------------------------------------------------------------
    # 主处理逻辑
    # ------------------------------------------------------------------

    def process_request(self, request):
        # =====================================================================
        # 首次运行：系统中无超级管理员时自动创建默认账号
        # =====================================================================
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser('xiaoying', password='xiaoyingadmin')

        path = request.path_info

        # =====================================================================
        # 权重页面项目 - 域名访问处理
        # 非后台路径 → 检查域名是否匹配权重项目，如是则根据 wp_proxy_public
        # 配置判断是否需要登录后再代理转发
        #
        # 注意：API 路径前缀（如 /api/）不走权重代理，由当前项目直接处理。
        # 若不加此判断，当 API_URL 指向自身域名时，请求会再次被代理转发
        # 到匹配的权重子项目，而子项目未运行时返回 502。
        # =====================================================================
        if not path.startswith('/xiaoying_admin/'):
            # API 路径不走权重代理（由当前项目直接处理）
            if path.startswith('/api/'):
                return None
            host = request.META.get('HTTP_HOST', '').split(':')[0].strip().lower()
            if host:
                wp = self._find_weight_project_by_domain(host)
                if wp:
                    from XiaoYingAdmin.models.site_settings import SiteSettings
                    ss = SiteSettings.objects.first()
                    # 如果要求登录且用户未认证 → 跳转到登录页
                    if ss and not ss.wp_proxy_public and not request.user.is_authenticated:
                        login_url = getattr(settings, 'LOGIN_URL', '/xiaoying_admin/login/')
                        return HttpResponseRedirect(login_url)
                    # 公开访问 或 已登录 → 代理转发
                    return self._proxy_to_weight_project(request, wp)
            return None

        # 预先查询站点设置（多个路径分支都需要用到）
        from XiaoYingAdmin.models.site_settings import SiteSettings
        from XiaoYingAdmin.common.http import get_client_ip
        site_settings = SiteSettings.objects.first()

        # 反向代理路径不受 IP 白名单限制，子项目内容应对公网开放
        if not path.startswith('/xiaoying_admin/wp-proxy/'):
            # =================================================================
            # IP 白名单检查：如果配置了白名单，非白名单 IP 禁止访问后台
            # =================================================================
            if site_settings and site_settings.login_ip_whitelist.strip():
                whitelist_ips = [
                    ip.strip() for ip in site_settings.login_ip_whitelist.strip().split('\n')
                    if ip.strip()
                ]
                if whitelist_ips:
                    client_ip = get_client_ip(request)
                    if client_ip not in whitelist_ips:
                        return HttpResponse(
                            '<h1 style="text-align:center;margin-top:15%;color:#999;">'
                            '访问被拒绝<br><span style="font-size:14px;">您的 IP 不在访问白名单中</span></h1>',
                            status=403, content_type='text/html; charset=utf-8',
                        )

            # =================================================================
            # 域名白名单检查：如果配置了允许的域名，非白名单域名禁止访问后台
            # =================================================================
            if site_settings and site_settings.allowed_admin_domains.strip():
                from XiaoYingAdmin.common.http import get_request_host, is_host_allowed
                current_host = get_request_host(request)
                if not is_host_allowed(current_host, site_settings.allowed_admin_domains):
                    return HttpResponse(
                        '<h1 style="text-align:center;margin-top:15%;color:#999;">'
                        '访问被拒绝<br><span style="font-size:14px;">'
                        '请通过指定的域名访问后台管理</span></h1>',
                        status=403, content_type='text/html; charset=utf-8',
                    )

        # 如果用户已认证,通行
        if request.user.is_authenticated:
            return None

        # 白名单路径通行
        for pattern in LOGIN_WHITELIST:
            if re.match(pattern, path):
                return None

        # 权重项目代理路径：如果开启了公开访问，无需登录
        if path.startswith('/xiaoying_admin/wp-proxy/'):
            if site_settings and site_settings.wp_proxy_public:
                return None

        # 未登录 → 跳转到登录页
        login_url = getattr(settings, 'LOGIN_URL', '/xiaoying_admin/login/')
        return HttpResponseRedirect(login_url)
