"""
自动备份功能 + 域名SEO记录树形展示 测试

运行方式: python manage.py test XiaoYingAdmin.tests --verbosity=2
"""
import json
import os
import shutil
import tempfile

from django.conf import settings
from django.test import TestCase, RequestFactory

from XiaoYingAdmin.models.operation_log import OperationLog
from XiaoYingAdmin.models.site_settings import SiteSettings
from XiaoYingAdmin.models.seo_domain import SeoDomain
from XiaoYingAdmin.models.spider_log import SpiderAccessLog
from XiaoYingAdmin.utils.backup import (
    check_and_auto_backup,
    get_backup_dir,
    list_backup_files,
)
from XiaoYingAdmin.views.seo.domain_records import api_seo_domains_tree


class TestCheckAndAutoBackup(TestCase):
    """测试 check_and_auto_backup 函数"""

    def setUp(self):
        # 使用临时目录作为备份目录
        self.temp_dir = tempfile.mkdtemp()
        self._orig_backup_dir = getattr(settings, 'BACKUP_DIR', None)
        settings.BACKUP_DIR = self.temp_dir

        # 确保 SiteSettings 存在
        SiteSettings.objects.get_or_create(pk=1)

    def tearDown(self):
        # 清理临时目录
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self._orig_backup_dir is not None:
            settings.BACKUP_DIR = self._orig_backup_dir

    def _create_spider_logs(self, count: int):
        """批量创建蜘蛛日志"""
        for i in range(count):
            SpiderAccessLog.objects.create(
                ip='127.0.0.1',
                user_agent=f'test-bot-{i}',
                path=f'/test/path/{i}',
            )

    def _create_operation_logs(self, count: int):
        """批量创建操作日志"""
        for i in range(count):
            OperationLog.objects.create(
                username=f'testuser-{i}',
                action='create',
                target_type='Test',
                target_id=str(i),
                target_repr=f'测试操作 {i}',
            )

    # ================================================================
    # 蜘蛛日志 - auto_backup_spider_threshold
    # ================================================================

    def test_spider_threshold_zero_no_backup(self):
        """阈值=0 时，不触发自动备份"""
        self._create_spider_logs(10)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_spider_threshold = 0
        ss.save()

        check_and_auto_backup(SpiderAccessLog, 'spider_logs', 'auto_backup_spider_threshold')

        self.assertEqual(SpiderAccessLog.objects.count(), 10,
                         '阈值=0 不应删除日志')
        self.assertEqual(len(list_backup_files('spider_logs')), 0,
                         '阈值=0 不应生成备份')

    def test_spider_threshold_not_reached(self):
        """未达到阈值时，不触发自动备份"""
        self._create_spider_logs(5)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_spider_threshold = 10
        ss.save()

        check_and_auto_backup(SpiderAccessLog, 'spider_logs', 'auto_backup_spider_threshold')

        self.assertEqual(SpiderAccessLog.objects.count(), 5,
                         '未达阈值不应删除数据')

    def test_spider_threshold_exact_match(self):
        """日志数刚好等于阈值时，触发自动备份"""
        self._create_spider_logs(10)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_spider_threshold = 10
        ss.save()

        check_and_auto_backup(SpiderAccessLog, 'spider_logs', 'auto_backup_spider_threshold')

        self.assertEqual(SpiderAccessLog.objects.count(), 0,
                         '达到阈值应清空日志')
        files = list_backup_files('spider_logs')
        self.assertEqual(len(files), 1,
                         '应生成一个备份文件')
        self.assertGreater(files[0]['size_bytes'], 0,
                           '备份文件不应为空')

    def test_spider_threshold_exceeded(self):
        """日志数超过阈值时，也应触发自动备份"""
        self._create_spider_logs(15)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_spider_threshold = 10
        ss.save()

        check_and_auto_backup(SpiderAccessLog, 'spider_logs', 'auto_backup_spider_threshold')

        self.assertEqual(SpiderAccessLog.objects.count(), 0,
                         '超过阈值应清空日志')
        files = list_backup_files('spider_logs')
        self.assertEqual(len(files), 1,
                         '应生成一个备份文件')

    # ================================================================
    # 操作日志 - auto_backup_operation_threshold
    # ================================================================

    def test_operation_threshold_zero_no_backup(self):
        """阈值=0 时，不触发自动备份"""
        self._create_operation_logs(10)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_operation_threshold = 0
        ss.save()

        check_and_auto_backup(OperationLog, 'op_logs', 'auto_backup_operation_threshold')

        self.assertEqual(OperationLog.objects.count(), 10,
                         '阈值=0 不应删除日志')
        self.assertEqual(len(list_backup_files('op_logs')), 0,
                         '阈值=0 不应生成备份')

    def test_operation_threshold_exact_match(self):
        """操作日志数刚好等于阈值时，触发自动备份"""
        self._create_operation_logs(10)
        ss = SiteSettings.objects.get(pk=1)
        ss.auto_backup_operation_threshold = 10
        ss.save()

        check_and_auto_backup(OperationLog, 'op_logs', 'auto_backup_operation_threshold')

        self.assertEqual(OperationLog.objects.count(), 0,
                         '达到阈值应清空操作日志')
        files = list_backup_files('op_logs')
        self.assertEqual(len(files), 1,
                         '应生成一个操作日志备份文件')


