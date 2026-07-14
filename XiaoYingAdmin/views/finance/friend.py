"""
好友管理视图 — 好友分类 + 好友 + 事件 CRUD + 到期提醒
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import parse_json_body, err, get_or_404
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.finance import FriendCategory, EventType, Friend, FriendEvent
from XiaoYingAdmin.views.finance import paginate_queryset, paginate_response

FRIEND_TEMPLATE = 'XiaoYingAdmin/个人财务/好友管理.html'


@login_required
@require_GET
def friend_view(request):
    """好友管理页面"""
    return render(request, FRIEND_TEMPLATE)


# =============================================================================
# 分类 API
# =============================================================================

@csrf_exempt
@require_GET
def category_api_list(request):
    """获取好友分类列表"""
    cats = FriendCategory.objects.all()
    data = [{
        'id': c.id,
        'name': c.name,
        'sort_order': c.sort_order,
        'is_preset': c.is_preset,
    } for c in cats]
    return JsonResponse({'ok': True, 'list': data})


@csrf_exempt
@require_POST
def category_api_save(request):
    """创建/更新分类"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    cat_id = body.get('id')
    name = (body.get('name') or '').strip()
    sort_order = body.get('sort_order', 0)

    if not name:
        return err('请输入分类名称')

    if cat_id:
        cat, error_resp = get_or_404(FriendCategory, id=cat_id)
        if error_resp:
            return error_resp
        cat.name = name
        cat.sort_order = sort_order
        cat.save()
    else:
        cat = FriendCategory.objects.create(name=name, sort_order=sort_order)
    return JsonResponse({'ok': True, 'id': cat.id})


@csrf_exempt
@require_POST
def category_api_delete(request):
    """删除分类（预设分类不可删除）"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    cat_id = body.get('id')
    cat, error_resp = get_or_404(FriendCategory, id=cat_id)
    if error_resp:
        return error_resp
    if cat.is_preset:
        return err('预设分类不可删除')
    # 将关联好友设为无分类
    Friend.objects.filter(category=cat).update(category=None)
    cat.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_GET
def category_api_presets(request):
    """生成预设分类（首次使用调用）"""
    if FriendCategory.objects.exists():
        return JsonResponse({'ok': True, 'message': '已有分类'})

    presets = ['亲密好友', '好朋友', '普通朋友', '同事', '家人']
    for i, name in enumerate(presets):
        FriendCategory.objects.create(name=name, sort_order=i, is_preset=True)
    return JsonResponse({'ok': True, 'message': '预设分类已创建'})


# =============================================================================
# 事件类型 API
# =============================================================================

@csrf_exempt
@require_GET
def event_type_api_list(request):
    """获取事件类型列表"""
    types = EventType.objects.all()
    data = [{
        'id': t.id,
        'name': t.name,
        'is_preset': t.is_preset,
    } for t in types]
    return JsonResponse({'ok': True, 'list': data})


@csrf_exempt
@require_POST
def event_type_api_save(request):
    """创建/更新事件类型"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    type_id = body.get('id')
    name = (body.get('name') or '').strip()
    if not name:
        return err('请输入类型名称')

    if type_id:
        et, error_resp = get_or_404(EventType, id=type_id)
        if error_resp:
            return error_resp
        et.name = name
        et.save()
    else:
        et = EventType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': et.id})


@csrf_exempt
@require_POST
def event_type_api_delete(request):
    """删除事件类型"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    type_id = body.get('id')
    et, error_resp = get_or_404(EventType, id=type_id)
    if error_resp:
        return error_resp
    if et.is_preset:
        return err('预设类型不可删除')
    et.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_GET
def event_type_api_presets(request):
    """生成预设事件类型"""
    if EventType.objects.exists():
        return JsonResponse({'ok': True, 'message': '已有类型'})

    presets = ['请吃饭', '送礼物', '聚会', '看电影', '其他']
    for name in presets:
        EventType.objects.create(name=name, is_preset=True)
    return JsonResponse({'ok': True, 'message': '预设类型已创建'})


# =============================================================================
# 好友 API
# =============================================================================

@csrf_exempt
@require_GET
def friend_api_list(request):
    """获取好友列表（分页）"""
    category_id = request.GET.get('category_id')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    qs = Friend.objects.all()
    if category_id:
        qs = qs.filter(category_id=category_id)
    data_list, total, total_pages, page, page_size = paginate_queryset(qs, page, page_size)
    data = [{
        'id': f.id,
        'name': f.name,
        'category_id': f.category_id,
        'category_name': f.category.name if f.category else '未分类',
        'remark': f.remark,
        'create_time': f.create_time.strftime('%Y-%m-%d %H:%M:%S'),
    } for f in data_list]
    return JsonResponse(paginate_response(True, data, total, total_pages, page, page_size))


@csrf_exempt
@require_POST
def friend_api_save(request):
    """创建/更新好友"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    friend_id = body.get('id')
    name = (body.get('name') or '').strip()
    category_id = body.get('category_id')
    remark = (body.get('remark') or '').strip()

    if not name:
        return err('请输入好友姓名')

    if friend_id:
        friend, error_resp = get_or_404(Friend, id=friend_id)
        if error_resp:
            return error_resp
        friend.name = name
        friend.category_id = category_id or None
        friend.remark = remark
        friend.save()
    else:
        friend = Friend.objects.create(
            name=name,
            category_id=category_id or None,
            remark=remark,
        )
    return JsonResponse({'ok': True, 'id': friend.id})


