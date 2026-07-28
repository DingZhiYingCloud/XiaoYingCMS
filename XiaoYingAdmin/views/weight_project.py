"""权重页面项目视图 — 项目 CRUD + 启动/停止 + 模板创建 + 反向代理。"""
import io
import json
import os
import signal
import socket
import subprocess
import sys
import logging
import re
from urllib.parse import urlparse
import urllib.request
import urllib.error

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from XiaoYingAdmin.models import WeightProject
from XiaoYingAdmin.common.http import err, parse_json_body, get_or_404

logger = logging.getLogger('XiaoYingAdmin.weight_project')

# 项目模板目录（相对于项目根目录 manage.py 所在目录）
TEMPLATE_PROJECT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'project_template')


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _is_port_available(port: int) -> bool:
    """检查端口是否可用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def _find_available_port(start: int = 9000, end: int = 9999) -> int:
    """从 start 开始找一个可用端口。"""
    for port in range(start, end + 1):
        if _is_port_available(port):
            return port
    return 0


def _get_manage_py(project_path: str) -> str:
    """获取项目路径下的 manage.py 路径。"""
    return os.path.join(project_path, 'manage.py')


def _get_python_path(project_path: str) -> str:
    """获取项目对应的 Python 解释器路径。
    
    优先级：
      1. settings.WEIGHT_PROJECT_PYTHON 手动指定
      2. 项目目录下的 .venv 或 venv
      3. 当前进程的 Python（sys.executable）
    """
    # 1. 优先使用配置的手动路径
    from django.conf import settings as dj_settings
    configured_python = getattr(dj_settings, 'WEIGHT_PROJECT_PYTHON', '')
    if configured_python and os.path.isfile(configured_python):
        return configured_python

    # 2. 检查项目是否有虚拟环境
    venv_paths = [
        os.path.join(project_path, '.venv', 'Scripts', 'python.exe'),
        os.path.join(project_path, 'venv', 'Scripts', 'python.exe'),
        os.path.join(project_path, '.venv', 'bin', 'python'),
        os.path.join(project_path, 'venv', 'bin', 'python'),
    ]
    for p in venv_paths:
        if os.path.exists(p):
            return p
    return sys.executable


def _get_log_path(project_path: str, port: int) -> str:
    """获取项目的日志文件路径，确保目录存在。"""
    log_dir = os.path.join(project_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f'django-{port}.log')


def _read_log_tail(log_path: str, max_lines: int = 200) -> str:
    """读取日志文件末尾的 max_lines 行。"""
    if not os.path.isfile(log_path):
        return ''
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return ''.join(lines[-max_lines:])
    except Exception:
        return ''


def _get_log_line_count(log_path: str) -> int:
    """获取日志文件的行数。"""
    if not os.path.isfile(log_path):
        return 0
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _get_backup_dir(project_path: str) -> str:
    """获取项目的日志备份目录，确保目录存在。"""
    backup_dir = os.path.join(project_path, 'backups', 'logs')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _do_auto_backup(project) -> str | None:
    """检查并执行日志自动备份。返回备份文件名，无需备份则返回 None。"""
    threshold = project.auto_backup_threshold
    if threshold <= 0:
        return None

    log_path = _get_log_path(
        os.path.abspath(project.project_path) if project.project_path else '',
        project.port,
    )
    line_count = _get_log_line_count(log_path)
    if line_count < threshold:
        return None

    # 执行备份：复制文件到备份目录，清空原文件
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f'django-{project.port}-backup-{timestamp}.log'
    backup_dir = _get_backup_dir(
        os.path.abspath(project.project_path) if project.project_path else '',
    )
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        import shutil
        shutil.copy2(log_path, backup_path)
        # 清空原文件
        open(log_path, 'w').close()
        logger.info(
            '权重项目日志自动备份: %s → %s (%d 行)',
            project.name, backup_filename, line_count,
        )
        return backup_filename
    except Exception as e:
        logger.exception('权重项目日志自动备份失败: %s', e)
        return None


def _ensure_migrations_dirs(project_path: str):
    """确保项目下所有 Django app 都有 migrations/__init__.py。
    扫描 manage.py 同级目录下的子目录，如果包含 apps.py 则视为 app。
    """
    if not os.path.isdir(project_path):
        return
    for name in os.listdir(project_path):
        app_dir = os.path.join(project_path, name)
        if not os.path.isdir(app_dir) or name.startswith('.'):
            continue
        if os.path.isfile(os.path.join(app_dir, 'apps.py')) or os.path.isfile(os.path.join(app_dir, '__init__.py')):
            migrations_dir = os.path.join(app_dir, 'migrations')
            if not os.path.isdir(migrations_dir):
                try:
                    os.makedirs(migrations_dir, exist_ok=True)
                    init_file = os.path.join(migrations_dir, '__init__.py')
                    if not os.path.isfile(init_file):
                        with open(init_file, 'w') as f:
                            f.write('')
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 页面视图
# ---------------------------------------------------------------------------

def weight_project_list_view(request):
    """权重页面项目列表页"""
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/项目列表.html')


def weight_project_create_view(request):
    """添加项目页（模式A：手动配置）"""
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/添加项目.html', {
        'project_type': 'manual',
    })


def weight_project_edit_view(request, pk):
    """编辑项目页"""
    project = get_object_or_404(WeightProject, pk=pk)
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/编辑项目.html', {
        'project': project,
    })


def weight_project_detail_view(request, pk):
    """项目详情页"""
    project = get_object_or_404(WeightProject, pk=pk)
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/项目详情.html', {
        'project': project,
    })


def weight_project_auto_create_view(request):
    """系统创建项目页（模式B）"""
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/添加项目.html', {
        'project_type': 'auto',
    })


# ---------------------------------------------------------------------------
# API: 项目 CRUD
# ---------------------------------------------------------------------------

@require_GET
def api_weight_project_list(request):
    """获取项目列表"""
    projects = WeightProject.objects.select_related('created_by').all()
    return JsonResponse({
        'projects': [p.to_dict() for p in projects],
    })


@require_POST
def api_weight_project_create(request):
    """创建项目（模式A：手动配置）"""
    data, error = parse_json_body(request)
    if error:
        return error

    name = (data.get('name') or '').strip()
    if not name:
        return err('项目名称不能为空')

    project_path = (data.get('project_path') or '').strip()
    port = data.get('port', 9000)

    try:
        port = int(port)
    except (TypeError, ValueError):
        return err('端口必须为数字')

    if port < 1 or port > 65535:
        return err('端口范围必须在 1-65535 之间')

    project = WeightProject.objects.create(
        name=name,
        description=(data.get('description') or '').strip(),
        project_type=WeightProject.ProjectType.MANUAL,
        project_path=project_path,
        port=port,
        domain=(data.get('domain') or '').strip(),
        auto_start=data.get('auto_start', False),
        created_by=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse({'message': '项目已创建', 'project': project.to_dict()})


@require_POST
def api_weight_project_update(request, pk):
    """更新项目信息"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    data, parse_err = parse_json_body(request)
    if parse_err:
        return parse_err

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return err('项目名称不能为空')
        project.name = name

    if 'description' in data:
        project.description = (data['description'] or '').strip()
    if 'project_path' in data:
        project.project_path = (data['project_path'] or '').strip()
    if 'port' in data:
        try:
            port = int(data['port'])
            if port < 1 or port > 65535:
                return err('端口范围必须在 1-65535 之间')
            project.port = port
        except (TypeError, ValueError):
            return err('端口必须为数字')
    if 'domain' in data:
        project.domain = (data['domain'] or '').strip()
    if 'auto_start' in data:
        project.auto_start = bool(data['auto_start'])

    project.save()
    return JsonResponse({'message': '项目已更新', 'project': project.to_dict()})


