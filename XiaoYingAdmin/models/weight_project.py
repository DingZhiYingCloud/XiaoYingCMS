"""
权重页面项目模型 — 管理独立的 Django 子项目。
每个项目拥有独立数据库，可在小影CMS中启动/停止/重启。
"""
from django.db import models
from XiaoYingAdmin.common.base import BaseModel
from XiaoYingAdmin.models.user import User


class WeightProject(BaseModel):
    class ProjectType(models.TextChoices):
        MANUAL = 'manual', '手动准备'
        AUTO = 'auto', '系统创建'

    class Status(models.TextChoices):
        STOPPED = 'stopped', '已停止'
        RUNNING = 'running', '运行中'
        ERROR = 'error', '异常'

    name = models.CharField('项目名称', max_length=128)
    description = models.TextField('项目描述', blank=True, default='')
    project_type = models.CharField(
        '项目类型', max_length=20,
        choices=ProjectType.choices, default=ProjectType.MANUAL,
        help_text='手动准备：你自行准备好项目代码；系统创建：由小影CMS自动创建基础项目',
    )
    project_path = models.CharField(
        '项目目录路径', max_length=512, blank=True, default='',
        help_text='项目代码在服务器上的存放路径（模式A必填）',
    )
    port = models.IntegerField('运行端口', default=9000)
    status = models.CharField(
        '运行状态', max_length=20,
        choices=Status.choices, default=Status.STOPPED,
    )
    pid = models.IntegerField('进程PID', null=True, blank=True)
    auto_start = models.BooleanField('开机自启', default=False)
    auto_backup_threshold = models.IntegerField(
        '日志自动备份阈值', default=0,
        help_text='控制台日志行数达到此值时自动备份并清空。0=关闭自动备份',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='创建者',
    )

    class Meta:
        db_table = 'weight_project'
        verbose_name = '权重页面项目'
        verbose_name_plural = verbose_name
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'project_type': self.project_type,
            'project_type_display': self.get_project_type_display(),
            'project_path': self.project_path,
            'port': self.port,
            'status': self.status,
            'status_display': self.get_status_display(),
            'pid': self.pid,
            'auto_start': self.auto_start,
            'auto_backup_threshold': self.auto_backup_threshold,
            'created_by_id': self.created_by_id,
            'created_by': str(self.created_by) if self.created_by else '',
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else '',
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else '',
        }
