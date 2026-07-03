"""
页面生成服务 — 在独立线程中调用 DeepSeek AI 生成页面 HTML。

工作流程：
  1. start_generation(input_content, session_key)
     - 创建 PageGenerationTask 记录（status=pending, progress=0）
     - 启动 daemon 线程执行 _run_generation
     - 立即返回 task 对象（不等 AI 返回，避免阻塞 HTTP 请求）

  2. _run_generation(task_id) — 后台线程函数
     - 取出最新提示词
     - 调用 DeepSeek API（POST x-www-form-urlencoded）
     - 实时更新 task.progress / task.message
     - 成功 → 写 result_html，状态 completed
     - 失败 → 写 error_message，状态 failed

  3. get_task_progress(task_id) — 给前端轮询用

注意：
  - 线程内的 ORM 操作必须重新获取 task 实例；Django ORM 默认不允许跨线程共享对象
  - 线程开始时关闭旧的 DB 连接，结束时再关闭，让 Django 重新建立新连接
  - daemon=True 保证主进程退出时线程不会卡住
"""

import json
import threading
import urllib.parse
import urllib.request
import urllib.error

from django.conf import settings
from django.db import connection

from XiaoYingAdmin.models.prompt import Prompt
from XiaoYingAdmin.models.task import PageGenerationTask
from XiaoYingAdmin.models.generated_page import GeneratedPage

# DeepSeek API 地址
DEEPSEEK_API_URL = f'{settings.XIAOYING_API_URL}/api/ai/BuiltInModel/deepseek'

# 单次请求总超时（秒）— AI 生成可能较慢，但也不能无限等待
DEEPSEEK_TIMEOUT = 120

# 从响应对象中按优先级尝试的字段名（统一定义，dict / SSE 两条解析路径共用）
_REPLY_KEYS = ('reply', 'content', 'text', 'message')

# 页面名称兜底提取时需要剥离的常见前缀 / 后缀
_NAME_PREFIXES = ('帮我生成一个', '帮我创建一个', '帮我做个', '生成一个', '创建一个', '做个', '生成', '一个')
_NAME_SUFFIXES = ('的页面', '页面', '的网页', '网页', '的网站', '网站')


def _extract_reply(obj) -> str:
    """
    从单个响应对象中提取回复文本。

    兼容两种结构：
      - 嵌套：{"data": {"reply"/"content": "..."}}
      - 扁平：{"reply"/"content"/"text"/"message": "..."}

    取不到时返回空串。
    """
    if not isinstance(obj, dict):
        return ''
    inner = obj.get('data')
    if isinstance(inner, dict):
        for key in ('reply', 'content'):
            if inner.get(key):
                return inner[key]
    for key in _REPLY_KEYS:
        if obj.get(key):
            return obj[key]
    return ''


