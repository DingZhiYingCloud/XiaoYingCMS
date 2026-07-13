"""
日消费记录视图 — 记录每日花销
"""
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import parse_json_body, err, get_or_404
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.finance import DailyExpense
from XiaoYingAdmin.views.finance import paginate_queryset, paginate_response

EXPENSE_TEMPLATE = 'XiaoYingAdmin/个人财务/日常消费.html'


@login_required
@require_GET
def expense_view(request):
    """日常消费页面"""
    return render(request, EXPENSE_TEMPLATE)


# =============================================================================
# AJAX API
# =============================================================================

@csrf_exempt
@require_GET
def expense_api_list(request):
    """获取消费记录列表，支持按月/按日筛选 + 分页"""
    month = request.GET.get('month', '')  # YYYY-MM
    date_from = request.GET.get('date_from', '')  # YYYY-MM-DD
    date_to = request.GET.get('date_to', '')  # YYYY-MM-DD
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    qs = DailyExpense.objects.all()
    if month:
        qs = qs.filter(related_month=month)
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    # 统计（基于全部筛选结果）
    total_amount = sum(float(e.amount) for e in qs)

    data_list, total, total_pages, page, page_size = paginate_queryset(qs, page, page_size)
    data = []
    for e in data_list:
        media_url = ''
        if e.media_file:
            media_url = e.media_file.url
        data.append({
            'id': e.id,
            'expense_date': e.expense_date.isoformat(),
            'expense_time': e.expense_time.strftime('%H:%M') if e.expense_time else '',
            'title': e.title,
            'description': e.description,
            'amount': str(e.amount),
            'media_file': media_url,
            'related_month': e.related_month,
            'create_time': e.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse(paginate_response(
        True, data, total, total_pages, page, page_size,
        total_amount=str(round(total_amount, 2)),
    ))


@csrf_exempt
@require_POST
def expense_api_save(request):
    """创建/更新消费记录"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    expense_id = body.get('id')
    title = (body.get('title') or '').strip()
    description = (body.get('description') or '').strip()
    amount = body.get('amount')
    expense_date = body.get('expense_date')
    expense_time = body.get('expense_time')  # HH:MM

    if not title:
        return err('请输入消费标题')
    if not amount:
        return err('请输入金额')
    if not expense_date:
        expense_date = date.today().isoformat()

    # 自动推导关联月份
    related_month = expense_date[:7]

    if expense_time:
        try:
            expense_time_obj = datetime.strptime(expense_time, '%H:%M').time()
        except ValueError:
            expense_time_obj = None
    else:
        expense_time_obj = None

    if expense_id:
        exp, error_resp = get_or_404(DailyExpense, id=expense_id)
        if error_resp:
            return error_resp
        exp.title = title
        exp.description = description
        exp.amount = amount
        exp.expense_date = expense_date
        exp.expense_time = expense_time_obj
        exp.related_month = related_month
        exp.save()
        log_operation(request, f'更新消费记录: {exp}')
    else:
        exp = DailyExpense.objects.create(
            title=title,
            description=description,
            amount=amount,
            expense_date=expense_date,
            expense_time=expense_time_obj,
            related_month=related_month,
        )
        log_operation(request, f'新增消费记录: {exp}')

    return JsonResponse({'ok': True, 'id': exp.id})


@csrf_exempt
@require_POST
def expense_api_upload(request):
    """上传消费图片/视频"""
    expense_id = request.POST.get('id')
    if not expense_id:
        return err('缺少消费记录ID')

    exp, error_resp = get_or_404(DailyExpense, id=expense_id)
    if error_resp:
        return error_resp

    if 'media_file' not in request.FILES:
        return err('未选择文件')

    exp.media_file = request.FILES['media_file']
    exp.save()
    log_operation(request, f'上传消费凭证: {exp}')

    return JsonResponse({'ok': True, 'media_url': exp.media_file.url})


@csrf_exempt
@require_POST
def expense_api_delete(request):
    """删除消费记录"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    expense_id = body.get('id')
    if not expense_id:
        return err('缺少ID')
    exp, error_resp = get_or_404(DailyExpense, id=expense_id)
    if error_resp:
        return error_resp
    # 删除关联文件
    if exp.media_file:
        exp.media_file.delete(save=False)
    log_operation(request, f'删除消费记录: {exp}')
    exp.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_GET
def expense_api_stats(request):
    """获取消费统计，按月或按日"""
    today = date.today()
    month = request.GET.get('month', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    qs = DailyExpense.objects.all()
    if month:
        qs = qs.filter(related_month=month)
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    total = sum(float(e.amount) for e in qs)
    count = qs.count()
    return JsonResponse({
        'ok': True,
        'month': month or '',
        'date_from': date_from,
        'date_to': date_to,
        'total': str(round(total, 2)),
        'count': count,
    })
