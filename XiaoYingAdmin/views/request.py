from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from XiaoYingAdmin.common.http import parse_json_body, err, get_or_404
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.views.page_generator import (
    get_task_progress,
    start_generation,
)

from XiaoYingAdmin.models.prompt import Prompt
from XiaoYingAdmin.models.generated_page import GeneratedPage
from XiaoYingAdmin.models.site_settings import SiteSettings
from XiaoYingAdmin.models.user_config import UserConfig
from XiaoYingAdmin.models.user import User
from XiaoYingAdmin.models.spider_log import SpiderAccessLog
from XiaoYingAdmin.models.operation_log import OperationLog
from XiaoYingAdmin.models.login_log import LoginLog
from XiaoYingAdmin.models.task import PageGenerationTask


# =============================================================================
# 页面视图（模板渲染）
# =============================================================================

# TemplateView: 模板视图（用于直接预览母版）
def template_view(request):
    return render(request, 'XiaoYingAdmin/template.html')


# IndexView: 首页视图
def index_view(request):
    """首页仪表盘 — 展示项目概览统计"""
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    context = {
        # 用户统计
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'staff_users': User.objects.filter(is_staff=True).count(),
        # 内容统计
        'total_pages': GeneratedPage.objects.count(),
        'total_prompts': Prompt.objects.count(),
        'active_prompts': Prompt.objects.filter(is_active=True).count(),
        # 蜘蛛统计
        'spider_total': SpiderAccessLog.objects.count(),
        'spider_today': SpiderAccessLog.objects.filter(create_time__gte=today).count(),
        # 日志统计
        'op_log_today': OperationLog.objects.filter(created_at__gte=today).count(),
        'login_log_today': LoginLog.objects.filter(login_time__gte=today).count(),
        'total_tasks': PageGenerationTask.objects.count(),
        'failed_tasks': PageGenerationTask.objects.filter(status='failed').count(),
    }
    return render(request, 'XiaoYingAdmin/index.html', context)


# CoreSettingsView: 网站设置视图
def site_settings_view(request):
    """
    网站设置页：单例 SiteSettings + UserConfig 读写。

    GET:  渲染表单（带当前值）
    POST: 保存 statistics_code / is_active / user_config 配置，然后 PRG 重定向回 GET
    """
    settings, _ = SiteSettings.objects.get_or_create(pk=1)
    user_config = UserConfig.get_singleton()

    if request.method == 'POST':
        settings.statistics_code = request.POST.get('statistics_code', '') or ''
        settings.is_active = request.POST.get('is_active') == 'on'
        settings.save(update_fields=['statistics_code', 'is_active', 'updated_time'])

        # 用户系统配置
        user_config.registration_enabled = request.POST.get('registration_enabled') == 'on'
        user_config.save(update_fields=['registration_enabled', 'updated_time'])

        return redirect(reverse('site_settings') + '?saved=1')

    return render(request, 'XiaoYingAdmin/核心设置/网站设置.html', {
        'site_settings': settings,
        'user_config': user_config,
        'saved': request.GET.get('saved') == '1',
    })


# PageGenerateView: 页面生成视图
def page_generate_view(request):
    """页面生成页 — 若 session 中存在活跃任务，自动恢复进度显示。"""
    task_id = request.session.get('page_gen_task_id')
    active_task = None
    if task_id:
        active_task = get_task_progress(task_id)
        if active_task and active_task['status'] in ('completed', 'failed'):
            # 已结束的任务不保留在 session
            request.session.pop('page_gen_task_id', None)
    return render(request, 'XiaoYingAdmin/页面管理/页面生成.html', {
        'active_task': active_task,
    })


# PageListView: 页面列表视图
def page_list_view(request):
    return render(request, 'XiaoYingAdmin/页面管理/页面列表.html')


# =============================================================================
# AJAX API: 页面生成
# =============================================================================