def _call_deepseek(content: str, system_prompt_json: str) -> str:
    """
    调用 DeepSeek API，返回 content 字段。

    抛出：
      RuntimeError: 网络错误或 HTTP 非 2xx
    """
    form_data = urllib.parse.urlencode({
        'content': content,
        'system_prompt': system_prompt_json,
    }).encode('utf-8')

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=DEEPSEEK_TIMEOUT) as resp:
            body = resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:500]
        raise RuntimeError(f'DeepSeek HTTP {e.code}: {detail}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'DeepSeek 连接失败: {e.reason}')

    # 标准响应：{"code":10000, "msg":"成功", "data":{"reply":"...", ...}}
    try:
        reply = _extract_reply(json.loads(body))
        if reply:
            return reply
    except json.JSONDecodeError:
        pass

    # SSE 流：逐行拼接 data: {...} 中的回复片段
    chunks = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            break
        try:
            reply = _extract_reply(json.loads(payload))
        except json.JSONDecodeError:
            continue
        if reply:
            chunks.append(reply)
    return ''.join(chunks)


def _run_generation(task_id: str):
    """
    后台线程函数：执行一次 AI 页面生成并实时更新进度。

    参数：
      task_id: PageGenerationTask.task_id (UUID 字符串)
    """
    # 线程内必须关闭继承的 DB 连接，让 Django 重新建立
    connection.close()
    try:
        task = PageGenerationTask.objects.get(task_id=task_id)

        # 1. 加载提示词（5%）
        task.update_progress(5, '正在加载提示词...')
        system_prompt_list = Prompt.get_all_active_contents('page_generation')
        task.prompt_snapshot = system_prompt_list[0]['content'] if system_prompt_list else ''
        task.save(update_fields=['prompt_snapshot', 'updated_time'])

        # 2. 构造 system_prompt（15%）
        task.update_progress(15, '正在构造请求参数...')
        system_prompt_json = json.dumps(system_prompt_list, ensure_ascii=False)

        # 3. 调用 AI（20% → 80%）
        task.update_progress(20, '正在请求 AI 接口（可能需要 30-60 秒）...')
        user_content = (task.input_content)

        result = _call_deepseek(user_content, system_prompt_json)
        task.update_progress(80, '正在处理返回结果...')

        if not result or not result.strip():
            task.mark_failed('AI 返回内容为空')
            return

        # 简单清洗：如果返回是 markdown 代码块，去掉包裹
        result = _strip_code_fence(result)

        # 4. 保存结果 + AI 总结页面名称 + 自动保存到库
        task.result_html = result
        task.save(update_fields=['result_html', 'updated_time'])

        # 4a. 调用 AI 总结页面简短名称
        task.update_progress(90, '正在总结页面名称...')
        # 先尝试从用户输入中提取关键词（去掉常见前缀/后缀）作为兜底名称
        raw = task.input_content.strip()
        for prefix in _NAME_PREFIXES:
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        for suffix in _NAME_SUFFIXES:
            if raw.endswith(suffix):
                raw = raw[:-len(suffix)]
                break
        raw = raw.strip()[:30]
        fallback_name = raw if raw else '未命名页面'
        try:
            page_name = _call_deepseek(
                f'从以下需求中提取简短页面名称（2-6个字），只返回名称不要任何其他文字：{task.input_content}',
                json.dumps(
                    [{'role': 'system', 'content': '只返回名称'}],
                    ensure_ascii=False,
                ),
            )
            page_name = page_name.strip().strip('"\'').strip()[:50]
            if not page_name or len(page_name) > 20 or '?' in page_name or not any(ord(c) > 127 for c in page_name):
                page_name = fallback_name
        except RuntimeError:
            page_name = fallback_name
        task.page_name = page_name
        task.save(update_fields=['page_name', 'updated_time'])

        # 4b. 自动保存到 GeneratedPage 表
        try:
            GeneratedPage.objects.create(
                name=page_name,
                html_content=result,
                task_id=task.task_id,
                input_content=task.input_content,
                created_by=task.created_by,
            )
        except Exception:
            pass  # 保存失败不影响主流程

        task.update_progress(100, '生成完成')

    except PageGenerationTask.DoesNotExist:
        pass  # 任务记录被删除了，安静退出
    except RuntimeError as e:
        try:
            task = PageGenerationTask.objects.get(task_id=task_id)
            task.mark_failed(str(e))
        except PageGenerationTask.DoesNotExist:
            pass
    except Exception as e:
        try:
            task = PageGenerationTask.objects.get(task_id=task_id)
            task.mark_failed(f'系统错误: {type(e).__name__}: {e}')
        except PageGenerationTask.DoesNotExist:
            pass
    finally:
        connection.close()


def _strip_code_fence(text: str) -> str:
    """去掉 AI 返回中常见的 markdown 代码块包裹。"""
    text = text.strip()
    # 优先匹配 ```html\n（带换行）
    for prefix in ('```html\n', '```html\r\n', '```html', '```\n', '```\r\n', '```'):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in ('\n```', '\r\n```', '```'):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    return text.strip()


def start_generation(input_content: str, session_key: str = '',
                     created_by=None) -> PageGenerationTask:
    """
    启动一次页面生成任务（主线程调用，立即返回）。

    参数：
      input_content: 用户输入的页面描述
      session_key: 当前 session_key，用于跨请求查询
      created_by: 发起任务的用户对象（User 实例或 None）

    返回：
      新创建的 PageGenerationTask 实例
    """
    task = PageGenerationTask.objects.create(
        input_content=input_content,
        session_key=session_key,
        status=PageGenerationTask.STATUS_PENDING,
        progress=0,
        message='任务已创建，等待执行...',
        created_by=created_by,
    )

    thread = threading.Thread(
        target=_run_generation,
        args=(str(task.task_id),),
        daemon=True,
        name=f'page-gen-{task.task_id}',
    )
    thread.start()

    return task


def get_task_progress(task_id: str) -> dict | None:
    """
    查询任务进度（前端轮询用）。

    返回：
      dict: {task_id, status, progress, message, result_html?, error_message?}
      None: 任务不存在
    """
    try:
        task = PageGenerationTask.objects.get(task_id=task_id)
    except (PageGenerationTask.DoesNotExist, ValueError):
        return None

    data = {
        'task_id': str(task.task_id),
        'status': task.status,
        'status_display': task.get_status_display(),
        'progress': task.progress,
        'message': task.message,
    }
    if task.status == PageGenerationTask.STATUS_COMPLETED:
        data['result_html'] = task.result_html
        data['page_name'] = task.page_name
    if task.status == PageGenerationTask.STATUS_FAILED:
        data['error_message'] = task.error_message
    return data
