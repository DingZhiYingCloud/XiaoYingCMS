"""
域名解析工具集 — 根域名提取、子域名判断、域名分组。

用于页面列表树形视图中按根域名聚合展示所有子域名。
"""

from typing import Optional


def extract_root_domain(domain_str: str) -> str:
    """
    从完整域名中提取根域名（二级域名.顶级域名）。

    规则:
      - 去掉端口号 (example.com:8000 → example.com)
      - 去掉通配符前缀 (*.example.com → example.com)
      - 去掉 www 前缀 (www.example.com → example.com)
      - IP 地址 / 127.0.0.1 / localhost 保持不变
      - 两级如 example.com → 自身即为根域名
      - 三级及以上如 blog.example.com → example.com

    >>> extract_root_domain('www.example.com')
    'example.com'
    >>> extract_root_domain('*.example.com')
    'example.com'
    >>> extract_root_domain('example.com:8000')
    'example.com'
    >>> extract_root_domain('127.0.0.1')
    '127.0.0.1'
    >>> extract_root_domain('localhost')
    'localhost'
    """
    if not domain_str or not isinstance(domain_str, str):
        return domain_str or ''

    # 1. 去掉端口
    domain = domain_str.split(':')[0]

    # 2. 去掉通配符前缀
    domain = domain.lstrip('*.')

    # 3. 如果是 IP 地址或 localhost，直接返回
    if _is_ip_or_local(domain):
        return domain

    # 4. 去掉 www 前缀（仅当 www 是子域名时）
    if domain.startswith('www.'):
        domain = domain[4:]

    # 5. 提取最后两部分作为根域名
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain


def is_subdomain(domain_str: str) -> bool:
    """
    判断一个域名是否为子域名（有三级及以上）。

    规则:
      - example.com → False（二级域名）
      - www.example.com → True（三级域名）
      - blog.example.com → True（三级域名）
      - 127.0.0.1 → False

    >>> is_subdomain('www.example.com')
    True
    >>> is_subdomain('example.com')
    False
    """
    if not domain_str or not isinstance(domain_str, str):
        return False
    domain = domain_str.split(':')[0].lstrip('*.')
    if _is_ip_or_local(domain):
        return False
    parts = domain.split('.')
    return len(parts) >= 3


def _is_ip_or_local(domain: str) -> bool:
    """判断是否为 IP 地址或 localhost。"""
    if domain in ('localhost', '0.0.0.0'):
        return True
    parts = domain.split('.')
    if len(parts) == 4:
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except (ValueError, TypeError):
            pass
    return False


def group_domains_by_root(domains: list) -> dict:
    """
    将域名列表按根域名分组。

    输入: ['www.example.com', 'example.com', 'blog.example.com', 'test.com']
    输出: {
        'example.com': ['www.example.com', 'example.com', 'blog.example.com'],
        'test.com': ['test.com'],
    }

    注意:
      - 每个域名会同时出现在根域名和自身条目中
      - 如果域名本身就是根域名（二级域名），会出现在根域名的域名列表中
    """
    groups: dict = {}
    for d in domains:
        root = extract_root_domain(d)
        if root not in groups:
            groups[root] = []
        if d not in groups[root]:
            groups[root].append(d)
    # 确保每个 group 列表中的域名按字母排序
    for root in groups:
        groups[root].sort()
    return groups
