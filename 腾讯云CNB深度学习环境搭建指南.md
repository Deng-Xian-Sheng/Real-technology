# 这是在“腾讯云CNB”，搭建涉及深度学习的软硬件环境，的指南

## 为什么写这个指南？

因为我花了一天的时间才从各个犄角旮旯找到我需要的信息，我希望其他人可以将这个时间缩短到**1小时**！

## 什么是腾讯云CNB

类似于 Github Codespace、阿里云云效、腾讯云TAPD，但是它有云上的GPU环境支持，并且截止2025年1月份，它拥有免费额度。

一句话概况就是：

它实现了二进制产物、代码的托管，拥有支持GPU的云上开发环境，可以通过docker和CNB的配置文件快速灵活构建开发环境。

还拥有HuggingFace热门模型的内网镜像，但仍可以直连外网下载模型，只不过比内网镜像慢的多且可能会失败，但是下载镜像未收录的小模型没问题。

## 指南

### 内网模型镜像

在这个组织下：

https://cnb.cool/ai-models

该组织下仓库命名规则：https://cnb.cool/ai-models/[HuggingFace的组织/用户名]/[HuggingFace的仓库名]

搜索的时候不要直接搜索HuggingFace的仓库名，而是带上HuggingFace的组织/用户搜索仓库名。

例如：black-forest-labs/FLUX.1-dev

你可以将模型拉取到`/workspace/模型名`，记得在`.gitignore`文件添加排除，否则将模型推送到仓库会占用大量容量。

在代码中加载时，使用本地路径。因为模型镜像并不是对huggingface的完整镜像，不是镜像站，只是一个仓库，所以将模型拉取，然后使用本地路径加载。

### 注册与实名

CNB是通过微信扫码登录的，用户头像和用户昵称会继承微信的。

CNB需要通过绑定手机号的形式进行实名认证才能使用。

### CNB的仓库

CNB有三种仓库，公开、私有、密钥

其中，密钥仓库用于存储密钥，这些密钥可以在启动云开发环境时通过变量传入，这样即使你的仓库是公开的，也不会影响你的密钥安全，还能确保使用密钥，例如HF的token。详细用法：https://docs.cnb.cool/zh/repo/secret.html。关于`stages`的用法：https://docs.cnb.cool/zh/build/grammar.html#dan-ge-job

一个例子：
```
# .cnb.yml
$:
  vscode:
    - docker:
        build: .ide/Dockerfile
        imports: https://cnb.cool/CanQiJin/pandoraHFToken/-/blob/main/env.dev.yml
      runner:
        tags: cnb:arch:amd64:gpu:H20
      services:
        - vscode
        - docker
      # 开发环境启动后会执行的任务
      stages:
        - name: runAPI
          script: | 
            echo "拉取模型"
            git clone https://cnb.cool/ai-models/black-forest-labs/FLUX.1-dev /workspace/huggingface
            echo "运行API"
            HF_TOKEN=$HF_TOKEN python main.py
```

### CNB的组织

CNB可能是由于设计架构的原因，或者腾讯的产品工程师有意为之，一切都是以组织为基础的。

新用户需要新建一个组织，你可以以你的姓名的拼音创建一个组织，组织名似乎不能重复。

组织下有组织的配额，比如CPU、GPU、存储空间的用量（https://cnb.cool/YOU GROUP NAME/-/settings/charge）

仓库是建立在组织下的，不是建立在用户下的。

### 云开发环境

云开发环境通过仓库启动，你可以fork或者创建一个仓库，点击仓库中的按钮即可启动云开发环境，此时仓库里面的文件就在你的环境中。

你可以通过Dockerfile和CNB的配置文件定制你的云开发环境。

云开发环境存放在用户下，可以通过点击头像弹出的菜单访问，URL是（https://cnb.cool/u/YOU USER ID/workspaces）

这会打开一个列表，里面是你所有的云开发环境，其中有的可能处于关闭状态，而有的处于开启状态。

