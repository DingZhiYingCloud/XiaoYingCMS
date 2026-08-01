"""
友情链接模型 — 自定义友情链接配置。

在单页面管理列表中维护，用于为生成的页面添加友情链接。
仅需填写标题和 URL 两个字段。
"""

from django.db import models

from XiaoYingAdmin.common.base import BaseModel


class FriendLink(BaseModel):
    """自定义友情链接"""

    title = models.CharField(
        '链接标题',
        max_length=128,
        help_text='友情链接的显示标题',
    )
    url = models.CharField(
        '链接 URL',
        max_length=512,
        help_text='友情链接的跳转地址，如 https://example.com',
    )

    class Meta:
        verbose_name = '友情链接'
        verbose_name_plural = verbose_name
        ordering = ['-create_time']

    def __str__(self):
        return self.title

    def to_dict(self) -> dict:
        """序列化为前端所需字典。"""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        }
