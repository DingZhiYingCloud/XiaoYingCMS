"""
认证中间件 — 未登录用户自动跳转到登录页。

白名单路径（无需登录即可访问）:
  - /xiaoying_admin/login/
  - /xiaoying_admin/logout/  （已登录时主动退出用）
  - 静态资源路径

注意: 此中间件必须放在 AuthenticationMiddleware 之后,
      确保 request.user 已可用。
"""

import re
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from XiaoYingAdmin.models.user import User


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

    def process_request(self, request):
        # =====================================================================
        # 首次运行：系统中无超级管理员时自动创建默认账号
        # =====================================================================
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser('xiaoying', password='xiaoyingadmin')

        # 如果用户已认证,通行
        if request.user.is_authenticated:
            return None

        path = request.path_info

        # 白名单路径通行
        for pattern in LOGIN_WHITELIST:
            if re.match(pattern, path):
                return None

        # 非后台路径通行（仅保护 /xiaoying_admin/ 下的页面）
        if not path.startswith('/xiaoying_admin/'):
            return None

        # 未登录 → 跳转到登录页
        login_url = getattr(settings, 'LOGIN_URL', '/xiaoying_admin/login/')
        return HttpResponseRedirect(login_url)
