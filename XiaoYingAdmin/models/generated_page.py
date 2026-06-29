"""
已保存的生成页面 — 每次 AI 生成完成后自动保存。

每次 AI 生成完 HTML 后，系统会再次调用 AI 总结出一个简短页面名称
（如"爱思助手"），然后以该名称保存到本表。
"""

from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class GeneratedPage(BaseModel):
    """
    已保存的 AI 生成页面。
    """

    name = models.CharField(
        '页面名称',
        max_length=128,
        help_text='AI 总结出的简短名称，如"爱思助手"',
    )
    html_content = models.TextField(
        'HTML 内容',
        help_text='完整的生成 HTML',
    )
    task_id = models.UUIDField(
        '关联任务 ID',
        db_index=True,
        help_text='生成该页面的 PageGenerationTask.task_id',
    )
    input_content = models.TextField(
        '用户输入',
        blank=True,
        default='',
        help_text='用户提交的原始需求描述',
    )
    domain = models.CharField(
        '使用域名',
        max_length=255,
        null=True,
        blank=True,
        default=None,
        unique=True,
        help_text='该页面绑定的域名，如"domain.com"。全局唯一，只能有一条记录占用。',
    )

    class Meta:
        verbose_name = '已保存页面'
        verbose_name_plural = verbose_name
        ordering = ['-create_time']

    def __str__(self):
        return self.name

    def to_dict(self, *, with_html: bool = False) -> dict:
        """
        序列化为前端所需的字典。

        参数：
          with_html: 是否包含完整 HTML 内容（列表页不需要，详情页需要）
        """
        from XiaoYingAdmin.common.http import fmt_dt, DATETIME_FMT_SHORT

        data = {
            'id': self.id,
            'name': self.name,
            'input_content': self.input_content,
            'domain': self.domain,
            'create_time': fmt_dt(self.create_time, DATETIME_FMT_SHORT),
        }
        if with_html:
            data['html_content'] = self.html_content
        return data
