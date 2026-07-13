"""
个人财务管理 —— 债务、总金额、消费记录、好友管理

包含：
  - Debt              债务记录（借入/借出）
  - FinanceBalance     总金额系统余额
  - FinanceTransaction 财务交易记录（生活费发放、其他收支统一入口）
  - DailyExpense       日消费记录
  - FriendCategory     好友分类
  - EventType          事件类型预设
  - Friend             好友
  - FriendEvent        好友关联事件
"""

from django.db import models
from XiaoYingAdmin.common.base import BaseModel


class Debt(BaseModel):
    """
    债务记录（借入/借出同一张表，用 direction 区分）。

    direction:
      - lend   -> 我借给别人（别人欠我）
      - borrow -> 我向别人借（我欠别人）

    status 为自定义文本字段，用户可自由填写如「待还」「已还清」「逾期中」等。
    """

    DIRECTION_CHOICES = [
        ('lend', '借出（别人欠我）'),
        ('borrow', '借入（我欠别人）'),
    ]

    direction = models.CharField('方向', max_length=10, choices=DIRECTION_CHOICES, db_index=True)
    person_name = models.CharField('对方姓名', max_length=100, help_text='债务人/债权人姓名')
    amount = models.DecimalField('金额', max_digits=12, decimal_places=2)
    borrow_date = models.DateField('借款日期')
    due_date = models.DateField('到期日期')
    status = models.CharField('状态', max_length=50, default='待还')
    reminder_days = models.IntegerField('提前提醒天数', default=3, help_text='到期前多少天在后台提醒')
    remark = models.TextField('备注', blank=True, default='')

    class Meta:
        verbose_name = '债务记录'
        verbose_name_plural = '债务记录'
        db_table = 'finance_debt'
        ordering = ['-due_date']

    def __str__(self):
        prefix = '借出' if self.direction == 'lend' else '借入'
        return f'{prefix} | {self.person_name} | ¥{self.amount} | {self.status}'


class FinanceBalance(BaseModel):
    """
    总金额系统 —— 单例模式，仅保留一条当前总余额记录。

    后续可通过新增 FinanceTransaction 类型来扩展各种收支业务。
    """
    balance = models.DecimalField('当前总金额', max_digits=14, decimal_places=2, default=0)
    initial_amount = models.DecimalField('初始金额', max_digits=14, decimal_places=2, default=0,
                                         help_text='第一次设置时的初始值，仅用于参考')

    class Meta:
        verbose_name = '总金额'
        verbose_name_plural = '总金额'
        db_table = 'finance_balance'
        # 在 admin 或其他地方可以强制单例，但这里不设硬限制（由业务层保证）

    def __str__(self):
        return f'总金额: ¥{self.balance}'


class FinanceTransaction(BaseModel):
    """
    财务交易记录 —— 所有资金变动的统一入口。

    类型（tx_type）说明：
      - monthly_allowance   -> 每月发放生活费
      - server_renewal      -> 服务器续费
      - red_packet          -> 红包支出
      - reward              -> 奖励某人
      - income              -> 其他收入（如充值总金额）
      - expense             -> 其他支出
      - adjustment          -> 余额调整（手动修正）
      - （后续可按需扩展）
    """

    TX_TYPE_CHOICES = [
        ('income', '收入（充入总金额）'),
        ('monthly_allowance', '生活费发放'),
        ('server_renewal', '服务器续费'),
        ('red_packet', '红包支出'),
        ('reward', '奖励支出'),
        ('expense', '其他支出'),
        ('adjustment', '余额调整'),
    ]

    tx_type = models.CharField('交易类型', max_length=30, choices=TX_TYPE_CHOICES, db_index=True)
    amount = models.DecimalField('金额', max_digits=12, decimal_places=2,
                                 help_text='正数=收入/发放，负数=支出')
    description = models.TextField('描述', blank=True, default='')
    related_month = models.CharField('关联月份', max_length=7, blank=True, default='',
                                     help_text='生活费专用，格式 YYYY-MM')
    balance_snapshot = models.DecimalField('交易后余额快照', max_digits=14, decimal_places=2,
                                           null=True, blank=True)

    class Meta:
        verbose_name = '财务交易'
        verbose_name_plural = '财务交易'
        db_table = 'finance_transaction'
        ordering = ['-create_time']

    def __str__(self):
        return f'[{self.get_tx_type_display()}] ¥{self.amount} | {self.create_time.strftime("%Y-%m-%d %H:%M")}'