云开发环境的保持时间是10分钟、8小时、18小时，因情况不同而不同：https://docs.cnb.cool/zh/workspaces/workspace-recycling.html

### CNB的存储空间与Git

CNB没有服务器云盘的概念，CNB的云开发环境在关闭时会清空里面的内容，你必须将所有内容推送到代码仓库才能持久保存，不过代码仓库很大，100G的空间。

CNB的云开发环境有一套备份机制，会将未推送到代码仓库的内容备份到某个位置，我还没用过，详见https://docs.cnb.cool/zh/workspaces/file-keeper.html#man-you-nei-rong

CNB的云开发环境拥有运行、关闭、删除三种状态，尽可能的在关闭之前将内容推送到代码仓库，关闭之后内容将消失，而删除之后可能会清空CNB的备份。

### 开发环境的双容器与单容器

CNB的配置文件例子如下：

```
# .cnb.yml
$:
  vscode:
    - docker:
        # 指定开发环境镜像，可以是任意可访问的镜像。
        # 如果 image 指定的镜像中已安装 code-server 代码服务，将使用单容器模式启动开发环境
        # 如果 image 指定的镜像中未安装 code-server 代码服务，将使用双容器模式启动开发环境
        # 如下镜像为 CNB 默认开发环境镜像，已安装代码服务，将使用单容器模式启动开发环境
        # 可按需替换为其他镜像
        image: cnbcool/default-dev-env:latest
      services:
        - vscode
        - docker
      # 开发环境启动后会执行的任务
      stages:
        - name: ls
          script: ls -al
```

其中，如果你指定了一个https://hub.docker.com/的镜像，但是这个镜像中并没有 code-server 服务，那么云环境就无法启动，为此，CNB会用双容器的形式启动云环境。

一个镜像是你指定的镜像，一个是CNB提供的带有 code-server 服务的镜像。

这会造成一些问题，你从vscode的终端中可以看到两个终端，你可以打开两种不同的终端，一种对应一个容器。

如果恰巧你的镜像中没有git，但是有深度学习环境。

而CNB镜像中有git，肯定没有深度学习环境。

git是一个必须使用的命令，详见本文中“# CNB的存储空间与Git”。

但不只是git，还可能有其他的命令也这样，那么你用起来就很糟糕，你不得不在两个终端中来回切换。

我建议单容器模式，那么你就必须确保你指定的这个https://hub.docker.com/的镜像拥有 code-server 服务的同时还拥有深度学习开发环境。

这是扯淡，所以应该使用Dockerfile实现单容器模型，你可以通过Dockerfile确保镜像拥有 code-server 服务和深度学习开发环境。

### 构建环境的绝佳方法

你首先需要创建一个组织，然后才能创建一个仓库，或者fork一个。

有了仓库之后，你需要定制你的深度学习云开发环境。虽然你也可以直接点击仓库中的按钮启动云开发环境，但那是默认的环境，因此没有安装深度学习所需的依赖，也没有GPU，即使你安装了依赖，环境在关闭后会将你安装的内容清除。

所以我们需要写一个Dockerfile自定义云开发环境，当它构建成docker镜像之后就可以方便的使用。

第一次启动会比较慢，因为CNB在使用Dockerfile构建镜像，当镜像构建之后，会自动存到仓库的制品里面，叫做docker-caches，下次启动就不用重新构建了。

对于深度学习领域的环境构建，我强烈建议使用Dockerfile，因为我在尝试直接在CNB配置文件中使用https://hub.docker.com/的镜像时出现问题，然后我使用了Dockerfile解决了问题。

首先你需要搞清楚你要运行什么，你运行的这个python代码需要哪些库、哪些模型，这些库和模型支持哪些cuda软件版本。

你需要找一个英伟达的docker镜像，例如`FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04`后缀因你是否训练模型而异，如果是推理，那么只需运行时镜像。

推荐使用`devel`镜像，虽然大一点但是带有编译工具链，能防止python pip依赖包构建问题。

OK，我们Dockerfile的第一句已经有了。

然后需要添加一个变量：
```
ENV DEBIAN_FRONTEND=noninteractive
```

