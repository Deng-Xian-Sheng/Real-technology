在控制台输入此js
当点击某个笔记的时候，该笔记内的所有图片均会下载到本地。

已知局限性：
 - 一次只能下载一个笔记的图片
 - 某些图片下载后为webp格式
 - 图片下载后无后缀名
 - 某些图片在控制台报告404，无法下载

使用场景：
用于小规模场景，特定笔记的图片下载。

如果你需要多个笔记的下载，可以向我支付1w元人民币，我将帮助你实现这个，由于小红书算法非常复杂，所以，效果可能不如下载单个笔记那样稳定。

```js
// 配置需要拦截的路径关键词（支持字符串或正则表达式）
const interceptRoutes = ['api/sns/web/v1/feed'];

// 保存原生方法
const nativeOpen = XMLHttpRequest.prototype.open;
const nativeSend = XMLHttpRequest.prototype.send;
const nativeFetch = window.fetch;

// 拦截 XMLHttpRequest
XMLHttpRequest.prototype.open = function(method, url) {
  this._url = url;
  return nativeOpen.apply(this, arguments);
};

XMLHttpRequest.prototype.send = function(body) {
  if (interceptRoutes.some(route => {
    if (typeof route === 'string') return this._url.includes(route);
    return route.test(this._url);
  })) {
    const originalOnreadystatechange = this.onreadystatechange;
    
    this.onreadystatechange = function() {
      if (this.readyState === 4) {
        console.log('[XHR 拦截]', this._url, {
          status: this.status,
          response: tryParseJSON(this.response)
        });
        // 新增响应处理逻辑
        const responseData = tryParseJSON(this.response);
        processResponseData(responseData);
      }
      originalOnreadystatechange?.apply(this, arguments);
    };
  }
  return nativeSend.apply(this, arguments);
};

// 拦截 Fetch
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : input.url;
  
  if (interceptRoutes.some(route => {
    if (typeof route === 'string') return url.includes(route);
    return route.test(url);
  })) {
    const response = await nativeFetch(input, init);
    const clone = response.clone();
    
    console.log('[Fetch 拦截]', url, {
      status: response.status,
      response: await tryParseResponse(clone)
    });
    // 新增响应处理逻辑
    const data = await tryParseResponse(clone);
    processResponseData(data);
    
    return response;
  }
  return nativeFetch(input, init);
};

// 辅助函数：尝试解析 JSON
function tryParseJSON(str) {
  try {
    return JSON.parse(str);
  } catch {
    return str;
  }
}

// 辅助函数：尝试解析响应内容
async function tryParseResponse(response) {
  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    return await response.json();
  }
  return await response.text();
}

// 截取URL关键部分
function extractPart(url) {
  const parts = url.split('/');
  const lastPart = parts[parts.length - 1];
  return lastPart.split('!')[0];
}

// 下载图片核心逻辑
async function downloadImage(url) {
  try {
    const response = await fetch(url, { 
      // mode: 'cors',
      // credentials: 'include'
    });
    
    if (!response.ok) throw new Error(`HTTP错误! 状态码: ${response.status}`);
    
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = url.split('/').pop().split('?')[0];
    document.body.appendChild(a);
    a.click();
    
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    }, 100);
    
  } catch (error) {
    console.error('图片下载失败:', error);
  }
}

// 处理接口响应数据
function processResponseData(data) {
  if (data?.data?.items) {
    data.data.items.forEach(item => {
      const imageList = item.note_card?.image_list;
      if (imageList) {
        imageList.forEach(image => {
          const originalUrl = image.url_default;
          if (originalUrl) {
            // 构造新下载地址
            const resourceId = extractPart(originalUrl);
            const targetUrl = new URL(
              `http://sns-na-i3.xhscdn.com/${resourceId}`
            );
            targetUrl.search = 'imageView2/2/w/1440/format/heif/q/45&redImage/frame/0&ap=1&sc=DETAIL';
            
            console.log('生成下载地址:', targetUrl.href);
            downloadImage(targetUrl.href);
          }
        });
      }
    });
  }
}

console.log('增强版请求拦截器已激活');
```
