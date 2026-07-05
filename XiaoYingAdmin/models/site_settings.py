from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class SiteSettings(BaseModel):
    """
    全局网站设置模型（单例模式，仅有一条记录）。
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
    auto_backup_spider_threshold = models.IntegerField(
        verbose_name='蜘蛛日志自动备份阈值',
        default=0,
        help_text='蜘蛛日志记录数达到此值时自动备份并清空。0=关闭自动备份',
    )
    auto_backup_operation_threshold = models.IntegerField(
        verbose_name='操作日志自动备份阈值',
        default=0,
        help_text='操作日志记录数达到此值时自动备份并清空。0=关闭自动备份',
    )

    class Meta:
        verbose_name = '网站设置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'网站设置 v{self.pk}'
