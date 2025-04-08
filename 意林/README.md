# 这里是意林，深度学习数据集，欢迎来到意林，我娇贵的小公主

```python
import requests
from bs4 import BeautifulSoup
import html2text
from urllib.parse import urljoin
import os
import re
import urllib3
import time

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置参数
MAIN_URL = "https://www.yilinzazhi.com/"
OUTPUT_DIR = "yilin_articles"

# 将提供的请求标头统一放在这里
# 注意：其中以 ":" 开头的伪首部（如 :authority、:method 等）在某些场景下并不是真正的请求头，
# 只在 HTTP/2 中作为伪首部来传递，这里示例性地一并写入，但实际可能无法全部生效。
CUSTOM_HEADERS = {
    "authority": "www.yilinzazhi.com",
    "method": "GET",
    "path": "/",
    "scheme": "https",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
              "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6",
    "cache-control": "no-cache",
    "cookie": "Hm_lvt_46020bfb3065f0421b46f5e268865b1d=1744087755; HMACCOUNT=AE419A15DFFA205B;"
              " Hm_lpvt_46020bfb3065f0421b46f5e268865b1d=1744091811",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "referer": "https://www.bing.com/",
    "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Microsoft Edge\";v=\"134\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Linux\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "cross-site",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
}

# 创建一个全局的 Session，并更新默认的请求头（也可以直接在 get/post 中传 headers）
session = requests.Session()
session.headers.update(CUSTOM_HEADERS)

HTML2TEXT_HANDLER = html2text.HTML2Text()
HTML2TEXT_HANDLER.body_width = 0  # 禁用自动换行

def sanitize_filename(title):
    """清理标题中的非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def fetch_page(url):
    """获取页面内容并返回BeautifulSoup对象"""
    try:
        response = session.get(url, timeout=10, verify=False)
        response.raise_for_status()
        # 使用原始内容进行解析以自动检测编码
        return BeautifulSoup(response.content, "html.parser")
    except Exception as e:
        print(f"请求页面失败: {url} - {str(e)}")
        return None

def parse_issues(main_soup):
    """
    解析主页获取所有期刊链接和标题。
    返回列表，每个元素为 (期刊标题, 期刊链接) 的元组。
    """
    issues = []
    for section in main_soup.find_all("div", class_="year-section"):
        for link in section.select("ul.issue-list a"):
            issue_title = link.get_text(strip=True)
            issue_url = urljoin(MAIN_URL, link["href"])
            issues.append((issue_title, issue_url))
    return issues

def parse_articles(issue_url):
    """解析期刊页面获取所有文章链接"""
    soup = fetch_page(issue_url)
    if not soup:
        return []
    
    articles = []
    
    # 新版页面结构
    catalog_sections = soup.find_all("section", class_="catalog-section")
    for section in catalog_sections:
        for item in section.select("div.article-item a"):
            articles.append(urljoin(issue_url, item["href"]))
    
    # 旧版页面结构
    if not articles:
        for mag_title in soup.find_all("span", class_="maglisttitle"):
            if mag_title.a:
                articles.append(urljoin(issue_url, mag_title.a["href"]))
    
    return articles

def parse_article(article_url):
    """解析文章页面获取内容和标题"""
    soup = fetch_page(article_url)
    if not soup:
        return None, None
    
    # 获取标题（新版结构）
    title_tag = soup.find("h1", class_="article-title")
    if not title_tag:
        # 旧版结构
        title_container = soup.find("div", class_=lambda x: x and "blkContainerSblk" in x)
        title_tag = title_container.find("h1") if title_container else None
    
    if not title_tag:
        return None, None
    
    title = title_tag.get_text(strip=True)
    
    # 获取内容（新版结构）
    content_div = soup.find("div", class_="article-content")
    if not content_div:
        # 旧版结构
        content_div = soup.find("div", class_=lambda x: x and "blkContainerSblkCon" in x)
        if content_div:
            # 移除广告内容
            for ad in content_div.find_all("div", class_="contentAd"):
                ad.decompose()
    
    if not content_div:
        return title, None
    
    # 转换为Markdown
    markdown_content = HTML2TEXT_HANDLER.handle(str(content_div)).strip()
    return title, f"# {title}\n\n{markdown_content}"

def save_article(title, content, issue_title):
    """保存文章到Markdown文件，并在文件名中包含所属期刊"""
    if not content:
        return
    
    # 在文件名开头添加所属期刊
    # 例如：2024年第19期 - 不落下一只蚂蚁.md
    filename = f"{sanitize_filename(issue_title)} - {sanitize_filename(title)}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"成功保存: {filename}")
    except Exception as e:
        print(f"保存文件失败: {filename} - {str(e)}")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 获取主页面
    main_soup = fetch_page(MAIN_URL)
    if not main_soup:
        return
    
    # 获取所有期刊链接和期刊标题
    issues = parse_issues(main_soup)
    print(f"发现 {len(issues)} 期期刊")
    
    # 遍历每个期刊
    for issue_title, issue_url in issues:
        print(f"\n正在处理期刊: {issue_title}（{issue_url}）")
        
        # 获取期刊中的文章列表
        articles = parse_articles(issue_url)
        print(f"发现 {len(articles)} 篇文章")
        
        # 处理每篇文章
        for article_url in articles:
            print(f"正在抓取文章: {article_url}")
            title, content = parse_article(article_url)
            if content:
                save_article(title, content, issue_title)
            
            # 略微休眠，避免过快请求目标站点
            time.sleep(0.2)

if __name__ == "__main__":
    main()

```