class TestSeoDomainTree(TestCase):
    """测试域名SEO记录的树形展示 API"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_subdomains_with_virtual_root_appear_in_tree(self):
        """
        复现 bug：多个子域名共享一个虚拟根域名时，树形 API 不显示这些域名。

        场景：同步了两个域名 m.web-apply-whatsapp.com.cn 和
        www.web-apply-whatsapp.com.cn，group_domains_by_root 会自动推断
        虚拟根域名 web-apply-whatsapp.com.cn，但该域名不在 SeoDomain 表中，
        导致树形 API 跳过整个分组。
        """
        # 创建两个子域名（模拟用户通过批量导入 zip 上传的）
        SeoDomain.objects.create(
            domain='m.web-apply-whatsapp.com.cn',
            domain_type='root',
            remark='来自批量导入',
        )
        SeoDomain.objects.create(
            domain='www.web-apply-whatsapp.com.cn',
            domain_type='root',
            remark='来自批量导入',
        )

        # 调用树形 API
        request = self.factory.get('/xiaoying_admin/api/seo/domains/tree/')
        response = api_seo_domains_tree(request)
        data = json.loads(response.content)

        self.assertTrue(data['ok'], f'API 应返回 ok=True，实际: {data}')

        # 检查 tree 中包含这两个域名
        all_domains_in_tree = set()
        for node in data['tree']:
            all_domains_in_tree.add(node['domain'])
            for child in node.get('children', []):
                all_domains_in_tree.add(child['domain'])

        self.assertIn(
            'm.web-apply-whatsapp.com.cn',
            all_domains_in_tree,
            f'树中应包含 m.web-apply-whatsapp.com.cn，实际树节点: {all_domains_in_tree}',
        )
        self.assertIn(
            'www.web-apply-whatsapp.com.cn',
            all_domains_in_tree,
            f'树中应包含 www.web-apply-whatsapp.com.cn，实际树节点: {all_domains_in_tree}',
        )

    def test_single_subdomain_works(self):
        """单个子域名（没有虚拟根域名）应正常显示"""
        SeoDomain.objects.create(
            domain='m.web-apply-whatsapp.com.cn',
            domain_type='root',
        )

        request = self.factory.get('/xiaoying_admin/api/seo/domains/tree/')
        response = api_seo_domains_tree(request)
        data = json.loads(response.content)

        self.assertTrue(data['ok'])
        all_domains_in_tree = set()
        for node in data['tree']:
            all_domains_in_tree.add(node['domain'])
            for child in node.get('children', []):
                all_domains_in_tree.add(child['domain'])

        self.assertIn('m.web-apply-whatsapp.com.cn', all_domains_in_tree)
