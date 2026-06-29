# 页面路由
from django.urls import path
from XiaoYingAdmin.views import request as admin_request
from XiaoYingAdmin.views.seo.blackhat.cloak import seo_cloak_view, seo_cloak_config_save

# 域名前缀: /xiaoying_admin/
urlpatterns = [
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
]