class DailyExpense(BaseModel):
    """
    日消费记录 —— 记录每天从生活费中花掉的每一笔钱。

    media_file 支持上传图片/视频文件（存储于 MEDIA_ROOT/finance/expense/ 目录下）。
    """
    expense_date = models.DateField('消费日期', db_index=True)
    expense_time = models.TimeField('消费时间', blank=True, null=True)
    title = models.CharField('标题', max_length=200)
    description = models.TextField('描述', blank=True, default='')
    amount = models.DecimalField('金额', max_digits=10, decimal_places=2)
    media_file = models.FileField('图片/视频', upload_to='finance/expense/%Y/%m/',
                                  blank=True, null=True,
                                  help_text='支持图片或视频文件')
    related_month = models.CharField('关联月份', max_length=7, blank=True, default='',
                                     help_text='格式 YYYY-MM，关联到当月生活费')

    class Meta:
        verbose_name = '日消费记录'
        verbose_name_plural = '日消费记录'
        db_table = 'finance_daily_expense'
        ordering = ['-expense_date', '-expense_time']

    def __str__(self):
        return f'{self.expense_date} {self.title} ¥{self.amount}'


class FriendCategory(BaseModel):
    """
    好友分类（预设 + 自定义）。

    is_preset=True 表示系统预设分类（不可删除，可编辑名称）。
    预设种子：亲密好友、好朋友、普通朋友、同事、家人。
    """
    name = models.CharField('分类名称', max_length=50)
    sort_order = models.IntegerField('排序', default=0)
    is_preset = models.BooleanField('是否预设', default=False)

    class Meta:
        verbose_name = '好友分类'
        verbose_name_plural = '好友分类'
        db_table = 'finance_friend_category'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name


class EventType(BaseModel):
    """
    事件类型标签（预设 + 自定义）。

    预设种子：请吃饭、送礼物、聚会、看电影、其他。
    """
    name = models.CharField('类型名称', max_length=50)
    is_preset = models.BooleanField('是否预设', default=False)

    class Meta:
        verbose_name = '事件类型'
        verbose_name_plural = '事件类型'
        db_table = 'finance_event_type'
        ordering = ['id']

    def __str__(self):
        return self.name


class Friend(BaseModel):
    """
    好友。
    """
    category = models.ForeignKey(
        FriendCategory, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='分类'
    )
    name = models.CharField('姓名', max_length=100)
    remark = models.TextField('备注', blank=True, default='')

    class Meta:
        verbose_name = '好友'
        verbose_name_plural = '好友'
        db_table = 'finance_friend'
        ordering = ['name']

    def __str__(self):
        return self.name


class FriendEvent(BaseModel):
    """
    好友关联事件 —— 记录与好友相关的活动。

    status: pending / todo / done
    """
    STATUS_CHOICES = [
        ('pending', '未开始'),
        ('todo', '进行中'),
        ('done', '已完成'),
    ]

    friend = models.ForeignKey(
        Friend, on_delete=models.CASCADE, related_name='events',
        verbose_name='好友'
    )
    event_type = models.ForeignKey(
        EventType, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='事件类型'
    )
    custom_type_name = models.CharField('自定义类型', max_length=50, blank=True, default='',
                                        help_text='如果预设类型不够用，可在此自由填写')
    title = models.CharField('标题', max_length=200)
    description = models.TextField('描述', blank=True, default='')
    event_date = models.DateField('事件日期', null=True, blank=True)
    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES, default='todo')

    class Meta:
        verbose_name = '好友事件'
        verbose_name_plural = '好友事件'
        db_table = 'finance_friend_event'
        ordering = ['-event_date', '-create_time']

    def __str__(self):
        return f'{self.friend.name} - {self.title}'
