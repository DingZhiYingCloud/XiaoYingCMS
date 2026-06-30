"""
蜘蛛访问日志 视图

URL: /xiaoying_admin/spider/logs/
"""
import csv
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import ExtractHour
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import err
from XiaoYingAdmin.models.seo_cloak import SeoCloakRule
from XiaoYingAdmin.models.spider_log import SpiderAccessLog, SpiderLogConfig


PAGE_SIZE = 10  # 每页条数（默认 10，可在请求参数 ?page_size= 覆盖）
ALLOWED_PAGE_SIZES = [10, 20, 50, 100]  # 允许用户自定义的分页大小

# 时间段定义：用于树状图分组
# (key, label, icon, hour_start, hour_end_exclusive, color)
PERIOD_DEFS = [
    ('dawn',     '凌晨', '🌙', 0,  6,  '#5C6BC0'),
    ('morning',  '上午', '☀️', 6,  12, '#FFA726'),
    ('afternoon','下午', '🌤️', 12, 18, '#26A69A'),
    ('evening',  '晚上', '🌃', 18, 24, '#7E57C2'),
]

# 时间范围映射
DAYS_OPTIONS = {
    'today': 0,        # 仅今天（0:00 至今）
    '1d': 1,
    '3d': 3,
    '7d': 7,
    '30d': 30,
    'all': None,       # 全部
}


def _parse_days_param(request) -> timedelta | None:
    """根据 ?days= 参数返回起始时间（None 表示不限时间）。"""
    days = request.GET.get('days', '7d')
    if days == 'today':
        now = timezone.now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if days == 'all':
        return None
    n = DAYS_OPTIONS.get(days, 7)
    return timezone.now() - timedelta(days=n)


def _build_filters(request) -> dict:
    """根据 request 构造 ORM 过滤条件（不含时间范围，时间单独处理）。"""
    q = request.GET
    filters = {}
    if spider := q.get('spider', '').strip():
        filters['spider_name'] = spider
    if ip := q.get('ip', '').strip():
        # GenericIPAddressField 精确匹配
        filters['ip'] = ip
    if method := q.get('method', '').strip().upper():
        if method in ('GET', 'POST', 'HEAD', 'PUT', 'DELETE'):
            filters['method'] = method
    return filters


# 访问者类型定义
# 分类规则:
#   spider → spider_name != ''         (User-Agent 匹配爬虫关键字)
#   human  → spider_name == ''         (真人,含来自搜索引擎的)
#   direct → spider_name == '' AND referer == ''  (真人且直接输入 URL)
WHO_LABELS = {
    '':        '全部访问者',
    'spider':  '仅蜘蛛',
    'human':   '仅真人（含搜索引擎）',
    'direct':  '仅直接访问',
}


def _parse_who(request) -> str:
    """解析并校验 ?who= 参数,返回合法值(非法值视为空)。"""
    who = request.GET.get('who', '').strip().lower()
    return who if who in WHO_LABELS else ''


def _apply_who(qs, who: str):
    """根据 who 值过滤 qs:
        ''       → 不过滤
        'spider' → spider_name != ''
        'human'  → spider_name == ''
        'direct' → spider_name == '' AND referer == ''
    """
    if who == 'spider':
        return qs.exclude(spider_name='')
    if who == 'human':
        return qs.filter(spider_name='')
    if who == 'direct':
        return qs.filter(spider_name='', referer='')
    return qs


