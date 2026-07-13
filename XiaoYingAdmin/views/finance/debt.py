"""
债务管理视图 — 借入/借出 CRUD + 到期提醒
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import parse_json_body, err, get_or_404
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.finance import Debt
from XiaoYingAdmin.views.finance import paginate_queryset, paginate_response

DEBT_TEMPLATE = 'XiaoYingAdmin/个人财务/债务管理.html'


@login_required
@require_GET
def debt_view(request):
    """债务管理页面"""
    return render(request, DEBT_TEMPLATE)


# =============================================================================
# AJAX API
# =============================================================================

@csrf_exempt
@require_GET
def debt_api_list(request):
    """获取债务列表，支持方向筛选 + 分页"""
    direction = request.GET.get('direction', '')  # lend / borrow / ''(全部)
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    qs = Debt.objects.all()
    if direction in ('lend', 'borrow'):
        qs = qs.filter(direction=direction)

    data_list, total, total_pages, page, page_size = paginate_queryset(qs, page, page_size)
    data = []
    for d in data_list:
        data.append({
            'id': d.id,
            'direction': d.direction,
            'direction_label': '借出（别人欠我）' if d.direction == 'lend' else '借入（我欠别人）',
            'person_name': d.person_name,
            'amount': str(d.amount),
            'borrow_date': d.borrow_date.isoformat(),
            'due_date': d.due_date.isoformat(),
            'status': d.status,
            'reminder_days': d.reminder_days,
            'remark': d.remark,
            'create_time': d.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_time': d.updated_time.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse(paginate_response(True, data, total, total_pages, page, page_size))


@csrf_exempt
@require_POST
def debt_api_save(request):
    """创建/更新债务记录"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    debt_id = body.get('id')
    direction = (body.get('direction') or '').strip()
    person_name = (body.get('person_name') or '').strip()
    amount = body.get('amount')
    borrow_date = body.get('borrow_date')
    due_date = body.get('due_date')
    status = (body.get('status') or '').strip()
    reminder_days = body.get('reminder_days', 3)
    remark = (body.get('remark') or '').strip()

    # 参数校验
    if not person_name:
        return err('请输入对方姓名')
    if not amount:
        return err('请输入金额')
    if direction not in ('lend', 'borrow'):
        return err('请选择方向（借入/借出）')
    if not borrow_date or not due_date:
        return err('请填写借款日期和到期日期')

    if debt_id:
        debt, error_resp = get_or_404(Debt, id=debt_id)
        if error_resp:
            return error_resp
        debt.direction = direction
        debt.person_name = person_name
        debt.amount = amount
        debt.borrow_date = borrow_date
        debt.due_date = due_date
        debt.status = status or debt.status
        debt.reminder_days = reminder_days
        debt.remark = remark
        debt.save()
        log_operation(request, f'更新债务记录: {debt}')
    else:
        debt = Debt.objects.create(
            direction=direction,
            person_name=person_name,
            amount=amount,
            borrow_date=borrow_date,
            due_date=due_date,
            status=status or '待还',
            reminder_days=reminder_days,
            remark=remark,
        )
        log_operation(request, f'新增债务记录: {debt}')

    return JsonResponse({'ok': True, 'id': debt.id})


@csrf_exempt
@require_POST
def debt_api_delete(request):
    """删除债务记录"""
    body, error = parse_json_body(request)
    if error is not None:
        return error
    debt_id = body.get('id')
    if not debt_id:
        return err('缺少ID')
    debt, error_resp = get_or_404(Debt, id=debt_id)
    if error_resp:
        return error_resp
    log_operation(request, f'删除债务记录: {debt}')
    debt.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_GET
def debt_api_reminders(request):
    """获取即将到期的债务提醒列表"""
    today = date.today()
    qs = Debt.objects.filter(~Q(status='已还清'))
    reminders = []
    for d in qs:
        days_left = (d.due_date - today).days
        if 0 <= days_left <= d.reminder_days:
            reminders.append({
                'id': d.id,
                'direction': d.direction,
                'direction_label': '借出' if d.direction == 'lend' else '借入',
                'person_name': d.person_name,
                'amount': str(d.amount),
                'due_date': d.due_date.isoformat(),
                'days_left': days_left,
                'status': d.status,
            })
        elif days_left < 0:
            # 逾期
            reminders.append({
                'id': d.id,
                'direction': d.direction,
                'direction_label': '借出' if d.direction == 'lend' else '借入',
                'person_name': d.person_name,
                'amount': str(d.amount),
                'due_date': d.due_date.isoformat(),
                'days_left': days_left,
                'status': d.status,
                'overdue': True,
            })
    return JsonResponse({'ok': True, 'reminders': reminders})