@csrf_exempt
@require_POST
def api_start_generate(request):
    """
    启动一次 AI 页面生成。

    请求: POST application/json
      {"content": "页面描述..."}

    响应: application/json
      {"task_id": "...", "status": "pending", "progress": 0, "message": "..."}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    content = (body.get('content') or '').strip()
    if not content:
        return err('请输入页面描述内容')

    if not request.session.session_key:
        request.session.save()

    task = start_generation(
        input_content=content,
        session_key=request.session.session_key,
    )

    # 写入 session：刷新页面后可恢复进度
    request.session['page_gen_task_id'] = str(task.task_id)

    log_operation(request, 'create', 'PageGeneration', str(task.task_id),
                  f'页面生成「{content[:50]}」',
                  detail={'changes': {'需求描述': {'new': content[:100]}}})

    return JsonResponse({
        'task_id': str(task.task_id),
        'status': task.status,
        'status_display': task.get_status_display(),
        'progress': task.progress,
        'message': task.message,
    })


@require_GET
def api_get_progress(request, task_id):
    """
    查询指定任务的进度（前端轮询用）。

    响应: application/json
      {"task_id":"...","status":"running","progress":50,"message":"..."}
    """
    progress = get_task_progress(task_id)
    if progress is None:
        return err('任务不存在', status=404)
    return JsonResponse(progress)


# =============================================================================
# AJAX API: 提示词管理
# =============================================================================

@require_GET
def api_prompt_list(request):
    """
    获取所有提示词列表。

    查询参数:
      category: str（可选），按分类筛选

    响应: application/json
      [{"id":1, "category":"...", "name":"...", "version":1, "is_active":true, "content":"...", ...}]
    """
    qs = Prompt.objects.all()
    category = request.GET.get('category')
    if category:
        qs = qs.filter(category=category)
    return JsonResponse([p.to_dict() for p in qs], safe=False)


@require_GET
def api_prompt_detail(request, prompt_id):
    """获取单个提示词详情。"""
    prompt, error = get_or_404(Prompt, id=prompt_id)
    if error is not None:
        return error
    return JsonResponse(prompt.to_dict())


@csrf_exempt
@require_POST
def api_prompt_save(request):
    """
    创建新的提示词版本。

    请求: application/json
      {"category":"page_generation", "name":"通用页面生成 v3", "content":"...", "description":"调整了..."}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    category = (body.get('category') or 'page_generation').strip()
    name = (body.get('name') or '').strip()
    content = (body.get('content') or '').strip()
    description = (body.get('description') or '').strip()

    if not name:
        return err('请输入提示词名称')
    if not content:
        return err('请输入提示词内容')

    prompt = Prompt.objects.create(
        category=category,
        name=name,
        content=content,
        description=description,
    )

    log_operation(request, 'create', 'Prompt', prompt.id,
                  f'提示词「{name}」v{prompt.version}',
                  detail={'changes': {'分类': {'new': category}, '名称': {'new': name}}})

    return JsonResponse({
        'id': prompt.id,
        'version': prompt.version,
        'message': f'提示词 v{prompt.version} 创建成功',
    })


@csrf_exempt
@require_POST
def api_prompt_activate(request):
    """
    切换指定提示词的启用状态。

    请求: application/json
      {"id": 1, "is_active": false}

    注意：允许多条提示词同时启用，生成时会合并到 system_prompt 中。
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    prompt, error = get_or_404(Prompt, id=body.get('id'))
    if error is not None:
        return error

    prompt.is_active = body.get('is_active', True)
    prompt.save(update_fields=['is_active', 'updated_time'])

    status_text = '启用' if prompt.is_active else '禁用'
    log_operation(request, 'update', 'Prompt', prompt.id,
                  f'提示词「{prompt.name}」→ {status_text}',
                  detail={'changes': {'启用状态': {'new': status_text}}})

    return JsonResponse({'message': '已更新', 'is_active': prompt.is_active})


@csrf_exempt
@require_POST
def api_prompt_delete(request):
    """
    删除提示词。

    请求: application/json
      {"id": 1}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    prompt, error = get_or_404(Prompt, id=body.get('id'))
    if error is not None:
        return error

    prompt_name = prompt.name
    prompt.delete()
    log_operation(request, 'delete', 'Prompt', body.get('id'),
                  f'提示词「{prompt_name}」',
                  detail={'changes': {'已删除提示词': {'new': prompt_name}}})
    return JsonResponse({'message': '已删除'})


# =============================================================================
# AJAX API: 已保存页面
# =============================================================================

@require_GET
def api_saved_pages(request):
    """
    获取已保存的生成页面列表（支持分页 + 搜索）。

    查询参数:
      page: int（默认 1）
      limit: int（默认 15）
      keyword: str（可选，按 name 或 input_content 模糊匹配）

    响应: application/json
      {"total": 100, "page": 1, "items": [{"id":1, "name":"...", ...}]}
    """
    page = max(int(request.GET.get('page', 1) or 1), 1)
    limit = max(int(request.GET.get('limit', 15) or 15), 1)
    keyword = (request.GET.get('keyword') or '').strip()

    qs = GeneratedPage.objects.all()
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(input_content__icontains=keyword))

    total = qs.count()
    offset = (page - 1) * limit
    items = qs.order_by('-create_time')[offset:offset + limit]

    return JsonResponse({
        'total': total,
        'page': page,
        'items': [p.to_dict() for p in items],
    }, safe=False)


