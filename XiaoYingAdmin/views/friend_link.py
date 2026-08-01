"""
友情链接管理 API。

提供友情链接的列表、添加、删除接口，
用于在单页面管理列表中维护自定义友情链接（标题 + URL）。
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from XiaoYingAdmin.common.http import err, get_or_404, parse_json_body
from XiaoYingAdmin.middleware.operation_log import log_operation
from XiaoYingAdmin.models.friend_link import FriendLink


@require_GET
def friend_link_list(request):
    """获取友情链接列表。响应: {"items": [{"id":1, "title":"...", "url":"...", ...}]}"""
    items = FriendLink.objects.all()
    return JsonResponse({'items': [l.to_dict() for l in items]})


@csrf_exempt
@require_POST
def friend_link_create(request):
    """
    添加友情链接。

    请求: application/json
      {"title": "链接标题", "url": "https://example.com"}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    title = (body.get('title') or '').strip()
    url = (body.get('url') or '').strip()

    if not title:
        return err('链接标题不能为空')
    if not url:
        return err('链接 URL 不能为空')

    link = FriendLink.objects.create(title=title, url=url)

    log_operation(request, 'create', 'FriendLink', link.id,
                  f'添加友情链接「{link.title}」',
                  detail={'changes': {'标题': {'new': title}, 'URL': {'new': url}}})

    return JsonResponse({'message': '添加成功', 'link': link.to_dict()})


@csrf_exempt
@require_POST
def friend_link_delete(request):
    """
    删除友情链接。

    请求: application/json
      {"id": 1}
    """
    body, error = parse_json_body(request)
    if error is not None:
        return error

    link, error = get_or_404(FriendLink, id=body.get('id'), not_found_msg='友情链接不存在')
    if error is not None:
        return error

    title = link.title
    link.delete()

    log_operation(request, 'delete', 'FriendLink', link.id,
                  f'删除友情链接「{title}」')

    return JsonResponse({'message': '删除成功'})