意思是避免软件包管理器与用户交互，而是直接使用默认值，具体：
```
ENV: 这是 Dockerfile 的一个关键字，用于设置环境变量 [1]。
DEBIAN_FRONTEND: 这是 Debian/Ubuntu Linux 发行版中用于控制软件包管理器（如 apt-get、apt、dpkg）行为的一个特殊环境变量 [1]。
noninteractive: 这个值告诉软件包管理器在执行安装、升级或其他操作时，不要尝试以交互方式提示用户输入（例如，询问用户是否接受某个许可证、选择一个时区或配置一个服务）[1]。
为什么使用这个指令？
在构建 Docker 镜像时，通常需要在无人值守的情况下自动安装软件包。如果软件包安装程序试图与用户进行交互，构建过程将会挂起并失败。设置 DEBIAN_FRONTEND=noninteractive 可以确保所有安装过程都在非交互模式下自动完成，使用默认值或预先配置的选项，从而使 Docker 镜像的构建过程能够顺利完成 [1]。
```

然后，你需要安装python，基本上是这样的：

```
# 基础环境（Python、curl 用于安装 code-server）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    curl ca-certificates build-essential python-is-python3 python3-dev cmake \
 && rm -rf /var/lib/apt/lists/*

# 创建符号链接，使 'python' 命令指向 'python3'
RUN ln -sf /usr/bin/python3 /usr/bin/python
```

然后需要一些CNB必要的依赖：

```
# 安装 code-server 和 vscode 常用插件
RUN curl -fsSL https://code-server.dev/install.sh | sh \
   && code-server --install-extension cnbcool.cnb-welcome \
   && code-server --install-extension redhat.vscode-yaml \
   && code-server --install-extension dbaeumer.vscode-eslint \
   && code-server --install-extension waderyan.gitblame \
   && code-server --install-extension mhutchie.git-graph \
   && code-server --install-extension donjayamanne.githistory \
   && code-server --install-extension tencent-cloud.coding-copilot \
   && code-server --install-extension ritwickdey.LiveServer \
   && echo done

# 安装 ssh 服务与常用工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs wget unzip openssh-server neofetch \
    rsync jq vim lsof nload htop net-tools dnsutils \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system
RUN mkdir -p /var/run/sshd

# 指定字符集支持命令行输入中文
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8
ENV LC_ALL C.UTF-8
```

还可以添加一些有用的环境变量：
```
# 一些常用环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
# /workspace 是云开发环境启动后的仓库根目录，将模型目录设置到 /workspace/huggingface 并添加git排除文件就可以在不提交模型的情况下使用模型。
# 如果要提交模型则需要在仓库下执行 git lfs install 以更新 .git/config ，然后 git lfs track "*.safetensors" 然后 git add .gitattributes 然后 git commit -m "add lfs" 然后才能添加模型这样的大文件，例如 git add .
# 至于为什么不是 /root/.cache/huggingface ，CNB文档没说工作目录与其他目录的区别，但是我认为大多数云开发环境提供工作目录之后，工作目录之外的文件夹读写速度和大小可能不够
ENV HF_HOME=/workspace/huggingface
```

