from playwright.sync_api import sync_playwright


def save_login_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 必须有头模式
        context = browser.new_context()
        page = context.new_page()

        print("请在浏览器中扫码登录知乎...")
        page.goto("https://www.zhihu.com/signin")

        # 等待直到你登录成功（检测到头像元素出现，或者手动等待时间）
        # 这里简单粗暴等待 60秒给你扫码
        page.wait_for_timeout(60000)

        # 保存状态
        context.storage_state(path="storage_state.json")
        print("登录状态已保存至 storage_state.json")
        browser.close()


if __name__ == "__main__":
    save_login_state()