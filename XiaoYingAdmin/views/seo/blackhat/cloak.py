import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from XiaoYingAdmin.common.http import err, parse_json_body
from XiaoYingAdmin.models.seo_cloak import SeoCloakRule, ACTION_CHOICES, REDIRECT_CODE_CHOICES


# =============================================================================
# 页面视图
# =============================================================================

def seo_cloak_view(request):
    """
    斗篷伪装（Cloaking）配置页面。

    核心原理：根据访问者身份（搜索引擎爬虫 vs 真实用户）返回不同的内容。
    对爬虫展示精心优化的 SEO 内容，对真实用户展示正常页面，
    从而在搜索引擎中获得更高排名。
    """
    config = SeoCloakRule.get_singleton()
    return render(request, 'XiaoYingAdmin/黑帽SEO/斗篷伪装/index.html', {
        'config': config.to_dict(),
    })


# =============================================================================
# AJAX API: 配置管理
# =============================================================================

@csrf_exempt
@require_POST
def seo_cloak_config_save(request):
    """
    保存斗篷伪装配置。

    请求: application/json
      {
        "is_enabled": true,
        "search_engines": "[\"google.\", \"bing.\"]",
        "spider_keywords": "[\"googlebot\", \"bingbot\"]",
        "spider_action": "redirect",
        "search_action": "show_cloak",
        "direct_action": "pass_through",
        "redirect_status_code": 301,
        "spider_redirect_url": "https://example.com/seo-page",
        "search_redirect_url": "https://example.com/cloak-page",
        "direct_redirect_url": "",
        "whitelist_paths": "/api/\n/static/",
        "seo_content": "<html>SEO content</html>",
        "cloak_content": "<html>Cloak content</html>"
      }
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    rule = SeoCloakRule.get_singleton()

    # 开关
    if 'is_enabled' in body:
        rule.is_enabled = bool(body['is_enabled'])

    # 搜索引擎列表
    if 'search_engines' in body:
        try:
            eng = json.loads(body['search_engines']) if isinstance(body['search_engines'], str) else body['search_engines']
            if not isinstance(eng, list):
                return err('search_engines 必须为数组')
            rule.search_engines = json.dumps(eng, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return err('search_engines JSON 格式错误')

    # 爬虫关键字列表
    if 'spider_keywords' in body:
        try:
            kw = json.loads(body['spider_keywords']) if isinstance(body['spider_keywords'], str) else body['spider_keywords']
            if not isinstance(kw, list):
                return err('spider_keywords 必须为数组')
            rule.spider_keywords = json.dumps(kw, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return err('spider_keywords JSON 格式错误')

    # 行为策略
    valid_actions = set(v for v, _ in ACTION_CHOICES)
    for field in ('spider_action', 'search_action', 'direct_action'):
        if field in body:
            val = str(body[field]).strip()
            if val not in valid_actions:
                return err(f'{field} 值非法，可选：{", ".join(sorted(valid_actions))}')
            setattr(rule, field, val)

    # 重定向状态码
    if 'redirect_status_code' in body:
        code = int(body['redirect_status_code'])
        valid_codes = set(c for c, _ in REDIRECT_CODE_CHOICES)
        if code not in valid_codes:
            return err(f'redirect_status_code 非法，可选：{sorted(valid_codes)}')
        rule.redirect_status_code = code

    # 重定向 URL
    for field in ('spider_redirect_url', 'search_redirect_url', 'direct_redirect_url'):
        if field in body:
            setattr(rule, field, (body[field] or '').strip())

    # 其他文本字段
    for field in ('whitelist_paths', 'seo_content', 'cloak_content'):
        if field in body:
            setattr(rule, field, (body[field] or ''))

    rule.save()

    return JsonResponse({
        'message': '配置已保存',
        'config': rule.to_dict(),
    })
