"""
SEO测试流程 — 列表页 + 详情页（LayUI 风格）
"""
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST, require_GET

from XiaoYingAdmin.common.http import parse_json_body, err
from XiaoYingAdmin.models.seo_domain import SeoDomain
from XiaoYingAdmin.models.seo_test_workflow import SeoTestWorkflow, SeoTestWorkflowStep

LIST_TEMPLATE = 'XiaoYingAdmin/SEO/测试流程/list.html'
DETAIL_TEMPLATE = 'XiaoYingAdmin/SEO/测试流程/detail.html'


# =============================================================================
# 页面视图
# =============================================================================

@login_required
@require_http_methods(['GET'])
def test_workflow_list_view(request):
    """测试流程列表页"""
    return render(request, LIST_TEMPLATE)


@login_required
@require_http_methods(['GET'])
def test_workflow_detail_view(request, pk):
    """测试流程详情页（步骤管理）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    return render(request, DETAIL_TEMPLATE, {'workflow': workflow})


# =============================================================================
# 测试流程 CRUD API
# =============================================================================

@csrf_exempt
@require_GET
def api_test_workflow_list(request):
    """获取所有测试流程，支持 ?sort=due & ?status=pending|success|failed & ?q= 筛选"""
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '').strip()
    status_filter = request.GET.get('status', '').strip()

    workflows = SeoTestWorkflow.objects.all()
    if q:
        workflows = workflows.filter(name__icontains=q)
    if status_filter in ('pending', 'success', 'failed'):
        workflows = workflows.filter(result=status_filter)

    data = [w.to_dict() for w in workflows]

    # 按当前步骤截止时间排序（未设置截止日期的排最后）
    if sort == 'due':
        def sort_key(w):
            due = w.get('current_due_date') or ''
            return (0 if due else 1, due)
        data.sort(key=sort_key)

    return JsonResponse({
        'code': 0,
        'data': data,
    })


@csrf_exempt
@require_POST
def api_test_workflow_create(request):
    """创建测试流程"""
    body, error = parse_json_body(request)
    if error:
        return error
    name = (body.get('name') or '').strip()
    if not name:
        return err('请填写测试流程名称')
    description = (body.get('description') or '').strip()
    domain_ids = body.get('domain_ids', [])

    workflow = SeoTestWorkflow.objects.create(
        name=name,
        description=description,
    )
    if domain_ids:
        domains = SeoDomain.objects.filter(id__in=domain_ids)
        workflow.domains.set(domains)
    return JsonResponse({'code': 0, 'data': workflow.to_dict()})


@csrf_exempt
@require_POST
def api_test_workflow_update(request, pk):
    """更新测试流程（名称、描述、域名、结果）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    body, error = parse_json_body(request)
    if error:
        return error
    name = (body.get('name') or '').strip()
    if name:
        workflow.name = name
    description = body.get('description')
    if description is not None:
        workflow.description = description.strip()
    domain_ids = body.get('domain_ids')
    if domain_ids is not None:
        domains = SeoDomain.objects.filter(id__in=domain_ids)
        workflow.domains.set(domains)
    result = body.get('result')
    if result in ('success', 'failed', 'pending'):
        workflow.result = result
    workflow.save()
    return JsonResponse({'code': 0, 'data': workflow.to_dict()})


@csrf_exempt
@require_POST
def api_test_workflow_delete(request, pk):
    """删除测试流程（级联删除步骤）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    workflow.delete()
    return JsonResponse({'code': 0})


@csrf_exempt
@require_GET
def api_test_workflow_detail(request, pk):
    """获取测试流程详情（含步骤列表）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    data = workflow.to_dict()
    data['steps'] = [s.to_dict() for s in workflow.steps.all().order_by('step_order')]
    return JsonResponse({'code': 0, 'data': data})