def _compute_who_counts(qs) -> dict:
    """计算 蜘蛛/真人/直接访问 数量与占比 + SVG 环形图参数。

    互斥分类（用于环形图,3 类加起来 = total）:
      spider        → spider_name != ''           (爬虫)
      human_direct  → spider_name == '' AND referer == ''  (真人直接访问)
      human_refer   → spider_name == '' AND referer != ''  (真人有来源)

    过滤分类（用于卡片点击,保留 human 包含 direct 的语义）:
      human = human_direct + human_refer
      direct = human_direct

    SVG 参数（stroke-dasharray 技巧画环形）:
      周长 C = 2π × 80 ≈ 502
      每段 dasharray = "段长度 (C-段长度)"
      每段 dashoffset = -(前面所有段长度之和)  负值表示沿圆周前进
    """
    SVG_CIRCUMFERENCE = 502  # 2π × 80 ≈ 502.65, 取整数避免模板浮点运算
    total = qs.count()
    if total == 0:
        return {
            'total': 0, 'spider': 0, 'human': 0, 'direct': 0,
            'human_refer': 0,
            'spider_pct': 0, 'human_pct': 0, 'direct_pct': 0,
            'human_refer_pct': 0,
            'svg': {'l1': 0, 'l2': 0, 'l3': 0, 'o1': 0, 'o2': 0, 'o3': 0, 'c': SVG_CIRCUMFERENCE},
        }
    spider = qs.exclude(spider_name='').count()
    human = qs.filter(spider_name='').count()
    direct = qs.filter(spider_name='', referer='').count()
    human_refer = human - direct  # 真人有来源 = 真人 - 真人直接

    # SVG 段长度（按比例换算到周长）
    l1 = round(spider / total * SVG_CIRCUMFERENCE)
    l2 = round(direct / total * SVG_CIRCUMFERENCE)
    l3 = round(human_refer / total * SVG_CIRCUMFERENCE)

    return {
        'total': total,
        'spider': spider,
        'human': human,
        'direct': direct,
        'human_refer': human_refer,
        'spider_pct': round(spider / total * 100),
        'human_pct': round(human / total * 100),
        'direct_pct': round(direct / total * 100),
        'human_refer_pct': round(human_refer / total * 100) if human_refer else 0,
        'svg': {
            'l1': l1, 'l2': l2, 'l3': l3,
            'o1': 0, 'o2': -l1, 'o3': -(l1 + l2),
            'c': SVG_CIRCUMFERENCE,
        },
    }


def _build_base_query(request, override: dict = None, drop: tuple = ()) -> str:
    """构造 query string:
        override: 强制覆盖/新增的 {param: value}, value='' 表示删除该参数
        drop:     要移除的参数名(如 'page')
    返回: 已 urlencode 的字符串
    """
    q = request.GET.copy()
    for k in drop:
        q.pop(k, None)
    if override:
        for k, v in override.items():
            if v:
                q[k] = v
            else:
                q.pop(k, None)
    return q.urlencode()


def _compute_stats(qs) -> dict:
    """基于 queryset 聚合 4 个统计指标。"""
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_qs = qs.filter(create_time__gte=today_start)
    return {
        'spider_count': today_qs.exclude(spider_name='').values('spider_name').distinct().count(),
        'ip_count': today_qs.values('ip').distinct().count(),
        'path_count': today_qs.values('path').distinct().count(),
        'total_count': today_qs.count(),
    }


# 爬虫颜色分配（用于时段分布图）
SPIDER_COLORS = ['#5C6BC0', '#FFA726', '#26A69A', '#7E57C2', '#42A5F5',
                 '#EF5350', '#66BB6A', '#8D6E63', '#FF7043', '#AB47BC']