@require_GET
def api_saved_page_detail(request, page_id):
    """获取已保存页面的详情（含 HTML 内容）。"""
    page, error = get_or_404(GeneratedPage, id=page_id, not_found_msg='页面不存在')
    if error is not None:
        return error
    return JsonResponse(page.to_dict(with_html=True))


@csrf_exempt
@require_POST
def api_saved_page_delete(request):
    """
    删除已保存页面。

    请求: application/json
      {"id": 1}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    page, error = get_or_404(GeneratedPage, id=body.get('id'), not_found_msg='页面不存在')
    if error is not None:
        return error

    page_name = page.name
    page.delete()
    log_operation(request, 'delete', 'GeneratedPage', body.get('id'),
                  f'生成页面「{page_name}」',
                  detail={'changes': {'已删除页面': {'new': page_name}}})
    return JsonResponse({'message': '已删除'})


@csrf_exempt
@require_POST
def api_saved_page_update(request):
    """
    更新已保存页面的名称、需求描述或 HTML 内容。

    只发送需要修改的字段即可，未传的字段保持不变。

    请求: application/json
      {"id": 1, "name": "新名称"}
      {"id": 1, "name": "新名称", "html_content": "新 HTML"}
      {"id": 1, "input_content": "新需求描述"}

    响应: application/json
      {"message": "已更新", "page": {id, name, ...}}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    page, error = get_or_404(GeneratedPage, id=body.get('id'), not_found_msg='页面不存在')
    if error is not None:
        return error

    changed_fields = []
    for field in ('name', 'input_content', 'html_content'):
        if field in body:
            val = (body[field] or '').strip()
            if getattr(page, field) != val:
                changed_fields.append(field)
                setattr(page, field, val)

    if not changed_fields:
        return JsonResponse({'message': '未检测到修改', 'page': page.to_dict(with_html=True)})

    page.save(update_fields=['name', 'input_content', 'html_content', 'updated_time'])

    # 构建变更详情
    field_labels = {'name': '页面名称', 'input_content': '需求描述', 'html_content': 'HTML内容'}
    changes = {}
    for f in changed_fields:
        label = field_labels.get(f, f)
        val = (body[f] or '').strip()
        changes[label] = {'new': val[:100] + ('…' if len(val) > 100 else ''), 'old': None}
    log_operation(request, 'update', 'GeneratedPage', body.get('id'),
                  f'生成页面「{page.name}」',
                  detail={'changes': changes})

    return JsonResponse({'message': '已更新', 'page': page.to_dict(with_html=True)})


# =============================================================================
# AJAX API: 域名管理（绑定/解绑）
# =============================================================================

@csrf_exempt
@require_POST
def api_saved_page_set_domain(request):
    """
    设置或清除页面的绑定域名。

    域名在全局唯一：同一时间只能有一条记录的 domain 非空。
    清空域名：传入 domain="" 即可。

    请求: application/json
      {"id": 1, "domain": "example.com"}  设置域名
      {"id": 1, "domain": ""}             清除域名

    响应: application/json
      {"message": "...", "page": {id, name, domain, ...}}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    page, error = get_or_404(GeneratedPage, id=body.get('id'), not_found_msg='页面不存在')
    if error is not None:
        return error

    domain = (body.get('domain') or '').strip()

    if not domain:
        # 清空域名
        old_domain = page.domain
        page.domain = None
        page.save(update_fields=['domain', 'updated_time'])
        log_operation(request, 'update', 'GeneratedPage', body.get('id'),
                      f'生成页面「{page.name}」清除域名',
                      detail={'changes': {'绑定域名': {'old': old_domain, 'new': '(空)'}}})
        return JsonResponse({
            'message': '域名已清除',
            'page': page.to_dict(),
        })

    # 检查域名是否已被其他页面占用
    existing = GeneratedPage.objects.filter(domain=domain).exclude(id=page.id).first()
    if existing:
        return err(f'域名 "{domain}" 已被页面「{existing.name}」占用')

    # 如果其他页面之前绑定过同一域名但已经被清除的（domain=None），这不会冲突
    old_domain = page.domain
    page.domain = domain
    try:
        page.save(update_fields=['domain', 'updated_time'])
    except Exception:
        return err(f'域名 "{domain}" 已被其他页面占用')

    log_operation(request, 'update', 'GeneratedPage', body.get('id'),
                  f'生成页面「{page.name}」绑定域名 {domain}',
                  detail={'changes': {'绑定域名': {'old': old_domain, 'new': domain}}})

    return JsonResponse({
        'message': f'域名已设置为 {domain}',
        'page': page.to_dict(),
    })