@csrf_exempt
@require_POST
def api_test_workflow_set_result(request, pk):
    """设置测试流程的最终结果（success / failed / pending）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    body, error = parse_json_body(request)
    if error:
        return error
    result = body.get('result', '').strip()
    if result not in ('success', 'failed', 'pending'):
        return err('无效的结果值，请使用 success / failed / pending')
    workflow.result = result
    workflow.save()
    return JsonResponse({'code': 0, 'data': workflow.to_dict()})


# =============================================================================
# 步骤 API
# =============================================================================

@csrf_exempt
@require_POST
def api_test_workflow_step_create(request, pk):
    """新增步骤（追加到最后）"""
    workflow = get_object_or_404(SeoTestWorkflow, id=pk)
    body, error = parse_json_body(request)
    if error:
        return error
    name = (body.get('name') or '').strip()
    if not name:
        return err('请填写步骤名称')
    description = (body.get('description') or '').strip()
    duration_days = int(body.get('duration_days', 1))

    # 计算下一个序号
    max_order = workflow.steps.aggregate(models.Max('step_order'))['step_order__max'] or 0
    step_order = max_order + 1

    # 第一个步骤自动设为「进行中」
    is_first = step_order == 1
    status = SeoTestWorkflowStep.StepStatus.IN_PROGRESS if is_first else SeoTestWorkflowStep.StepStatus.PENDING

    step = SeoTestWorkflowStep.objects.create(
        workflow=workflow,
        step_order=step_order,
        name=name,
        description=description,
        duration_days=max(duration_days, 1),
        status=status,
        started_at=now() if is_first else None,
    )
    return JsonResponse({'code': 0, 'data': step.to_dict()})


@csrf_exempt
@require_POST
def api_test_workflow_step_update(request, pk, step_pk):
    """更新步骤（名称、描述、天数）"""
    step = get_object_or_404(SeoTestWorkflowStep, id=step_pk, workflow_id=pk)
    body, error = parse_json_body(request)
    if error:
        return error
    name = (body.get('name') or '').strip()
    if name:
        step.name = name
    description = body.get('description')
    if description is not None:
        step.description = description.strip()
    duration_days = body.get('duration_days')
    if duration_days is not None:
        step.duration_days = max(int(duration_days), 1)
    step.save()
    return JsonResponse({'code': 0, 'data': step.to_dict()})


@csrf_exempt
@require_POST
def api_test_workflow_step_complete(request, pk, step_pk):
    """标记步骤完成 → 下一步自动变为进行中"""
    step = get_object_or_404(SeoTestWorkflowStep, id=step_pk, workflow_id=pk)
    if step.status == SeoTestWorkflowStep.StepStatus.COMPLETED:
        return err('该步骤已经完成，无需重复操作')

    # 标记当前步骤为完成
    step.status = SeoTestWorkflowStep.StepStatus.COMPLETED
    step.completed_at = now()
    step.save()

    # 激活下一步
    next_step = SeoTestWorkflowStep.objects.filter(
        workflow_id=pk,
        step_order=step.step_order + 1,
    ).first()
    if next_step:
        next_step.status = SeoTestWorkflowStep.StepStatus.IN_PROGRESS
        next_step.started_at = now()
        next_step.save()
    else:
        # 没有下一步 → 整个流程完成
        step.workflow.is_completed = True
        step.workflow.save()

    return JsonResponse({'code': 0})


@csrf_exempt
@require_POST
def api_test_workflow_step_delete(request, pk, step_pk):
    """删除步骤，后续步骤序号前移"""
    step = get_object_or_404(SeoTestWorkflowStep, id=step_pk, workflow_id=pk)
    workflow = step.workflow
    deleted_order = step.step_order
    deleted_status = step.status
    step.delete()

    # 后续步骤序号前移
    SeoTestWorkflowStep.objects.filter(
        workflow=workflow,
        step_order__gt=deleted_order,
    ).update(step_order=models.F('step_order') - 1)

    # 如果删除的是「进行中」的步骤，前移的下一个步骤自动变为进行中
    if deleted_status == SeoTestWorkflowStep.StepStatus.IN_PROGRESS:
        next_step = SeoTestWorkflowStep.objects.filter(
            workflow=workflow,
            step_order=deleted_order,
        ).first()
        if next_step and next_step.status == SeoTestWorkflowStep.StepStatus.PENDING:
            next_step.status = SeoTestWorkflowStep.StepStatus.IN_PROGRESS
            next_step.started_at = now()
            next_step.save()

    # 重新检查完成状态
    remaining = workflow.steps.count()
    if remaining == 0:
        workflow.is_completed = False
        workflow.save()
    else:
        completed = workflow.steps.filter(status=SeoTestWorkflowStep.StepStatus.COMPLETED).count()
        if completed >= remaining:
            workflow.is_completed = True
        else:
            workflow.is_completed = False
        workflow.save()

    return JsonResponse({'code': 0})


@csrf_exempt
@require_GET
def api_seo_domains_for_workflow(request):
    """获取可选域名列表（支持搜索）"""
    q = request.GET.get('q', '').strip()
    domains = SeoDomain.objects.all()
    if q:
        domains = domains.filter(domain__icontains=q)
    return JsonResponse({
        'code': 0,
        'data': [d.to_dict() for d in domains],
    })



