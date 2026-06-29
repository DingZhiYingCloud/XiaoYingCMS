"""
AI 提示词模型 — 管理页面生成所使用的提示词。

设计要点：
  - 提示词按 category（类别）分组，例如 "page_generation"
  - 同 category 下的多个记录代表不同版本；只有 is_active=True 且 version 最大的会被使用
  - 创建时自动 version+1，更新内容后保存即递增
  - 字段可扩展：未来可加 tags / variables / example_input 等

使用示例：
  from XiaoYingAdmin.models.prompt import Prompt

  prompt_text = Prompt.get_active_content('page_generation')
"""

from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class Prompt(BaseModel):
    """
    提示词记录。

    同一 category 下可能存在多条历史版本；当前生效的提示词由
    `Prompt.get_active_content()` 选取（is_active=True, version 最大）。
    """

    CATEGORY_CHOICES = (
        ('page_generation', '页面生成'),
        ('page_optimization', '页面优化'),
        ('custom', '自定义'),
    )

    category = models.CharField(
        '提示词分类',
        max_length=64,
        choices=CATEGORY_CHOICES,
        default='page_generation',
        db_index=True,
        help_text='按用途分组，调用时按分类查找',
    )
    name = models.CharField(
        '提示词名称',
        max_length=128,
        help_text='人类可读的名称，如"通用页面生成 v3"',
    )
    content = models.TextField(
        '提示词内容',
        help_text='完整的提示词文本，会作为 system_prompt 发送给 AI',
    )
    version = models.PositiveIntegerField(
        '版本号',
        default=1,
        help_text='同一 category 下递增；创建时自动 = max+1',
    )
    is_active = models.BooleanField(
        '是否启用',
        default=True,
        help_text='关闭后该提示词不会被 AI 调用使用',
    )
    description = models.TextField(
        '变更说明',
        blank=True,
        default='',
        help_text='本次更新的说明，例如"调整了输出格式要求"',
    )

    class Meta:
        verbose_name = '提示词'
        verbose_name_plural = verbose_name
        ordering = ['category', '-version']
        indexes = [
            models.Index(fields=['category', 'is_active', '-version']),
        ]

    def __str__(self):
        return f'[{self.get_category_display()}] {self.name} v{self.version}'

    def to_dict(self) -> dict:
        """序列化为前端所需的字典（列表与详情共用同一结构）。"""
        from XiaoYingAdmin.common.http import fmt_dt

        return {
            'id': self.id,
            'category': self.category,
            'category_display': self.get_category_display(),
            'name': self.name,
            'content': self.content,
            'version': self.version,
            'is_active': self.is_active,
            'description': self.description,
            'create_time': fmt_dt(self.create_time),
            'update_time': fmt_dt(self.updated_time),
        }

    def save(self, *args, **kwargs):
        """创建时自动设置 version = 同分类最大版本 + 1。"""
        if not self.pk:
            max_version = (
                Prompt.objects
                .filter(category=self.category)
                .aggregate(models.Max('version'))['version__max']
            ) or 0
            self.version = max_version + 1
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls, category: str = 'page_generation'):
        """获取指定分类下当前生效的提示词（is_active=True, version 最大）。"""
        return (
            cls.objects
            .filter(category=category, is_active=True)
            .order_by('-version')
            .first()
        )

    @classmethod
    def get_all_active(cls, category: str = 'page_generation'):
        """
        获取指定分类下所有启用的提示词（is_active=True, 按 version 降序）。
        返回 list[Prompt]。
        """
        return list(
            cls.objects
            .filter(category=category, is_active=True)
            .order_by('-version')
        )

    @classmethod
    def get_active_content(cls, category: str = 'page_generation') -> str:
        """
        获取指定分类下当前生效的提示词文本。

        若数据库中无提示词记录，返回内置默认提示词（保证 AI 调用不会因为空提示词失败）。
        """
        prompt = cls.get_active(category)
        if prompt is not None:
            return prompt.content
        return DEFAULT_PAGE_GENERATION_PROMPT

    @classmethod
    def get_all_active_contents(cls, category: str = 'page_generation') -> list[dict]:
        """
        获取所有活跃提示词，返回 system_prompt 条目列表。

        策略（按优先级排列）：
          1. 如果有任意分类（不限 category）is_active=True 的提示词 → 全部返回
          2. 全部没有 → 返回内置默认提示词（兜底）

        每个条目: {"role": "system", "content": "..."}
        """
        prompts = cls.objects.filter(is_active=True).order_by('-version')
        if prompts.exists():
            return [{'role': 'system', 'content': p.content} for p in prompts]
        return [{'role': 'system', 'content': DEFAULT_PAGE_GENERATION_PROMPT}]


# 内置默认提示词 — 仅在数据库中没有任何提示词时使用
DEFAULT_PAGE_GENERATION_PROMPT = """你是一个专业的前端工程师与 UI 设计师。
请根据用户的需求，生成一个完整、可直接运行的 HTML 页面。

要求：
1. 使用 LayUI + FontAwesome 实现样式
2. 布局合理、配色协调
3. 支持响应式（适配桌面和移动端）
4. 所有代码必须完整可用，不要省略
5. 使用中文文案
6. 页面头部 <!DOCTYPE html> 完整保留
7. 不要返回任何额外说明，只返回 HTML 代码
"""
