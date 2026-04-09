// JS/navbar.js
document.addEventListener('DOMContentLoaded', () => {
    // 1. 智能判断路径：统一转换为小写进行判断，避免因本地环境/浏览器不同导致的大小写匹配失败
    const currentPath = window.location.pathname.toLowerCase();
    const currentHref = window.location.href.toLowerCase();
    const isSubFolder = currentPath.includes('/html/') || currentHref.includes('/html/');
    
    const rootPath = isSubFolder ? '../' : './';
    const htmlPath = isSubFolder ? './' : 'Html/';

    // 2. 统一的导航栏 HTML 模板
    // 修复：为下拉菜单里的 <a> 标签补充了 class="nav-link"，这样它们才能被下方的高亮逻辑捕捉到
    const navHtml = `
      <div class="container nav">
        <div class="brand">社会雷达 · Social Radar</div>
        <nav class="menu">
          <a href="${rootPath}index.html" class="nav-link">首页</a>
          <div class="dropdown">
            <a href="javascript:void(0)" class="dropbtn">数据分析 ▾</a>
            <div class="dropdown-content">
              <a href="${htmlPath}zhihu_data.html" class="nav-link">知乎</a>
              <a href="${htmlPath}weibo_data.html" class="nav-link">微信公众号</a>
              <a href="${htmlPath}xiaohongshu.html" class="nav-link">小红书</a>
            </div>
          </div>
          <a href="${htmlPath}analysis.html" class="nav-link">CSV分析</a>
          <a href="${htmlPath}academic_trends.html" class="nav-link">学术动态</a>
          <a href="${htmlPath}work.html" class="nav-link">我们的工作</a>
          
          <button id="theme-toggle" class="theme-btn" title="切换主题">
            <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          </button>
        </nav>
      </div>
    `;

    // 3. 将模板注入到页面的 <header> 中
    const headerEl = document.getElementById('common-header');
    if (headerEl) {
        headerEl.innerHTML = navHtml;
        
        // 4. 自动高亮当前所在的页面 (active 状态)
        let currentFilename = window.location.pathname.split('/').pop();
        // 修复：如果是在根目录(如 / 或者 /socialradarweb-main/)，默认视为 index.html
        if (!currentFilename || currentFilename === '') {
            currentFilename = 'index.html';
        }
        
        const links = headerEl.querySelectorAll('.nav-link');
        links.forEach(link => {
            const href = link.getAttribute('href');
            if (href && href.includes(currentFilename)) {
                link.classList.add('active');
                
                // 附加功能：如果当前激活的是下拉菜单里的页面（比如 weibo_data.html），让主菜单的“数据分析”也保持高亮
                const parentDropdown = link.closest('.dropdown');
                if(parentDropdown) {
                    parentDropdown.querySelector('.dropbtn').classList.add('active');
                }
            }
        });

        // 5. 初始化深色/浅色主题切换逻辑
        initThemeToggle();
    } else {
        console.warn('导航栏加载失败：当前页面缺少 <header id="common-header"></header> 容器。');
    }
});

function initThemeToggle() {
    const toggleBtn = document.getElementById('theme-toggle');
    const root = document.documentElement;
    
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        root.setAttribute('data-theme', 'dark');
        updateIcon(true);
    }

    toggleBtn.addEventListener('click', () => {
        const isDark = root.getAttribute('data-theme') === 'dark';
        root.setAttribute('data-theme', isDark ? 'light' : 'dark');
        localStorage.setItem('theme', isDark ? 'light' : 'dark');
        updateIcon(!isDark);
    });

    function updateIcon(isDark) {
        if(isDark) {
             toggleBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>';
        } else {
             toggleBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        }
    }
}