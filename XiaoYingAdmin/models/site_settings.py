from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class SiteSettings(BaseModel):
    """
    全局网站设置模型（单例模式，仅有一条记录）。

    字段说明：
      - statistics_code: 全局代码统计，文本域，可存放统计代码、第三方分析脚本等
      - is_active: 是否启用该配置

    使用方式：
      from XiaoYingAdmin.models.site_settings import SiteSettings

      # 获取唯一配置（不存在则自动创建）
      settings = SiteSettings.objects.first()
      if settings:
          code = settings.statistics_code
    """

    statistics_code = models.TextField(
        verbose_name='全局代码统计',
        blank=True,
        null=False,
        default='',
        help_text='用于存放全局统计代码、第三方分析脚本等内容，会在全站页面底部引入',
    )
    is_active = models.BooleanField(
        verbose_name='是否启用',
        default=True,
        help_text='关闭后全局统计代码将不会在页面中输出',
    )

    class Meta:
        verbose_name = '网站设置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'网站设置 v{self.pk}'
