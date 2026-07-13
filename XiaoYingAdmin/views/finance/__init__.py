"""
财务管理 — 共享工具函数
"""


def paginate_queryset(qs, page, page_size=20):
    """
    通用分页函数
    返回值: (data_list, total, total_pages, page, page_size)
    """
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 20), 1)
    # 合理上限，防止恶意传参
    page_size = min(page_size, 200)

    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size
    data_list = list(qs[offset:offset + page_size])
    return data_list, total, total_pages, page, page_size


def paginate_response(ok, data, total, total_pages, page, page_size, **extra):
    """构建统一的分页 JSON 响应"""
    resp = {
        'ok': ok,
        'list': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
    }
    resp.update(extra)
    return resp
