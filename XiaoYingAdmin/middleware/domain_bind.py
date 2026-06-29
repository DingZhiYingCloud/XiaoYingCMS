"""
域名绑定中间件 — 将绑定了域名的页面直接渲染到前台。

工作方式：
  1. 请求进来，判断路径是否以 /xiaoying_admin/ 开头
  2. 是 → 跳过，正常走 Django 路由（管理后台）
  3. 否 → 从 Host 请求头提取域名，去 GeneratedPage 表匹配
  4. 匹配到 → 直接返回该页面 HTML
  5. 未匹配 → 返回纯文本"未开启页面"

注册到 settings.py MIDDLEWARE 列表即可启用。
建议放在靠前位置（如 SecurityMiddleware 之后），跳过 session/auth 等不必要处理。
"""

from django.http import HttpResponse
from XiaoYingAdmin.models.generated_page import GeneratedPage


class DomainBindMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._page_model = None

    @property
    def page_model(self):
        if self._page_model is None:
            self._page_model = GeneratedPage
        return self._page_model

    def __call__(self, request):
        # 管理后台路径 → 跳过
        if request.path.startswith('/xiaoying_admin/'):
            return self.get_response(request)

        # 静态文件路径 → 跳过（开发服务器由 staticfiles 处理）
        if request.path.startswith('/static/'):
            return self.get_response(request)

        # 从请求头提取 Host（绕过 ALLOWED_HOSTS 验证，因为绑定的域名是动态的）
        raw_host = request.META.get('HTTP_HOST', '')
        host = raw_host.split(':')[0].strip().lower()
        if not host:
            return self.get_response(request)

        # 同时匹配 host（无端口）和完整的 host:port
        full_host = raw_host.strip().lower()
        page = self.page_model.objects.filter(domain=host).first()
        if page is None and full_host != host:
            page = self.page_model.objects.filter(domain=full_host).first()
        if page is None:
            return HttpResponse('未开启页面', content_type='text/plain; charset=utf-8')

        return HttpResponse(page.html_content, content_type='text/html; charset=utf-8')