@csrf_exempt
@require_POST
def friend_api_delete(request):
    """删除好友"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    friend_id = body.get('id')
    friend, error_resp = get_or_404(Friend, id=friend_id)
    if error_resp:
        return error_resp
    friend.delete()
    return JsonResponse({'ok': True})


# =============================================================================
# 好友事件 API
# =============================================================================

@csrf_exempt
@require_GET
def event_api_list(request):
    """获取事件列表，可按好友筛选（分页）"""
    friend_id = request.GET.get('friend_id')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    qs = FriendEvent.objects.all()
    if friend_id:
        qs = qs.filter(friend_id=friend_id)
    data_list, total, total_pages, page, page_size = paginate_queryset(qs, page, page_size)
    data = [{
        'id': e.id,
        'friend_id': e.friend_id,
        'friend_name': e.friend.name,
        'event_type_id': e.event_type_id,
        'event_type_name': e.event_type.name if e.event_type else e.custom_type_name,
        'custom_type_name': e.custom_type_name,
        'title': e.title,
        'description': e.description,
        'event_date': e.event_date.isoformat() if e.event_date else '',
        'status': e.status,
        'status_label': e.get_status_display(),
        'create_time': e.create_time.strftime('%Y-%m-%d %H:%M:%S'),
    } for e in data_list]
    return JsonResponse(paginate_response(True, data, total, total_pages, page, page_size))


@csrf_exempt
@require_POST
def event_api_save(request):
    """创建/更新事件"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    event_id = body.get('id')
    friend_id = body.get('friend_id')
    event_type_id = body.get('event_type_id')
    custom_type_name = (body.get('custom_type_name') or '').strip()
    title = (body.get('title') or '').strip()
    description = (body.get('description') or '').strip()
    event_date = body.get('event_date')
    status = body.get('status', 'todo')

    if not friend_id:
        return err('请选择好友')
    if not title:
        return err('请输入事件标题')

    if event_id:
        ev, error_resp = get_or_404(FriendEvent, id=event_id)
        if error_resp:
            return error_resp
        ev.friend_id = friend_id
        ev.event_type_id = event_type_id or None
        ev.custom_type_name = custom_type_name
        ev.title = title
        ev.description = description
        ev.event_date = event_date
        ev.status = status
        ev.save()
    else:
        ev = FriendEvent.objects.create(
            friend_id=friend_id,
            event_type_id=event_type_id or None,
            custom_type_name=custom_type_name,
            title=title,
            description=description,
            event_date=event_date,
            status=status,
        )
    return JsonResponse({'ok': True, 'id': ev.id})


@csrf_exempt
@require_POST
def event_api_delete(request):
    """删除事件"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    event_id = body.get('id')
    ev, error_resp = get_or_404(FriendEvent, id=event_id)
    if error_resp:
        return error_resp
    ev.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
def event_api_toggle_status(request):
    """切换事件状态 (pending → todo → done → pending)"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    event_id = body.get('id')
    ev, error_resp = get_or_404(FriendEvent, id=event_id)
    if error_resp:
        return error_resp

    cycle = {'pending': 'todo', 'todo': 'done', 'done': 'pending'}
    ev.status = cycle.get(ev.status, 'pending')
    ev.save()
    return JsonResponse({'ok': True, 'status': ev.status, 'status_label': ev.get_status_display()})


@csrf_exempt
@require_GET
def event_api_reminders(request):
    """获取已到期但尚未开始的事件提醒列表"""
    today = date.today()
    qs = FriendEvent.objects.filter(
        event_date__lte=today,
        status='pending',
    ).select_related('friend')
    reminders = []
    for e in qs:
        days_overdue = (today - e.event_date).days
        reminders.append({
            'id': e.id,
            'friend_id': e.friend_id,
            'friend_name': e.friend.name,
            'title': e.title,
            'event_date': e.event_date.isoformat(),
            'days_overdue': days_overdue,
        })
    return JsonResponse({'ok': True, 'reminders': reminders})