def _compute_period_tree(qs, top_n: int = 5) -> dict:
    """按时间段(凌晨/上午/下午/晚上)聚合爬虫数据。

    返回两种数据结构:
      1. groups: 树状分组,每个 spider 携带 color 字段用于 CSS 渲染
      2. echarts: 扁平化数据（保留,兼容）

    top_n: 跨所有时段合并后取访问量前 N 的爬虫,其余合并为"其他爬虫"
    """
    # 只统计爬虫(spider_name 非空)
    spider_qs = qs.exclude(spider_name='').annotate(hour=ExtractHour('create_time'))

    total_all = spider_qs.count()

    # ===== 1. 按 (时段, 爬虫名) 聚合 =====
    # rows: [{'period_key', 'spider_name', 'count'}]
    rows = []
    for key, label, icon, h_start, h_end, color in PERIOD_DEFS:
        period_qs = spider_qs.filter(hour__gte=h_start, hour__lt=h_end)
        for r in period_qs.values('spider_name').annotate(count=Count('id')):
            rows.append({
                'period_key': key,
                'spider_name': r['spider_name'],
                'count': r['count'],
            })

    # ===== 2. 跨时段合并,取 top N 爬虫 =====
    spider_total = {}
    for r in rows:
        spider_total[r['spider_name']] = spider_total.get(r['spider_name'], 0) + r['count']
    top_spider_names = [n for n, _ in sorted(spider_total.items(), key=lambda x: -x[1])[:top_n]]

    # ===== 3. 构造 ECharts 扁平化数据 =====
    # (period_key, spider_name) -> count
    lookup = {(r['period_key'], r['spider_name']): r['count'] for r in rows}

    categories = [p[1] for p in PERIOD_DEFS]  # ['凌晨','上午','下午','晚上']
    series = []
    for name in top_spider_names:
        data = [lookup.get((p[0], name), 0) for p in PERIOD_DEFS]
        series.append({'name': name, 'data': data})

    # 其他爬虫（合并）
    other_data = [0, 0, 0, 0]
    for r in rows:
        if r['spider_name'] not in top_spider_names:
            idx = next(i for i, p in enumerate(PERIOD_DEFS) if p[0] == r['period_key'])
            other_data[idx] += r['count']
    if any(other_data):
        series.append({'name': '其他爬虫', 'data': other_data})

    totals = []
    for p in PERIOD_DEFS:
        totals.append(sum(lookup.get((p[0], n), 0) for n in spider_total))

    # ===== 4. 保留树状分组结构（降级展示用） =====
    groups = []
    for key, label, icon, h_start, h_end, color in PERIOD_DEFS:
        period_total = sum(lookup.get((key, n), 0) for n in spider_total)
        period_rows = sorted(
            [(n, lookup.get((key, n), 0)) for n in set(r['spider_name'] for r in rows if r['period_key'] == key)],
            key=lambda x: -x[1]
        )
        spiders = [
            {
                'name': n, 'count': c,
                'percent': round(c / period_total * 100) if period_total else 0,
                'color': SPIDER_COLORS[i % len(SPIDER_COLORS)],
            }
            for i, (n, c) in enumerate(period_rows[:top_n])
        ]
        other = period_total - sum(s['count'] for s in spiders)
        if other > 0:
            spiders.append({
                'name': '其他爬虫', 'count': other,
                'percent': round(other / period_total * 100) if period_total else 0,
                'color': '#b0b0b0',
            })
        groups.append({
            'key': key, 'label': label, 'icon': icon, 'color': color,
            'hour_range': (h_start, h_end), 'count': period_total,
            'percent': round(period_total / total_all * 100) if total_all else 0,
            'spiders': spiders,
        })

    return {
        'total': total_all,
        'groups': groups,
        'echarts': {
            'categories': categories,
            'series': series,
            'totals': totals,
        },
    }


# =============================================================================
# 页面视图
# =============================================================================

def _build_pagination_html(page: int, total_pages: int, current_query: str) -> str:
    """生成简洁的分页 HTML：当前页 ± 2 页 + 首页/末页 + 上下页按钮。

    current_query: 已包含其他参数的 query string（不含 page），如 "days=7d&spider=googlebot"
    """
    if total_pages <= 1:
        return ''
    sep = '&' if current_query else ''

    def link(n: int, label: str, disabled: bool = False, primary: bool = True) -> str:
        cls = 'layui-btn layui-btn-sm'
        cls += ' layui-btn-normal' if disabled else ' layui-btn-primary'
        if disabled:
            return f'<button class="{cls}" disabled>{label}</button>'
        return f'<a class="{cls}" href="?{current_query}{sep}page={n}">{label}</a>'

    parts = []
    parts.append(link(max(1, page - 1), '<i class="fas fa-chevron-left"></i> 上一页',
                      disabled=(page == 1)))
    # 数字页：当前页 ± 2
    start = max(1, page - 2)
    end = min(total_pages, page + 2)
    if start > 1:
        parts.append(link(1, '1'))
        if start > 2:
            parts.append('<span style="margin:0 5px; color:#999;">…</span>')
    for n in range(start, end + 1):
        parts.append(link(n, str(n), disabled=(n == page)))
    if end < total_pages:
        if end < total_pages - 1:
            parts.append('<span style="margin:0 5px; color:#999;">…</span>')
        parts.append(link(total_pages, str(total_pages)))
    parts.append(link(min(total_pages, page + 1), '下一页 <i class="fas fa-chevron-right"></i>',
                      disabled=(page == total_pages)))
    return '<div style="text-align:center; margin-top:15px;">' + ''.join(parts) + '</div>'


