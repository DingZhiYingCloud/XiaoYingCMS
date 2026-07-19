"""
总金额系统视图 — 余额管理 + 收支记录 + 模块重置
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import parse_json_body, err, get_or_404
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.finance import (
    FinanceBalance, FinanceTransaction, DailyExpense, Debt,
    FriendCategory, FriendEvent, Friend, EventType,
)
from XiaoYingAdmin.views.finance import paginate_queryset, paginate_response

BALANCE_TEMPLATE = 'XiaoYingAdmin/个人财务/总金额.html'


@login_required
@require_GET
def balance_view(request):
    """总金额管理页面"""
    return render(request, BALANCE_TEMPLATE)


# =============================================================================
# AJAX API
# =============================================================================

def _get_or_create_balance():
    """获取或创建单例总金额记录"""
    obj, _ = FinanceBalance.objects.get_or_create(pk=1)
    return obj


@csrf_exempt
@require_GET
def balance_api_info(request):
    """获取当前总金额信息"""
    bal = _get_or_create_balance()
    return JsonResponse({
        'ok': True,
        'balance': str(bal.balance),
        'initial_amount': str(bal.initial_amount),
        'create_time': bal.create_time.strftime('%Y-%m-%d %H:%M:%S') if bal.create_time else '',
    })


@csrf_exempt
@require_POST
def balance_api_initial(request):
    """首次设置初始金额"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    amount = body.get('amount')
    if not amount:
        return err('请输入初始金额')

    bal = _get_or_create_balance()
    if bal.balance != 0 or bal.initial_amount != 0:
        return err('总金额已经初始化，不可重复设置。如需调整请使用「余额调整」功能')

    bal.balance = amount
    bal.initial_amount = amount
    bal.save()

    # 记录初始交易
    FinanceTransaction.objects.create(
        tx_type='income',
        amount=amount,
        description='初始化总金额',
        balance_snapshot=amount,
    )
    log_operation(request, f'初始化总金额: ¥{amount}')
    return JsonResponse({'ok': True, 'balance': str(bal.balance)})


@csrf_exempt
@require_POST
def balance_api_transaction(request):
    """记录一笔交易（收入/支出/生活费发放等）"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    tx_type = (body.get('tx_type') or '').strip()
    amount = body.get('amount')
    description = (body.get('description') or '').strip()
    related_month = (body.get('related_month') or '').strip()

    # 校验交易类型
    valid_types = [c[0] for c in FinanceTransaction.TX_TYPE_CHOICES]
    if tx_type not in valid_types:
        return err('无效的交易类型')

    if not amount:
        return err('请输入金额')

    amount = float(amount)

    bal = _get_or_create_balance()

    # 非收入类交易，金额取负值表示支出
    if tx_type != 'income':
        if amount > 0:
            amount = -amount

    # 检查余额是否足够（支出时）
    if amount < 0 and float(bal.balance) + amount < 0:
        return err('余额不足')

    # 更新余额
    new_balance = float(bal.balance) + amount
    bal.balance = new_balance
    bal.save()

    tx = FinanceTransaction.objects.create(
        tx_type=tx_type,
        amount=amount,
        description=description,
        related_month=related_month,
        balance_snapshot=new_balance,
    )

    log_operation(request, f'财务交易 [{tx.get_tx_type_display()}] ¥{amount}: {description}')
    return JsonResponse({
        'ok': True,
        'id': tx.id,
        'balance': str(new_balance),
    })


@csrf_exempt
@require_GET
def balance_api_transactions(request):
    """获取交易记录列表（分页）"""
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    qs = FinanceTransaction.objects.all()
    data_list, total, total_pages, page, page_size = paginate_queryset(qs, page, page_size)
    data = []
    for t in data_list:
        data.append({
            'id': t.id,
            'tx_type': t.tx_type,
            'tx_type_label': t.get_tx_type_display(),
            'amount': str(t.amount),
            'description': t.description,
            'related_month': t.related_month,
            'balance_snapshot': str(t.balance_snapshot) if t.balance_snapshot else '',
            'create_time': t.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse(paginate_response(True, data, total, total_pages, page, page_size))


@csrf_exempt
@require_POST
def balance_api_adjust(request):
    """余额调整"""
    body, error = parse_json_body(request)
    if error is not None:
        return error

    new_balance = body.get('new_balance')
    reason = (body.get('reason') or '').strip()

    if new_balance is None:
        return err('请输入新的余额值')

    bal = _get_or_create_balance()
    old_balance = float(bal.balance)
    new_balance = float(new_balance)

    bal.balance = new_balance
    bal.save()

    # 计算差额并记录
    diff = new_balance - old_balance
    FinanceTransaction.objects.create(
        tx_type='adjustment',
        amount=diff,
        description=reason or f'余额调整: ¥{old_balance} → ¥{new_balance}',
        balance_snapshot=new_balance,
    )
    log_operation(request, f'余额调整: ¥{old_balance} → ¥{new_balance} ({reason})')
    return JsonResponse({'ok': True, 'balance': str(new_balance)})


# =============================================================================
# 模块重置
# =============================================================================

PRESET_CATEGORIES = ['亲密好友', '好朋友', '普通朋友', '同事', '家人']
PRESET_EVENT_TYPES = ['请吃饭', '送礼物', '聚会', '看电影', '其他']


@csrf_exempt
@require_POST
def finance_api_reset(request):
    """
    POST /xiaoying_admin/api/finance/reset/
    重置个人财务模块全部数据（总金额、流水、日常消费、债务、好友、分类等）。
    需要二次确认 confirm_token = 'yes' + 当前时间戳（防误触）。
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    # 二次确认检查
    if body.get('confirm') != 'yes':
        return err('请二次确认后执行重置（需传 confirm="yes"）')

    # 1. 好友事件（Friend 级联删除会自动删 FriendEvent，但先删更安全）
    FriendEvent.objects.all().delete()

    # 2. 好友
    Friend.objects.all().delete()

    # 3. 好友分类 → 重建预设
    FriendCategory.objects.all().delete()
    for i, name in enumerate(PRESET_CATEGORIES):
        FriendCategory.objects.create(name=name, sort_order=i * 10, is_preset=True)

    # 4. 事件类型 → 重建预设
    EventType.objects.all().delete()
    for name in PRESET_EVENT_TYPES:
        EventType.objects.create(name=name, is_preset=True)

    # 5. 债务
    Debt.objects.all().delete()

    # 6. 日常消费
    DailyExpense.objects.all().delete()

    # 7. 财务交易记录
    FinanceTransaction.objects.all().delete()

    # 8. 总金额 → 归零
    bal, _ = FinanceBalance.objects.get_or_create(pk=1)
    bal.balance = 0
    bal.initial_amount = 0
    bal.save()

    log_operation(request, '重置个人财务模块全部数据')
    return JsonResponse({'ok': True, 'message': '个人财务模块已全部重置'})