@require_POST
def api_weight_project_delete(request, pk):
    """删除项目（如果正在运行则先停止）"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    # 如果正在运行，先停止
    if project.status == WeightProject.Status.RUNNING:
        _stop_project(project)

    project.delete()
    return JsonResponse({'message': '项目已删除'})


# ---------------------------------------------------------------------------
# API: 项目启动/停止/重启/状态
# ---------------------------------------------------------------------------

def _start_project(project: WeightProject) -> tuple[bool, str]:
    """启动项目。返回 (成功?, 消息)"""
    if project.status == WeightProject.Status.RUNNING:
        # 先检查进程是否真实存在
        if project.pid and _is_process_running(project.pid):
            return True, '项目已在运行中'
        else:
            # 进程已不存在，更新状态
            project.status = WeightProject.Status.STOPPED
            project.pid = None
            project.save()

    project_path = os.path.abspath(project.project_path.strip()) if project.project_path else ''
    if not project_path or not os.path.isdir(project_path):
        return False, f'项目目录不存在: {project_path}'

    manage_py = _get_manage_py(project_path)
    if not os.path.isfile(manage_py):
        return False, f'项目目录中没有 manage.py，请确保是有效的 Django 项目'

    # 检查端口
    if not _is_port_available(project.port):
        # 尝试找可用端口
        new_port = _find_available_port(project.port + 1)
        if new_port == 0:
            return False, '无可用端口，请先停止其他项目'
        project.port = new_port

    python_path = _get_python_path(project_path)
    log_path = _get_log_path(project_path, project.port)

    # 检查 Python 是否能导入 Django，不能则自动创建 venv
    try:
        result = subprocess.run(
            [python_path, '-c', 'import django; print(django.__version__)'],
            capture_output=True, text=True, timeout=10,
        )
        can_import_django = result.returncode == 0
    except Exception:
        can_import_django = False

    if not can_import_django:
        # 尝试用 CMS 自身的 Python（当前进程的 Python）创建子项目的 venv
        logger.info('Python %s 没有 Django，自动为项目创建 venv', python_path)
        venv_dir = os.path.join(project_path, '.venv')
        try:
            subprocess.run(
                [sys.executable, '-m', 'venv', venv_dir],
                cwd=project_path, check=True, capture_output=True, timeout=60,
            )
            venv_python = os.path.join(venv_dir, 'bin', 'python')
            if not os.path.exists(venv_python):
                venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
            # 安装 Django
            subprocess.run(
                [venv_python, '-m', 'pip', 'install', 'django'],
                cwd=project_path, check=True, capture_output=True, timeout=120,
            )
            python_path = venv_python
            logger.info('子项目 venv 已创建: %s', venv_dir)
        except Exception as e:
            logger.exception('自动创建 venv 失败')
            return False, f'Python 缺少 Django 且自动创建虚拟环境失败: {str(e)}'

    # 子进程必须使用干净的 env，避免继承父进程的 DJANGO_SETTINGS_MODULE
    clean_env = os.environ.copy()
    clean_env.pop('DJANGO_SETTINGS_MODULE', None)

    try:
        log_file = open(log_path, 'a', encoding='utf-8')
        proc = subprocess.Popen(
            [python_path, 'manage.py', 'runserver', f'0.0.0.0:{project.port}'],
            cwd=project_path,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=clean_env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
            start_new_session=sys.platform != 'win32',  # Linux/macOS 创建新进程组，确保子进程可被一起清理
        )
        project.pid = proc.pid
        project.status = WeightProject.Status.RUNNING
        project.save()
        return True, f'项目已启动 (端口: {project.port})'
    except Exception as e:
        logger.exception('启动项目失败')
        project.status = WeightProject.Status.ERROR
        project.save()
        return False, f'启动失败: {str(e)}'


def _stop_project(project: WeightProject) -> tuple[bool, str]:
    """停止项目。返回 (成功?, 消息)"""
    if project.status != WeightProject.Status.RUNNING or not project.pid:
        project.status = WeightProject.Status.STOPPED
        project.pid = None
        project.save()
        return True, '项目已停止'

    try:
        if sys.platform == 'win32':
            # Windows 下用 taskkill 杀进程树
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(project.pid)],
                           capture_output=True, timeout=5)
        else:
            # 使用 killpg 杀死整个进程组（包含 Django runserver 的子进程）
            try:
                os.killpg(os.getpgid(project.pid), signal.SIGTERM)
            except ProcessLookupError:
                os.kill(project.pid, signal.SIGTERM)
    except Exception:
        logger.warning(f'kill 进程 {project.pid} 失败，可能已退出')

    project.status = WeightProject.Status.STOPPED
    project.pid = None
    project.save()
    return True, '项目已停止'


def _restart_project(project: WeightProject) -> tuple[bool, str]:
    """重启项目。"""
    _stop_project(project)
    return _start_project(project)


def _is_process_running(pid: int) -> bool:
    """检查进程是否在运行。"""
    try:
        if sys.platform == 'win32':
            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                                    capture_output=True, text=True, timeout=5)
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


@require_POST
def api_weight_project_start(request, pk):
    """启动项目"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    success, message = _start_project(project)
    if not success:
        return err(message)
    return JsonResponse({'message': message, 'project': project.to_dict()})


