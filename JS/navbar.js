// JS/navbar.js
document.addEventListener('DOMContentLoaded', () => {
    // 1. 智能判断路径：因为主页在根目录，而其他页面在 Html/ 文件夹下
    // 所以需要自动判断相对路径的前缀
    const isSubFolder = window.location.pathname.includes('/Html/') || window.location.href.includes('/Html/');
    const rootPath = isSubFolder ? '../' : './';
    const htmlPath = isSubFolder ? './' : 'Html/';

    // 2. 统一的导航栏 HTML 模板（在这里修改，所有页面都会生效）
    const navHtml = `
      <div class="container nav">
        <div class="brand">社会雷达 · Social Radar</div>
        <nav class="menu">
          <a href="${rootPath}index.html" class="nav-link">首页</a>
          <div class="dropdown">
            <a href="javascript:void(0)" class="dropbtn nav-link">数据分析</a>
            <div class="dropdown-content">
              <a href="${htmlPath}zhihu_data.html">知乎</a>
              <a href="${htmlPath}weibo_data.html">微信公众号</a>
              <a href="${htmlPath}xiaohongshu.html">小红书</a>
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
        const currentFilename = window.location.pathname.split('/').pop() || 'index.html';
        const links = headerEl.querySelectorAll('.nav-link');
        links.forEach(link => {
            if (link.getAttribute('href').includes(currentFilename)) {
                link.classList.add('active');
            }
        });

        // 5. 初始化深色/浅色主题切换逻辑
        initThemeToggle();
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