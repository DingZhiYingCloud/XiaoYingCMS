# 页面路由
from django.urls import path
from XiaoYingAdmin.views import request as admin_request
from XiaoYingAdmin.views.auth import (
    login_view, logout_view,
    register_view, forgot_password_view,
    change_password_view,
    user_list_view, user_create_view, user_edit_view,
    user_toggle_active_api, user_delete_api,
    user_info_api,
    login_log_view, login_log_list_api,
    operation_log_view, operation_log_list_api,
)
from XiaoYingAdmin.views.seo.blackhat.cloak import seo_cloak_view, seo_cloak_config_save
from XiaoYingAdmin.views.spider.logs import (
    spider_logs_view,
    spider_logs_api_list,
    spider_logs_api_clear,
    spider_logs_api_export,
)

# 域名前缀: /xiaoying_admin/
urlpatterns = [
    # 认证（无需登录）
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('forgot_password/', forgot_password_view, name='forgot_password'),

    # 认证（需登录）
    path('change_password/', change_password_view, name='change_password'),

    # 用户管理（需管理员权限）
    path('users/', user_list_view, name='user_list'),
    path('users/create/', user_create_view, name='user_create'),
    path('users/<int:pk>/edit/', user_edit_view, name='user_edit'),

    # AJAX API: 用户管理
    path('users/<int:pk>/toggle_active/', user_toggle_active_api, name='user_toggle_active'),
    path('users/<int:pk>/delete/', user_delete_api, name='user_delete'),
    path('api/user/info/', user_info_api, name='user_info_api'),

    # 登录日志
    path('login_logs/', login_log_view, name='login_logs'),
    path('api/login_logs/list/', login_log_list_api, name='login_logs_api_list'),

    # 操作日志
    path('operation_logs/', operation_log_view, name='operation_logs'),
    path('api/operation_logs/list/', operation_log_list_api, name='operation_logs_api_list'),

    # 页面
    path('template/', admin_request.template_view, name='template'),
    path('index/', admin_request.index_view, name='index'),
    path('site_settings/', admin_request.site_settings_view, name='site_settings'),
    path('pages/generate/', admin_request.page_generate_view, name='page_generate'),
    path('pages/list/', admin_request.page_list_view, name='page_list'),

    # AJAX API: 页面生成
    path('api/generate/start/', admin_request.api_start_generate, name='api_generate_start'),
    path('api/generate/progress/<uuid:task_id>/', admin_request.api_get_progress, name='api_generate_progress'),

    # AJAX API: 提示词管理
    path('api/prompts/', admin_request.api_prompt_list, name='api_prompt_list'),
    path('api/prompts/<int:prompt_id>/', admin_request.api_prompt_detail, name='api_prompt_detail'),
    path('api/prompts/save/', admin_request.api_prompt_save, name='api_prompt_save'),
    path('api/prompts/activate/', admin_request.api_prompt_activate, name='api_prompt_activate'),
    path('api/prompts/delete/', admin_request.api_prompt_delete, name='api_prompt_delete'),

    # SEO：斗篷伪装（黑帽）
    path('seo/cloak/', seo_cloak_view, name='seo_cloak'),
    path('seo/cloak/api/config/save/', seo_cloak_config_save, name='seo_cloak_config_save'),

    # AJAX API: 已保存页面
    path('api/pages/saved/', admin_request.api_saved_pages, name='api_saved_pages'),
    path('api/pages/saved/<int:page_id>/', admin_request.api_saved_page_detail, name='api_saved_page_detail'),
    path('api/pages/saved/set-domain/', admin_request.api_saved_page_set_domain, name='api_saved_page_set_domain'),
    path('api/pages/saved/delete/', admin_request.api_saved_page_delete, name='api_saved_page_delete'),
    path('api/pages/saved/update/', admin_request.api_saved_page_update, name='api_saved_page_update'),

    # 蜘蛛访问日志
    path('spider/logs/', spider_logs_view, name='spider_logs'),
    path('spider/logs/api/list/', spider_logs_api_list, name='spider_logs_api_list'),
    path('spider/logs/api/clear/', spider_logs_api_clear, name='spider_logs_api_clear'),
    path('spider/logs/api/export/', spider_logs_api_export, name='spider_logs_api_export'),
]