它们的意思是：
```
PYTHONDONTWRITEBYTECODE=1：不写 .pyc，减少 IO
PYTHONUNBUFFERED=1：标准输出不缓冲，方便日志
PIP_NO_CACHE_DIR=1：pip 不缓存，加快镜像层清理
HF_HUB_ENABLE_HF_TRANSFER=1 开启 hf-transfer 加速下载
PYTORCH_CUDA_ALLOC_CONF 似乎能释放一些显存防止OOM
```
对于HF_HUB_ENABLE_HF_TRANSFER的补充：
```
HF_HUB_ENABLE_HF_TRANSFER 是一个环境变量，用于启用 Hugging Face Hub 的加速文件传输功能。 
具体作用和特点如下：
加速下载：当设置为 1 (即 HF_HUB_ENABLE_HF_TRANSFER=1) 时，Hugging Face 的 huggingface_hub 库将使用名为 hf_transfer 的 Rust 编写的包来处理文件下载和上传。这个包通过将大文件分割成小块并使用多线程/多进程同时传输，最大限度地利用网络带宽，从而显著提高传输速度（有时速度能翻倍或更高）。
适用场景：这种优化主要针对具有高带宽（例如，速度超过 500MB/s）的大型机器或集群。在普通或慢速网络连接上，它可能不会带来任何好处，甚至可能由于多进程开销而降低速度。
局限性：hf_transfer 是一个专为高级用户设计的工具，目前仍处于实验阶段。它缺少一些标准下载方式具备的用户友好功能，例如：
不支持代理设置。
没有断点续传机制。
错误处理不够完善。
进度条更新不及时（例如，每 50MB 更新一次）。
使用方式：要使用此功能，除了设置环境变量，还需要单独安装 hf_transfer 库（例如，使用 pip install hf_transfer 或 pip install "huggingface_hub[hf_transfer]" 命令）。 
总之，仅当你在高带宽环境下且遇到下载瓶颈时，才建议启用此环境变量。如果遇到网络问题（如代理错误），应考虑禁用它（取消设置或设置为 0），回退到默认的基于 Python requests 库的传输方式。
```

然后安装你需要的python库：

```
# Python 依赖：
# - 安装 PyTorch CUDA 12.1 + xformers（用于显存优化）
# - 安装 transformers / accelerate / safetensors
# - 如果开启HF_HUB_ENABLE_HF_TRANSFER则需要添加它：hf-transfer
RUN python3 -m pip install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir \
    torch torchvision torchaudio xformers --index-url https://download.pytorch.org/whl/cu121 \
 && pip3 install --no-cache-dir \
    "transformers>=4.45.0" \
    accelerate \
    safetensors \
    pillow \
    sentencepiece \
    huggingface-hub \
    peft \
    scipy
```
上面是比较基础的一个依赖，你的依赖可能与上述有些不同，例如你可能还需要paddleocr、ultralytics、diffusers这样的库，可以继续添加。

然后就完成了，对于工作目录、开放端口、启动命令，可以在CNB的配置文件中设置。

要把写好的Dockerfile放在仓库下的`.ide/Dockerfile`目录下。

然后需要创建CNB的配置文件：

```
# .cnb.yml
$:
  vscode:
    - docker:
        build: .ide/Dockerfile
      runner:
        tags: cnb:arch:amd64:gpu:H20
      services:
        - vscode
        - docker
      # 开发环境启动后会执行的任务
      stages:
        - name: ls
          script: ls -al
```

这个文件要放在仓库下的`.cnb.yml`中。
其中：
```
      runner:
        tags: cnb:arch:amd64:gpu:H20
```
表示我们使用英伟达的H20 GPU。我尝试发现有接近50G的显存可用。
同时，也有一部分人使用`cnb:arch:amd64:gpu`、`cnb:arch:amd64:gpu:L40`，或许有些不同。

如果你需要在云开发环境启动后做些什么，例如从CNB的内网模型镜像拉取模型，或者从huggingface下载模型，或者运行类似于无服务器API的脚本，那么你可以写到这里：
```
      # 开发环境启动后会执行的任务
      stages:
        - name: ls
          script: ls -al
```

在启动开发环境之前，记得创建`.gitignore`文件并添加`/workspace/huggingface`，这样就避免了提交占大量仓库空间的开源模型到仓库。如果你需要提交微调好的模型，记得使用lfs。

### 定价与免费额度

https://docs.cnb.cool/zh/saas/pricing.html#ji-fei-gui-ze

### 更多例子仓库

如果有什么疑问，答案可能就在这里面：

https://cnb.cool/examples/showcase

### 端口开放方式

https://docs.cnb.cool/zh/workspaces/business-preview.html

如果你有一些无服务器API的自动化需求，可以再看看开放API部分 https://docs.cnb.cool/zh/openapi.html ，里面有针对云开发环境的创建销毁操作。在文档中他们称为“云原生”。
