from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Article


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('index')
        messages.error(request, '用户名或密码错误')
    return render(request, 'login.html')


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if not username or not password:
            messages.error(request, '请填写完整信息')
        elif password != password2:
            messages.error(request, '两次密码不一致')
        elif User.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在')
        else:
            User.objects.create_user(username=username, password=password)
            messages.success(request, '注册成功，请登录')
            return redirect('login')
    return render(request, 'register.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def index_view(request):
    recent_articles = Article.objects.filter(author=request.user)[:5]
    total = Article.objects.filter(author=request.user).count()
    return render(request, 'index.html', {
        'articles': recent_articles,
        'total': total,
    })


@login_required
def article_list_view(request):
    articles = Article.objects.filter(author=request.user)
    return render(request, 'article_list.html', {'articles': articles})


@login_required
def article_create_view(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        if title and content:
            Article.objects.create(title=title, content=content, author=request.user)
            messages.success(request, '文章已创建')
            return redirect('article_list')
        messages.error(request, '标题和内容不能为空')
    return render(request, 'article_form.html', {'mode': 'create'})


@login_required
def article_detail_view(request, pk):
    article = get_object_or_404(Article, pk=pk, author=request.user)
    return render(request, 'article_detail.html', {'article': article})


@login_required
def article_edit_view(request, pk):
    article = get_object_or_404(Article, pk=pk, author=request.user)
    if request.method == 'POST':
        article.title = request.POST.get('title', '').strip()
        article.content = request.POST.get('content', '').strip()
        article.save()
        messages.success(request, '文章已更新')
        return redirect('article_detail', pk=article.pk)
    return render(request, 'article_form.html', {'article': article, 'mode': 'edit'})


@login_required
def article_delete_view(request, pk):
    article = get_object_or_404(Article, pk=pk, author=request.user)
    article.delete()
    messages.success(request, '文章已删除')
    return redirect('article_list')