def _parse_page_size(request) -> int:
    """从 ?page_size= 解析分页大小,落到 ALLOWED_PAGE_SIZES 白名单,默认 PAGE_SIZE。"""
    raw = request.GET.get('page_size', '').strip()
    if not raw:
        return PAGE_SIZE
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return PAGE_SIZE
    return n if n in ALLOWED_PAGE_SIZES else PAGE_SIZE


def spider_logs_view(request):
    """蜘蛛日志列表页（后台页面 /xiaoying_admin/spider/logs/）。"""
    config = SpiderLogConfig.get_singleton()
    cloak_rule = SeoCloakRule.get_singleton()

    # 模式保存（POST）
    if request.method == 'POST':
        new_mode = request.POST.get('log_mode', '').strip()
        valid_modes = [v for v, _ in [
            ("all", "全部访问"), ("spider_only", "仅爬虫"), ("disabled", "关闭")
        ]]
        if new_mode not in valid_modes:
            return redirect(reverse('spider_logs') + '?error=invalid_mode')
        config.log_mode = new_mode
        config.save(update_fields=['log_mode', 'updated_time'])
        return redirect(reverse('spider_logs') + '?saved=1')

    # GET 渲染
    since = _parse_days_param(request)
    filters = _build_filters(request)
    current_who = _parse_who(request)

    # 基础 qs（不含 who 过滤）—— 用于计算 who 计数 + 树状图
    base_qs = SpiderAccessLog.objects.filter(**filters)
    if since is not None:
        base_qs = base_qs.filter(create_time__gte=since)

    # 应用 who 过滤 —— 用于列表分页
    qs = _apply_who(base_qs, current_who)

    # 分页（支持自定义 page_size）
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    page_size = _parse_page_size(request)
    total = qs.count()
    start = (page - 1) * page_size
    logs = list(qs[start:start + page_size])

    # 全部去重后的爬虫名（用于筛选下拉）
    all_spider_names = list(
        SpiderAccessLog.objects.exclude(spider_name='')
        .values_list('spider_name', flat=True).distinct().order_by('spider_name')
    )

    # 统计（基于 today 全量，不受筛选影响）
    stats = _compute_stats(SpiderAccessLog.objects.all())

    # 树状图数据（基于当前 who + 其他筛选）
    period_stats = _compute_period_tree(qs)

    # 访问者类型计数（基于 base_qs，不含 who 过滤本身,便于切换 who 后计数仍正确）
    who_counts = _compute_who_counts(base_qs)

    # 构造卡片用 query 字符串（保留所有筛选,只切换 who,移除 page）
    base_query_no_who = _build_base_query(request, override={'who': ''}, drop=('page',))
    base_query_with_who_spider = _build_base_query(request, override={'who': 'spider'}, drop=('page',))
    base_query_with_who_human = _build_base_query(request, override={'who': 'human'}, drop=('page',))
    base_query_with_who_direct = _build_base_query(request, override={'who': 'direct'}, drop=('page',))

    # 构造分页（保留其他筛选条件 + page_size + who）
    query_parts = [f'days={request.GET.get("days", "7d")}']
    if current_who:
        query_parts.append(f'who={current_who}')
    if request.GET.get('spider'):
        query_parts.append(f'spider={request.GET.get("spider")}')
    if request.GET.get('ip'):
        query_parts.append(f'ip={request.GET.get("ip")}')
    if request.GET.get('method'):
        query_parts.append(f'method={request.GET.get("method")}')
    query_parts.append(f'page_size={page_size}')
    current_query = '&'.join(query_parts)
    total_pages = max(1, (total + page_size - 1) // page_size)
    pagination_html = _build_pagination_html(page, total_pages, current_query)

    return render(request, 'XiaoYingAdmin/蜘蛛管理/蜘蛛日志/index.html', {
        'logs': logs,
        'stats': stats,
        'config': config,
        'spider_keywords': cloak_rule.get_spider_keywords(),
        'all_spider_names': all_spider_names,
        'days': request.GET.get('days', '7d'),
        'current_who': current_who,
        'who_label': WHO_LABELS[current_who],
        'current_spider': request.GET.get('spider', ''),
        'current_ip': request.GET.get('ip', ''),
        'current_method': request.GET.get('method', ''),
        'page': page,
        'page_size': page_size,
        'allowed_page_sizes': ALLOWED_PAGE_SIZES,
        'total': total,
        'total_pages': total_pages,
        'pagination_html': pagination_html,
        'period_stats': period_stats,
        'counts': who_counts,
        'base_query_no_who': base_query_no_who,
        'base_query_with_who_spider': base_query_with_who_spider,
        'base_query_with_who_human': base_query_with_who_human,
        'base_query_with_who_direct': base_query_with_who_direct,
        'saved': request.GET.get('saved') == '1',
        'error': request.GET.get('error', ''),
    })


# =============================================================================
# AJAX API
# =============================================================================

@csrf_exempt
@require_GET
def spider_logs_api_list(request):
    """
    GET /xiaoying_admin/spider/logs/api/list/
    Query: page, page_size, days, who, spider, ip, method
    """
    since = _parse_days_param(request)
    filters = _build_filters(request)
    base_qs = SpiderAccessLog.objects.filter(**filters)
    if since is not None:
        base_qs = base_qs.filter(create_time__gte=since)
    current_who = _parse_who(request)
    qs = _apply_who(base_qs, current_who)

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    page_size = _parse_page_size(request)
    total = qs.count()
    start = (page - 1) * page_size
    logs_qs = qs[start:start + page_size].values(
        'id', 'ip', 'user_agent', 'spider_name', 'path',
        'method', 'referer', 'status_code', 'response_size',
        'create_time',
    )
    return JsonResponse({
        'logs': [
            {**row, 'create_time': row['create_time'].strftime('%Y-%m-%d %H:%M:%S')}
            for row in logs_qs
        ],
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': max(1, (total + page_size - 1) // page_size),
        'who': current_who,
        'who_counts': _compute_who_counts(base_qs),
        'stats': _compute_stats(SpiderAccessLog.objects.all()),
    })


@csrf_exempt
@require_POST
def spider_logs_api_clear(request):
    """
    POST /xiaoying_admin/spider/logs/api/clear/
    Body: confirm=yes  (二次确认 token，缺失则拒绝)
    """
    if request.POST.get('confirm') != 'yes':
        return err('请二次确认后清空（需传 confirm=yes）')
    deleted, _ = SpiderAccessLog.objects.all().delete()
    return JsonResponse({'message': f'已清空 {deleted} 条记录', 'deleted': deleted})


@require_GET
def spider_logs_api_export(request):
    """
    GET /xiaoying_admin/spider/logs/api/export/?days=7d&spider=googlebot&who=spider
    返回 CSV 文件下载（含 BOM 让 Excel 正确识别中文）。
    """
    since = _parse_days_param(request)
    filters = _build_filters(request)
    base_qs = SpiderAccessLog.objects.filter(**filters)
    if since is not None:
        base_qs = base_qs.filter(create_time__gte=since)
    qs = _apply_who(base_qs, _parse_who(request))

    filename = f"spider_logs_{timezone.now():%Y%m%d_%H%M%S}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    # BOM 让 Excel 识别 UTF-8
    response.write('\ufeff')
    writer.writerow(['ID', '时间', 'IP', '爬虫名', '方法', '路径', '状态码', '大小(字节)', '来源', 'User-Agent'])
    for row in qs.values_list(
        'id', 'create_time', 'ip', 'spider_name', 'method', 'path',
        'status_code', 'response_size', 'referer', 'user_agent',
    ):
        writer.writerow([
            row[0],
            row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else '',
            row[2],
            row[3],
            row[4],
            row[5],
            row[6] if row[6] is not None else '',
            row[7] if row[7] is not None else '',
            row[8],
            row[9][:200],  # UA 截断，避免单行过长
        ])
    return response