@require_POST
def api_weight_project_stop(request, pk):
    """停止项目"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    success, message = _stop_project(project)
    return JsonResponse({'message': message, 'project': project.to_dict()})


@require_POST
def api_weight_project_restart(request, pk):
    """重启项目"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    success, message = _restart_project(project)
    if not success:
        return err(message)
    return JsonResponse({'message': message, 'project': project.to_dict()})


@require_GET
def api_weight_project_status(request, pk):
    """检查项目运行状态"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    # 如果标记为运行中但进程已不存在，自动修正
    if project.status == WeightProject.Status.RUNNING and project.pid:
        if not _is_process_running(project.pid):
            project.status = WeightProject.Status.STOPPED
            project.pid = None
            project.save()

    return JsonResponse({'project': project.to_dict()})


# ---------------------------------------------------------------------------
# API: 控制台日志
# ---------------------------------------------------------------------------

@require_GET
def api_weight_project_logs(request, pk):
    """获取项目运行日志（末尾 max_lines 行），触发自动备份检查。"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    max_lines = request.GET.get('lines', 200)
    try:
        max_lines = min(int(max_lines), 1000)
    except (TypeError, ValueError):
        max_lines = 200

    log_path = _get_log_path(os.path.abspath(project.project_path) if project.project_path else '', project.port)
    content = _read_log_tail(log_path, max_lines)

    # 自动备份检查
    backup_name = _do_auto_backup(project)

    return JsonResponse({
        'log': content,
        'log_path': log_path,
        'log_size': os.path.getsize(log_path) if os.path.isfile(log_path) else 0,
        'running': project.status == WeightProject.Status.RUNNING,
        'backup': backup_name,
    })


