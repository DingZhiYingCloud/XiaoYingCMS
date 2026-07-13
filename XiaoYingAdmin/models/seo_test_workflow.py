"""
SEO测试流程 — 创建一个多步骤的测试计划，跟踪每个域名的测试进度。
"""

from datetime import timedelta

from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class SeoTestWorkflow(BaseModel):
    """测试流程 — 包含多个步骤和多个关联域名。"""

    class WorkflowResult(models.TextChoices):
        PENDING = 'pending', '进行中'
        SUCCESS = 'success', '成功'
        FAILED = 'failed', '失败'

    name = models.CharField('测试流程名称', max_length=255, help_text='如「蜘蛛池效果测试」')
    description = models.TextField('描述', blank=True, default='', help_text='对这个测试流程的说明')
    domains = models.ManyToManyField(
        'SeoDomain',
        related_name='test_workflows',
        verbose_name='关联域名',
        blank=True,
        help_text='参与此测试的域名（从SEO域名中选择）',
    )
    is_completed = models.BooleanField('是否完成', default=False)
    result = models.CharField(
        '测试结果',
        max_length=20,
        choices=WorkflowResult.choices,
        default=WorkflowResult.PENDING,
        help_text='整个测试流程的最终结果',
    )

    class Meta:
        db_table = 'seo_test_workflow'
        verbose_name = 'SEO测试流程'
        verbose_name_plural = 'SEO测试流程'
        ordering = ['-create_time']

    def __str__(self):
        return self.name

    def to_dict(self) -> dict:
        steps = self.steps.all().order_by('step_order')
        completed_count = steps.filter(status='completed').count()
        total_count = steps.count()
        # 查找当前进行中步骤的截止日期
        active_step = steps.filter(status='in_progress').first()
        current_due_date = ''
        current_step_name = ''
        if active_step and active_step.started_at and active_step.duration_days:
            due = active_step.started_at + timedelta(days=active_step.duration_days)
            current_due_date = due.isoformat()
            current_step_name = active_step.name
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'domain_count': self.domains.count(),
            'domains': [d.to_dict() for d in self.domains.all()],
            'total_steps': total_count,
            'completed_steps': completed_count,
            'is_completed': self.is_completed,
            'result': self.result,
            'result_label': self.get_result_display(),
            'current_step_name': current_step_name,
            'current_due_date': current_due_date,
            'create_time': self.create_time.isoformat() if self.create_time else '',
            'updated_time': self.updated_time.isoformat() if self.updated_time else '',
        }


class SeoTestWorkflowStep(BaseModel):
    """测试流程的单个步骤。"""

    class StepStatus(models.TextChoices):
        PENDING = 'pending', '未开始'
        IN_PROGRESS = 'in_progress', '进行中'
        COMPLETED = 'completed', '已完成'

    workflow = models.ForeignKey(
        'SeoTestWorkflow',
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='所属流程',
    )
    step_order = models.IntegerField('步骤序号', help_text='步骤的执行顺序，从 1 开始')
    name = models.CharField('步骤名称', max_length=255, help_text='如「上传蜘蛛池」')
    description = models.TextField('操作描述', blank=True, default='', help_text='详细说明这一步需要做什么')
    duration_days = models.IntegerField('需要天数', default=1, help_text='此步骤预计需要的天数，用于计算截止日期')
    status = models.CharField(
        '状态',
        max_length=20,
        choices=StepStatus.choices,
        default=StepStatus.PENDING,
    )
    started_at = models.DateTimeField('开始时间', null=True, blank=True, help_text='步骤变为进行中的时间')
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        db_table = 'seo_test_workflow_step'
        verbose_name = '测试步骤'
        verbose_name_plural = '测试步骤'
        ordering = ['step_order']
        unique_together = [['workflow', 'step_order']]

    def __str__(self):
        return f'步骤{self.step_order}: {self.name}'

    def to_dict(self) -> dict:
        # 计算截止日期：开始时间 + 需要天数
        due_date = None
        if self.started_at and self.duration_days:
            due_date = (self.started_at + timedelta(days=self.duration_days)).isoformat()
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'step_order': self.step_order,
            'name': self.name,
            'description': self.description,
            'duration_days': self.duration_days,
            'status': self.status,
            'status_label': self.get_status_display(),
            'started_at': self.started_at.isoformat() if self.started_at else '',
            'due_date': due_date or '',
            'completed_at': self.completed_at.isoformat() if self.completed_at else '',
            'create_time': self.create_time.isoformat() if self.create_time else '',
        }
