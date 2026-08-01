"""
友情链接管理 API。

提供友情链接的列表、添加、删除接口，
用于在单页面管理列表中维护自定义友情链接（标题 + URL）。

友情链接支持配置应用范围（全部页面 / 指定分类），
添加或删除时自动同步注入到目标页面的 HTML 中（类似智能互链）。
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import err, get_or_404, parse_json_body
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.friend_link import FriendLink

# ---------------------------------------------------------------------------
# 自定义友情链接块标记（与智能互链块相互独立，可共存）
# ---------------------------------------------------------------------------
_FRIEND_LINK_TAG_START = '<!-- ====== 自定义友情链接 ====== -->'
_FRIEND_LINK_TAG_END = '<!-- ====== /自定义友情链接 ====== -->'


def _escape_attr(s: str) -> str:
    """HTML 属性转义。"""
    return str(s).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')


def _friend_link_block_html(links: list) -> str:
    """
    生成自定义友情链接块 HTML（含标记头尾）。

    links: [FriendLink, ...]
    """
    items = '\n'.join(
        f'      <a href="{_escape_attr(link.url)}" '
        f'title="{_escape_attr(link.title)}" '
        f'rel="friend" target="_blank">{_escape_attr(link.title)}</a>'
        for link in links
    )
    return (
        f'\n{_FRIEND_LINK_TAG_START}\n'
        '<div style="'
        '  max-width:1200px; margin:40px auto 0; padding:24px 20px 16px;'
        '  border-top:1px solid #e8e8e8; text-align:center;'
        '">\n'
        '  <div style="'
        '    font-size:13px; color:#999; margin-bottom:12px;'
        '    letter-spacing:1px;'
        '  ">— 友情链接 —</div>\n'
        '  <div style="display:flex; flex-wrap:wrap; justify-content:center; gap:8px;">\n'
        f'{items}\n'
        '  </div>\n'
        '</div>\n'
        f'{_FRIEND_LINK_TAG_END}\n'
    )


def _apply_friend_link_block(html: str, links: list) -> str:
    """
    将页面的自定义友情链接块替换为指定链接块。

    - links 为空 → 移除已有的友链块
    - links 非空 → 替换已有块，无块则追加到 </body> 前（无 </body> 则追加到末尾）
    """
    start_idx = html.find(_FRIEND_LINK_TAG_START)
    end_idx = html.find(_FRIEND_LINK_TAG_END)

    if not links:
        # 移除已有友链块
        if start_idx != -1 and end_idx != -1:
            end_idx += len(_FRIEND_LINK_TAG_END)
            return html[:start_idx] + html[end_idx:]
        return html

    new_block = _friend_link_block_html(links)

    if start_idx != -1 and end_idx != -1:
        end_idx += len(_FRIEND_LINK_TAG_END)
        return html[:start_idx] + new_block + html[end_idx:]

    # 无友链块 → 追加：优先 </body> 前，否则末尾
    body_idx = html.lower().rfind('</body>')
    if body_idx != -1:
        return html[:body_idx] + new_block + '\n' + html[body_idx:]
    return html + '\n' + new_block


def sync_friend_links_to_pages(pages=None) -> dict:
    """
    全量同步友情链接到页面 HTML。

    对每个页面重新计算其应展示的友情链接（scope=all 的全局友链 +
    页面所属分类匹配的友链），并替换/移除页面中的友链块。
    幂等操作：无论调用多少次，结果一致。

    pages: 可选，只同步指定页面（页面保存/更新后调用）。
           None 时同步所有页面。

    返回: {"updated": int, "total": int}
    """
    from XiaoYingAdmin.models.generated_page import GeneratedPage

    # 1. 收集所有友链，按范围分组
    all_links = list(FriendLink.objects.select_related('category').all())
    global_links = [l for l in all_links if l.scope == FriendLink.SCOPE_ALL]
    links_by_cat = {}
    for l in all_links:
        if l.scope == FriendLink.SCOPE_CATEGORY and l.category_id:
            links_by_cat.setdefault(l.category_id, []).append(l)

    # 2. 遍历页面
    if pages is not None:
        qs = pages
    else:
        qs = GeneratedPage.objects.all()

    updated = 0
    total = 0
    for page in qs.iterator():
        total += 1
        # 收集该页面应展示的友链（去重）
        merged = list(global_links)
        for cat_id in page.categories.values_list('id', flat=True):
            merged.extend(links_by_cat.get(cat_id, []))
        seen = set()
        final_links = []
        for l in merged:
            if l.id not in seen:
                seen.add(l.id)
                final_links.append(l)

        new_html = _apply_friend_link_block(page.html_content, final_links)
        if new_html != page.html_content:
            page.html_content = new_html
            page.save(update_fields=['html_content', 'updated_time'])
            updated += 1

    return {'updated': updated, 'total': total}


@require_GET
def friend_link_list(request):
    """获取友情链接列表。响应: {"items": [{...}]}"""
    items = FriendLink.objects.select_related('category').all()
    return JsonResponse({'items': [l.to_dict() for l in items]})


@csrf_exempt
@require_POST
def friend_link_create(request):
    """
    添加友情链接。

    请求: application/json
      {"title": "链接标题", "url": "https://example.com",
       "scope": "all" | "category", "category_id": 1}
    添加后自动同步注入到目标页面。
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    title = (body.get('title') or '').strip()
    url = (body.get('url') or '').strip()
    scope = (body.get('scope') or FriendLink.SCOPE_ALL).strip()
    category_id = body.get('category_id')

    if not title:
        return err('链接标题不能为空')
    if not url:
        return err('链接 URL 不能为空')
    if scope not in (FriendLink.SCOPE_ALL, FriendLink.SCOPE_CATEGORY):
        return err('应用范围不合法')

    category = None
    if scope == FriendLink.SCOPE_CATEGORY:
        if not category_id:
            return err('请选择应用分类')
        from XiaoYingAdmin.models.page_category import PageCategory
        category, error = get_or_404(
            PageCategory, id=category_id, not_found_msg='分类不存在',
        )
        if error is not None:
            return error

    link = FriendLink.objects.create(title=title, url=url, scope=scope, category=category)

    # 同步注入到目标页面
    sync_result = sync_friend_links_to_pages()

    log_operation(request, 'create', 'FriendLink', link.id,
                  f'添加友情链接「{link.title}」',
                  detail={'changes': {
                      '标题': {'new': title},
                      'URL': {'new': url},
                      '应用范围': {'new': link.to_dict()['scope_label']},
                  }})

    return JsonResponse({
        'message': f'添加成功，已同步到 {sync_result["updated"]} 个页面',
        'link': link.to_dict(),
        'sync': sync_result,
    })


@csrf_exempt
@require_POST
def friend_link_delete(request):
    """
    删除友情链接。

    请求: application/json
      {"id": 1}
    删除后自动从所有页面中移除该友链。
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    link, error = get_or_404(FriendLink, id=body.get('id'), not_found_msg='友情链接不存在')
    if error is not None:
        return error

    title = link.title
    link.delete()

    # 同步移除该友链
    sync_result = sync_friend_links_to_pages()

    log_operation(request, 'delete', 'FriendLink', link.id,
                  f'删除友情链接「{title}」')

    return JsonResponse({
        'message': f'删除成功，已同步 {sync_result["updated"]} 个页面',
        'sync': sync_result,
    })