@require_POST
def api_weight_project_clear_log(request, pk):
    """清空项目日志"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    log_path = _get_log_path(os.path.abspath(project.project_path) if project.project_path else '', project.port)
    if os.path.isfile(log_path):
        try:
            open(log_path, 'w').close()
            return JsonResponse({'message': '日志已清空'})
        except Exception as e:
            return err(f'清空失败: {str(e)}')
    return JsonResponse({'message': '日志文件不存在，无需清空'})


# ---------------------------------------------------------------------------
# API: 修复项目迁移
# ---------------------------------------------------------------------------

@require_POST
def api_weight_project_fix_migrations(request, pk):
    """为已有项目重新创建并执行数据库迁移"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    project_path = os.path.abspath(project.project_path.strip()) if project.project_path else ''
    if not project_path or not os.path.isdir(project_path):
        return err('项目目录不存在')

    clean_env = os.environ.copy()
    clean_env.pop('DJANGO_SETTINGS_MODULE', None)
    python_path = _get_python_path(project_path)
    log_path = _get_log_path(project_path, project.port)

    try:
        with open(log_path, 'a', encoding='utf-8') as log:
            log.write(f'\n{"=" * 40}\n[修复迁移] 开始: {__import__("datetime").datetime.now()}\n{"=" * 40}\n')

        # 确保所有 app 都有 migrations/__init__.py
        _ensure_migrations_dirs(project_path)

        result = subprocess.run(
            [python_path, 'manage.py', 'makemigrations'],
            cwd=project_path, capture_output=True, timeout=60, env=clean_env,
        )
        with open(log_path, 'a', encoding='utf-8') as log:
            log.write(f'[makemigrations] exit={result.returncode}\n')
            log.write((result.stdout or b'').decode('utf-8', errors='replace'))
            log.write((result.stderr or b'').decode('utf-8', errors='replace'))

        result = subprocess.run(
            [python_path, 'manage.py', 'migrate'],
            cwd=project_path, capture_output=True, timeout=60, env=clean_env,
        )
        with open(log_path, 'a', encoding='utf-8') as log:
            log.write(f'[migrate] exit={result.returncode}\n')
            log.write((result.stdout or b'').decode('utf-8', errors='replace'))
            log.write((result.stderr or b'').decode('utf-8', errors='replace'))

        if result.returncode != 0:
            return err(f'迁移执行失败 (exit={result.returncode})，请查看控制台日志')

        return JsonResponse({'message': '数据库迁移已修复，请重启项目'})
    except subprocess.TimeoutExpired:
        return err('迁移操作超时')
    except Exception as e:
        logger.exception('修复迁移异常')
        return err(f'修复异常: {str(e)}')


