// ==UserScript==
// @name         基于大模型的哔哩哔哩视频广告后置油猴脚本（修复版）
// @namespace    https://example.com/
// @version      0.0.3
// @description  将哔哩哔哩视频中的广告在播放结束后再播放，提升观感体验
// @match        https://www.bilibili.com/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    // 全局变量：用于保存视频信息数据（包含 bvid、cid、subtitles 等）
    let videoInfo = null;

    /*---------------------------
      1. 拦截获取视频信息的请求
    ---------------------------*/
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this._url = url;
        return originalOpen.call(this, method, url, ...rest);
    };

    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(body) {
        this.addEventListener('load', function() {
            if (this._url && this._url.includes('api.bilibili.com/x/player/wbi/v2')) {
                try {
                    const data = JSON.parse(this.responseText);
                    console.log('拦截到了返回数据 xhr:', data);
                    // 保存到全局变量
                    videoInfo = data;
                    handleVideoInfo();
                } catch (e) {
                    console.warn('解析返回数据失败 xhr:', e);
                }
            }
        });
        return originalSend.call(this, body);
    };

    /**
     * 当我们拿到了完整的 videoInfo，执行后续逻辑：
     * 1. 获取字幕链接
     * 2. 请求字幕数据
     * 3. 通过 OpenAI API 分析广告区间
     * 4. 绑定 video 事件，跳过广告并在结尾播放
     */
    function handleVideoInfo() {
        // 确保结构正常
        if (!videoInfo.data || 
            !videoInfo.data.subtitle || 
            !videoInfo.data.subtitle.subtitles || 
            !videoInfo.data.subtitle.subtitles.length
        ) {
            console.log('没有找到字幕链接');
            return;
        }

        // 取第一个字幕的 subtitle_url
        const subtitleInfo = videoInfo.data.subtitle.subtitles[0];
        if (!subtitleInfo) {
            console.log('没有找到字幕链接');
            return;
        }

        // 补全 URL
        const url = 'https:' + subtitleInfo.subtitle_url;
        // 使用 GM_xmlhttpRequest 请求字幕文本
        GM_xmlhttpRequest({
            method: 'GET',
            url: url,
            headers: {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6',
                'cache-control': 'no-cache',
                'origin': 'https://www.bilibili.com',
                'pragma': 'no-cache',
                'referer': `https://www.bilibili.com/video/${videoInfo.data.bvid}/?spm_id_from=333.337.search-card.all.click`,
                'sec-ch-ua': `"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"`,
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': `"Linux"`,
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'cross-site',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
            },
            onload: function(response) {
                if (response.status === 200) {
                    console.log('字幕请求成功，响应数据:', response.responseText);
                    let subtitleData;
                    try {
                        subtitleData = JSON.parse(response.responseText);
                    } catch (err) {
                        console.error('解析字幕数据出错:', err);
                        return;
                    }
                    // 只保留需要的字段
                    if (subtitleData.body && Array.isArray(subtitleData.body)) {
                        subtitleData.body = subtitleData.body.map(item => ({
                            from: item.from,
                            to: item.to,
                            sid: item.sid,
                            content: item.content
                        }));
                    }
                    // 拿到字幕数据后，去请求 OpenAI
                    requestOpenAI(subtitleData);
                } else {
                    console.error('字幕请求非200状态:', response.status, response.statusText);
                }
            },
            onerror: function(e) {
                console.error('字幕请求失败', e);
            }
        });
    }

    /*---------------------------
      通过 OpenAI API 分析字幕
      得到广告区间
    ---------------------------*/
    // OpenAI 相关
    const apiKey = "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";
    const baseUrl = "https://text.pollinations.ai/openai/v1/chat/completions";

    function requestOpenAI(subtitleData) {
        if (!subtitleData || !subtitleData.body) {
            console.log("字幕数据无效，无法调用 OpenAI。");
            return;
        }

        const messages = [
            {
                role: "system",
                content: `你是一个哔哩哔哩广告识别助手。
你要通过视频的字幕识别广告的开始和结束位置。

识别的方法是：
视频的字幕中，Up主在口播广告内容和视频内容时，有很大的区别。
广告大多是卖东西的，推销产品的倾向非常重，而视频往往是有趣的内容。
不过，也有视频没有广告。

字幕会以这样的json格式发送给你：
[
    {
        "from": 0,
        "to": 1.52,
        "sid": 1,
        "content": "xxx"
    },
    {
        "from": 1.52,
        "to": 2.48,
        "sid": 2,
        "content": "xxx"
    }
]
你需要以这样的json格式回复：
{
    "start":1.1,
    "end":2.2
}

需要注意的是：
1. 你只回复json,不回复其他内容。
2. 当视频中没有广告的时候，你将start和end都设为0`
            },
            {
                role: "user",
                content: JSON.stringify(subtitleData.body)
            }
        ];

        const requestBody = {
            model: "deepseek",
            messages: messages,
            max_tokens: 8192,
            temperature: 0.7,
            top_p: 0.7,
            extra_query: { private: true }
        };

        GM_xmlhttpRequest({
            method: "POST",
            url: baseUrl,
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${apiKey}`
            },
            data: JSON.stringify(requestBody),
            onload: function(response) {
                if (response.status !== 200) {
                    console.error("请求OpenAI失败", response.status, response.statusText, response.responseText);
                    return;
                }
                let adStart = 0;
                let adEnd = 0;
                try {
                    const data = JSON.parse(response.responseText);
                    console.log("OpenAI返回数据:", data);
                    if (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) {
                        try {
                            // 去除 ```json 和 ``` 
                            const cleanedContent = data.choices[0].message.content.trim().replace(/```(json)?/g, '');
                            const parsed = JSON.parse(cleanedContent);
                            adStart = typeof parsed.start === 'number' ? parsed.start : 0;
                            adEnd = typeof parsed.end === 'number' ? parsed.end : 0;
                            console.log("识别广告起止时间:", adStart, adEnd);
                        } catch (err) {
                            console.error("解析广告时间区间出错:", err);
                        }
                    }
                } catch (err) {
                    console.error("解析OpenAI响应数据失败:", err);
                }
                // 开始根据广告时间，绑定视频事件
                bindAdSkipEvents(adStart, adEnd);
            },
            onerror: function(err) {
                console.error("OpenAI请求出错:", err);
            }
        });
    }

    /*---------------------------
      根据识别到的广告时间，
      跳过广告并在结尾播放
    ---------------------------*/
    function bindAdSkipEvents(adStart, adEnd) {
        console.log("OpenAI广告检测完成，adStart:", adStart, " adEnd:", adEnd);

        const video = document.querySelector('video');
        if (!video) {
            console.log("未能获取到 video 标签，无法进行跳转操作");
            return;
        }

        // 当播放进度到达广告开始位置时，直接跳转到广告结束
        function onTimeUpdate() {
            if (adEnd > adStart && video.currentTime >= adStart && video.currentTime < adEnd) {
                console.log('检测到广告区间，跳转到:', adEnd);
                video.currentTime = adEnd;
            }
        }

        // 当视频播放结束后，再播放广告
        function onEnded() {
            if (adEnd > adStart) {
                console.log('视频主体播放结束，开始播放广告');
                video.currentTime = adStart;
                video.play();
                // 移除监听逻辑，防止循环播放
                video.removeEventListener('ended', onEnded);
                video.removeEventListener('timeupdate', onTimeUpdate)
            }
        }

        video.addEventListener('timeupdate', onTimeUpdate);
        video.addEventListener('ended', onEnded);
    }

})();
