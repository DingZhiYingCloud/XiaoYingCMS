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


class TestBuildDomainHierarchy(TestCase):
    """测试 build_domain_hierarchy 多层级树构建"""

    def test_two_levels(self):
        """二级域名结构：a.com + www.a.com"""
        from XiaoYingAdmin.utils.domain_utils import build_domain_hierarchy
        result = build_domain_hierarchy(['a.com', 'www.a.com'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['domain'], 'a.com')
        self.assertEqual(len(result[0]['children']), 1)
        self.assertEqual(result[0]['children'][0]['domain'], 'www.a.com')

    def test_three_levels(self):
        """三级域名结构：a.com > www.a.com > sub.www.a.com"""
        from XiaoYingAdmin.utils.domain_utils import build_domain_hierarchy
        result = build_domain_hierarchy(['a.com', 'www.a.com', 'sub.www.a.com'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['domain'], 'a.com')
        self.assertEqual(len(result[0]['children']), 1)
        self.assertEqual(result[0]['children'][0]['domain'], 'www.a.com')
        self.assertEqual(len(result[0]['children'][0]['children']), 1)
        self.assertEqual(
            result[0]['children'][0]['children'][0]['domain'],
            'sub.www.a.com',
        )

    def test_four_levels(self):
        """四级域名结构：a.com > www.a.com > sub.www.a.com > deep.sub.www.a.com"""
        from XiaoYingAdmin.utils.domain_utils import build_domain_hierarchy
        result = build_domain_hierarchy([
            'a.com', 'www.a.com', 'sub.www.a.com', 'deep.sub.www.a.com',
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['domain'], 'a.com')
        # 追溯最深层的域名
        deepest = result[0]['children'][0]['children'][0]['children'][0]
        self.assertEqual(deepest['domain'], 'deep.sub.www.a.com')

    def test_multiple_roots(self):
        """多根域名混合"""
        from XiaoYingAdmin.utils.domain_utils import build_domain_hierarchy
        result = build_domain_hierarchy([
            'a.com', 'www.a.com', 'b.com', 'api.b.com',
        ])
        self.assertEqual(len(result), 2)
        # 按 domain 排序
        result.sort(key=lambda n: n['domain'])
        self.assertEqual(result[0]['domain'], 'a.com')
        self.assertEqual(len(result[0]['children']), 1)
        self.assertEqual(result[1]['domain'], 'b.com')
        self.assertEqual(len(result[1]['children']), 1)


class TestSeoDomainTreeMultiLevel(TestCase):
    """测试多层级域名树的 API 返回"""

    def setUp(self):
        self.factory = RequestFactory()

    def _collect_all_domains(self, nodes):
        """递归收集树中所有域名字符串"""
        result = set()
        for node in nodes:
            result.add(node['domain'])
            if node.get('children'):
                result.update(self._collect_all_domains(node['children']))
        return result

    def _has_hierarchy(self, nodes, parent_domain, child_domain):
        """检查 parent_domain 下是否有直接的 child_domain 子节点"""
        for node in nodes:
            if node['domain'] == parent_domain and node.get('children'):
                for child in node['children']:
                    if child['domain'] == child_domain:
                        return True
                # 递归检查更深层
                for child in node['children']:
                    if self._has_hierarchy([child], parent_domain, child_domain):
                        return True
            elif node.get('children'):
                if self._has_hierarchy(node['children'], parent_domain, child_domain):
                    return True
        return False

    def test_multi_level_tree(self):
        """2级+3级+4级域名混合的树形展示"""
        # 根域名
        SeoDomain.objects.create(domain='example.com', domain_type='root')
        SeoDomain.objects.create(domain='test.org', domain_type='root')
        # 二级域名
        SeoDomain.objects.create(domain='www.example.com', domain_type='multi')
        SeoDomain.objects.create(domain='api.example.com', domain_type='multi')
        # 三级域名
        SeoDomain.objects.create(domain='sub.www.example.com', domain_type='multi')
        # 四级域名
        SeoDomain.objects.create(
            domain='deep.sub.www.example.com', domain_type='multi',
        )

        request = self.factory.get('/xiaoying_admin/api/seo/domains/tree/')
        response = api_seo_domains_tree(request)
        data = json.loads(response.content)
        self.assertTrue(data['ok'])

        # 所有域名都存在
        all_domains = self._collect_all_domains(data['tree'])
        for d in ['example.com', 'test.org', 'www.example.com',
                   'api.example.com', 'sub.www.example.com',
                   'deep.sub.www.example.com']:
            self.assertIn(d, all_domains, f'{d} 应在树中')

        # 检查层级结构：example.com is root
        example_root = None
        for node in data['tree']:
            if node['domain'] == 'example.com':
                example_root = node
                break
        self.assertIsNotNone(example_root, 'example.com 应作为根节点')
        self.assertIsNotNone(example_root['children'], 'example.com 应有子节点')

        # www.example.com 在 example.com 下
        www = None
        for child in example_root['children']:
            if child['domain'] == 'www.example.com':
                www = child
                break
        self.assertIsNotNone(www, 'www.example.com 应在 example.com 下')

        # sub.www.example.com 在 www.example.com 下
        sub = None
        for child in www['children']:
            if child['domain'] == 'sub.www.example.com':
                sub = child
                break
        self.assertIsNotNone(sub, 'sub.www.example.com 应在 www.example.com 下')

        # deep.sub.www.example.com 在 sub.www.example.com 下
        deep = None
        for child in sub['children']:
            if child['domain'] == 'deep.sub.www.example.com':
                deep = child
                break
        self.assertIsNotNone(
            deep,
            'deep.sub.www.example.com 应在 sub.www.example.com 下',
        )

    def test_virtual_root_two_levels(self):
        """虚拟根域名下仍然保留多层级结构"""
        # 创建两级子域名，但根域名不存在
        SeoDomain.objects.create(domain='www.example.com', domain_type='multi')
        SeoDomain.objects.create(domain='api.example.com', domain_type='multi')

        request = self.factory.get('/xiaoying_admin/api/seo/domains/tree/')
        response = api_seo_domains_tree(request)
        data = json.loads(response.content)
        self.assertTrue(data['ok'])

        all_domains = self._collect_all_domains(data['tree'])
        for d in ['www.example.com', 'api.example.com']:
            self.assertIn(d, all_domains, f'{d} 应在树中')