# ---------------------------------------------------------------------------
# 页面视图: 控制台
# ---------------------------------------------------------------------------

def weight_project_console_view(request, pk):
    """项目控制台页"""
    project = get_object_or_404(WeightProject, pk=pk)
    return render(request, 'XiaoYingAdmin/页面管理/权重页面项目/控制台.html', {
        'project': project,
    })


# ---------------------------------------------------------------------------
# API: 模式B - 从模板创建项目
# ---------------------------------------------------------------------------

@require_POST
def api_weight_project_create_from_template(request):
    """从内置模板创建 Django 项目（模式B）"""
    data, error = parse_json_body(request)
    if error:
        return error

    name = (data.get('name') or '').strip()
    if not name:
        return err('项目名称不能为空')

    port = data.get('port', 9000)
    try:
        port = int(port)
        if port < 1 or port > 65535:
            return err('端口范围必须在 1-65535 之间')
    except (TypeError, ValueError):
        return err('端口必须为数字')

    # 检查模板目录是否存在
    if not os.path.isdir(TEMPLATE_PROJECT_DIR):
        return err('系统项目模板不存在，请联系管理员')

    # 生成项目目录：在小影CMS 同级目录下创建 weight_projects/{name}/
    cms_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    projects_root = os.path.join(cms_root, '..', 'weight_projects')
    os.makedirs(projects_root, exist_ok=True)

    project_dir = os.path.join(projects_root, name)
    if os.path.exists(project_dir):
        return err(f'目录已存在: {project_dir}，请更换项目名称')

    # 复制模板到目标目录
    import shutil
    try:
        shutil.copytree(TEMPLATE_PROJECT_DIR, project_dir)
    except Exception as e:
        logger.exception('复制模板失败')
        return err(f'创建项目失败: {str(e)}')

    # 替换模板中的占位符（如果有）
    _replace_template_vars(project_dir, name, port)

    # 确保各 app 有 migrations/__init__.py（模板中已包含，双重保障）
    _ensure_migrations_dirs(project_dir)

    # 子进程必须使用干净的 env，避免继承父进程的 DJANGO_SETTINGS_MODULE
    clean_env = os.environ.copy()
    clean_env.pop('DJANGO_SETTINGS_MODULE', None)

    # 创建虚拟环境并安装依赖
    venv_dir = os.path.join(project_dir, '.venv')
    try:
        subprocess.run([sys.executable, '-m', 'venv', venv_dir], cwd=project_dir, check=True,
                       capture_output=True, timeout=60, env=clean_env)
        python_path = os.path.join(venv_dir, 'Scripts', 'python.exe')
        # 安装 Django
        subprocess.run([python_path, '-m', 'pip', 'install', 'django'],
                       cwd=project_dir, check=True, capture_output=True, timeout=120, env=clean_env)
        # 创建并执行数据库迁移
        subprocess.run([python_path, 'manage.py', 'makemigrations'],
                       cwd=project_dir, check=True, capture_output=True, timeout=60, env=clean_env)
        subprocess.run([python_path, 'manage.py', 'migrate'],
                       cwd=project_dir, check=True, capture_output=True, timeout=60, env=clean_env)
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr.decode('utf-8', errors='replace') if e.stderr else ''
        stdout_text = e.stdout.decode('utf-8', errors='replace') if e.stdout else ''
        full_output = (stderr_text + '\n' + stdout_text).strip()
        logger.error(f'初始化项目失败:\n{full_output[:1000]}')
        shutil.rmtree(project_dir, ignore_errors=True)
        # 截取有用信息：取最后200字符（通常是真正的错误信息）
        error_msg = full_output[-300:] if len(full_output) > 300 else full_output
        return err(f'项目初始化失败: {error_msg}')
    except Exception as e:
        logger.exception('初始化项目异常')
        shutil.rmtree(project_dir, ignore_errors=True)
        return err(f'项目初始化异常: {str(e)}')

    # 创建数据库记录
    project = WeightProject.objects.create(
        name=name,
        description=(data.get('description') or '').strip(),
        project_type=WeightProject.ProjectType.AUTO,
        project_path=project_dir,
        port=port,
        domain=(data.get('domain') or '').strip(),
        auto_start=data.get('auto_start', False),
        created_by=request.user if request.user.is_authenticated else None,
    )

    return JsonResponse({
        'message': '项目已创建并初始化完成',
        'project': project.to_dict(),
    })


def _replace_template_vars(project_dir: str, project_name: str, port: int):
    """替换模板项目中的占位符变量。"""
    # 替换 settings.py 中的项目名称等
    settings_py = os.path.join(project_dir, project_name, 'settings.py')
    alt_settings = os.path.join(project_dir, 'mysite', 'settings.py')
    for sp in [settings_py, alt_settings]:
        if os.path.isfile(sp):
            try:
                with open(sp, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace('{{ project_name }}', project_name)
                content = content.replace('{{ port }}', str(port))
                with open(sp, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception:
                logger.warning(f'替换占位符失败: {sp}')


# ---------------------------------------------------------------------------
# 反向代理 — 让子项目流量经过小影CMS中间件链
# ---------------------------------------------------------------------------

def _forward_headers(source_meta: dict) -> dict:
    """从 request.META 提取需要转发的 HTTP 头。"""
    headers = {}
    for key, value in source_meta.items():
        if key.startswith('HTTP_'):
            header_name = key[5:].replace('_', '-').title()
            # 跳过 Django 自动添加的头和被代理设置的头
            if header_name in ('Host', 'X-Forwarded-For', 'X-Forwarded-Proto',
                               'X-Forwarded-Host', 'Connection', 'Proxy-Connection',
                               'Transfer-Encoding', 'Content-Length'):
                continue
            headers[header_name] = value
    # 添加 X-Forwarded-For 追踪真实 IP
    xff = source_meta.get('HTTP_X_FORWARDED_FOR', '')
    remote_addr = source_meta.get('REMOTE_ADDR', '')
    if xff:
        headers['X-Forwarded-For'] = f'{xff}, {remote_addr}'
    elif remote_addr:
        headers['X-Forwarded-For'] = remote_addr
    return headers


def _proxy_request(method: str, target_url: str, headers: dict,
                   body: bytes | None = None, timeout: int = 30):
    """执行 HTTP 请求并返回 (status_code, headers_dict, body)"""
    try:
        req = urllib.request.Request(target_url, data=body if body else None,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read()
            resp_headers = dict(resp.headers)
            return resp.status, resp_headers, resp_body
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        logger.warning(f'代理请求失败: {target_url} → {e.reason}')
        return 502, {'Content-Type': 'text/plain; charset=utf-8'}, str(e.reason).encode('utf-8')


# 不需要重写的路径前缀（CMS 自身的路径）
_SKIP_REWRITE_PREFIXES = ('/xiaoying_admin/', '/cdn-cgi/', '/static/admin/',)


def _rewrite_html_paths(html: str, proxy_prefix: str, encoding: str = 'utf-8') -> str:
    """重写 HTML 中的绝对路径，将子项目的静态/API路径替换为代理路径。

    例如: src="/static/foo.js" → src="/xiaoying_admin/wp-proxy/1/static/foo.js"
    但不会重写 CMS 自身的路径（/xiaoying_admin/...）
    """
    if isinstance(html, bytes):
        html = html.decode(encoding, errors='replace')

    def _should_skip(path: str) -> bool:
        if not path.startswith('/') or path.startswith('//') or path.startswith(proxy_prefix):
            return True
        for prefix in _SKIP_REWRITE_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    def _replacer(m):
        attr = m.group(1)
        quote = m.group(2)
        path = m.group(3)
        if _should_skip(path):
            return m.group(0)
        return f'{attr}={quote}{proxy_prefix}{path}{quote}'

    # src="/..." 和 href="/..."
    html = re.sub(r'(src|href)=(["\'])(/[^"\']*?)\2', _replacer, html)
    # url('/...') 和 url("/...")（CSS 中的引用）
    html = re.sub(r'(url\()(["\'])(/[^"\'()]*?)\2', _replacer, html)

    return html


@csrf_exempt
def weight_project_proxy_view(request, pk, subpath=''):
    """反向代理：将请求转发到权重页面项目，返回子项目的响应。

    工作流程：
      1. 请求 → 小影CMS 中间件链（防火墙/蜘蛛日志/SEO斗篷等）
      2. 此视图将请求转发到子项目的 Django dev server
      3. 子项目的响应原样返回给客户端

    通过此方式访问时，防火墙、蜘蛛日志、SEO斗篷等中间件全部生效。
    """
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    # 检查项目状态
    if project.status != WeightProject.Status.RUNNING:
        return HttpResponse(
            f'<h1 style="text-align:center;margin-top:15%;color:#999;">'
            f'项目「{project.name}」未运行<br>'
            f'<span style="font-size:14px;">请先在权重页面项目中启动该项目</span></h1>',
            status=502, content_type='text/html; charset=utf-8',
        )

    # 验证项目路径
    project_path = os.path.abspath(project.project_path) if project.project_path else ''
    if not project_path or not os.path.isdir(project_path):
        return HttpResponse('项目目录不存在', status=502)

    # 构建转发 URL
    target_url = f'http://localhost:{project.port}/{subpath}'
    if request.META.get('QUERY_STRING'):
        target_url += f'?{request.META["QUERY_STRING"]}'

    # 转发请求头
    headers = _forward_headers(request.META)
    # 设置 Host 为 localhost:port 使子项目的 Django 能正确处理
    headers['Host'] = f'localhost:{project.port}'

    # 获取请求体
    body = request.body if request.method in ('POST', 'PUT', 'PATCH') else None

    # 执行代理请求
    status_code, resp_headers, resp_body = _proxy_request(
        request.method, target_url, headers, body,
    )

    # 构建 Django 响应
    content_type = resp_headers.get('Content-Type', 'text/html; charset=utf-8')

    # 对 HTML 响应重写静态路径，使子项目的/src="/..."正确指向代理路径
    proxy_prefix = f'/xiaoying_admin/wp-proxy/{pk}'
    if 'text/html' in content_type and isinstance(resp_body, (str, bytes)):
        resp_body = _rewrite_html_paths(resp_body, proxy_prefix).encode('utf-8')
        content_type = 'text/html; charset=utf-8'

    response = HttpResponse(
        content=resp_body,
        status=status_code,
        content_type=content_type,
    )

    # 转发关键响应头
    for header_name in ('Set-Cookie', 'Location', 'Cache-Control',
                        'Expires', 'Pragma', 'X-Frame-Options'):
        value = resp_headers.get(header_name)
        if value:
            response[header_name] = value

    return response


# ---------------------------------------------------------------------------
# API: 日志备份管理
# ---------------------------------------------------------------------------

@require_GET
def api_weight_project_backup_list(request, pk):
    """获取项目的日志备份文件列表"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    project_path = os.path.abspath(project.project_path) if project.project_path else ''
    if not project_path or not os.path.isdir(project_path):
        return JsonResponse({'backups': []})

    backup_dir = _get_backup_dir(project_path)
    backups = []
    if os.path.isdir(backup_dir):
        for fname in os.listdir(backup_dir):
            if fname.startswith(f'django-{project.port}-backup-') and fname.endswith('.log'):
                fpath = os.path.join(backup_dir, fname)
                if os.path.isfile(fpath):
                    mtime = os.path.getmtime(fpath)
                    from datetime import datetime
                    backups.append({
                        'filename': fname,
                        'size_bytes': os.path.getsize(fpath),
                        'size_str': (
                            f'{os.path.getsize(fpath) / 1024:.1f} KB'
                            if os.path.getsize(fpath) < 1024 * 1024
                            else f'{os.path.getsize(fpath) / 1024 / 1024:.2f} MB'
                        ),
                        'modified': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    })
    # 按时间倒序
    backups.sort(key=lambda x: x['modified'], reverse=True)
    return JsonResponse({'backups': backups})


@require_GET
def api_weight_project_backup_download(request, pk):
    """下载指定的日志备份文件"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    filename = request.GET.get('filename', '')
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return err('无效的文件名')

    project_path = os.path.abspath(project.project_path) if project.project_path else ''
    if not project_path or not os.path.isdir(project_path):
        return err('项目目录不存在')

    backup_path = os.path.join(_get_backup_dir(project_path), filename)
    if not os.path.isfile(backup_path):
        return err('备份文件不存在')

    from django.http import FileResponse
    response = FileResponse(open(backup_path, 'rb'), content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@require_POST
def api_weight_project_save_backup_config(request, pk):
    """保存日志备份配置"""
    project, error = get_or_404(WeightProject, pk=pk)
    if error:
        return error

    data, parse_err = parse_json_body(request)
    if parse_err:
        return parse_err

    threshold = data.get('auto_backup_threshold', 0)
    try:
        threshold = int(threshold)
    except (TypeError, ValueError):
        return err('阈值必须为数字')

    if threshold < 0:
        return err('阈值不能为负数')

    project.auto_backup_threshold = threshold
    project.save(update_fields=['auto_backup_threshold', 'updated_time'])

    return JsonResponse({
        'message': f'备份阈值已设置为 {threshold} 行' if threshold > 0 else '自动备份已关闭',
        'auto_backup_threshold': threshold,
    })
