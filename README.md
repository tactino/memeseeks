# 迷因捕手 · memeseeks

[English](README.en.md)

说出你记得的那句话，从自己的收藏里把那张梗图找回来。中英文都能搜，程序跑在你自己的电脑上；同时搜网上是可选的，默认关闭。

它也是一个个人梗图收藏夹，有点像网易云音乐之于歌：**图集**（像歌单）、**我喜欢**、全屏一张接一张地**刷梗**，还能在逛贴吧、小红书、豆瓣时一键**采集**。

**状态：** v0.3。本地网页应用、命令行、一键安装和 Docker 镜像都已可用。跨语言的「梗图关系图」和梗图译制在规划中。

## 安装

**Windows**：打开 PowerShell，运行：

```powershell
irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1 | iex
```

**macOS / Linux：**

```bash
curl -LsSf https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.sh | sh
```

安装脚本会把程序和它自带的 Python 放进一个文件夹（Windows 是 `%LOCALAPPDATA%\memeseeks`，macOS 是 `~/Library/Application Support/memeseeks`，Linux 是 `~/.local/share/memeseeks`），建好「迷因捕手」快捷方式，然后启动。

- 第一次启动会下载约 3.9 GB 的模型，网页上能看到进度；下完就能搜索，其他功能马上就能用。
- 在国内会自动换用镜像（PyPI、Python 和模型都走国内镜像）。
- 不改系统 PATH。想卸载，删掉那个文件夹和快捷方式即可；你的图库默认在 `~/.memeseeks`，不会被删。
- 想更新，再运行一次同一行命令。

**不想装在 C 盘**（或者想装到别处）时，在 Windows 上这样运行：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1))) -Dir D:\memeseeks -Library D:\memeseeks-library
```

- `-Dir`：程序、它的 Python 和模型放在哪。
- `-Library`：你的图库（索引、图集、采集来的图）放在哪。
- `-Models D:\某处\hf-cache`：复用你已经下载过的 Hugging Face 模型缓存，不再重新下载。

macOS / Linux 上对应的是在 `sh` 前面加 `MEMESEEKS_DIR=…`、`MEMESEEKS_LIBRARY=…`、`MEMESEEKS_MODELS=…`。

## 怎么用

打开后先把梗图放进来。可以在任意图集页点「上传」，也可以直接把图片拖进页面；还可以在「设置 → 来源文件夹」里添加电脑上已有的梗图文件夹。放进来的新图会在后台建立索引，页头会显示进度。在笔记本 CPU 上每张大约 3.5 秒，1000 张大约一小时，以后只处理新增的图。

- **搜索**：输入你记得的话，比如「上班的时候想下班」。把握大的结果排在前面，其余的折叠在「可能相关」里。
- **图集**：有「全部」「我喜欢」和你自己建的图集。在梗图页点「加入图集」；在任意图集页点「上传」，或者把图片拖进页面。
- **刷梗**：全屏一张接一张地看。可以按图集的顺序看，或者随机；在某张梗图上点大图，会接着刷和它相似的梗；从页头进入时，先刷最久没看过的。手机上划动，电脑上用滚轮或方向键。
- **首页**有今日一梗、你的图集和旧梗重温。点开一张梗图可以复制、保存、分享，也能看它的出处。
- **设置**：纸色 / 夜间主题、蒙德里安边框、开场动画、减少动效、网上搜索、来源文件夹、连接浏览器。设置存在图库里，用手机打开也一样。想改得更深，可以在图库文件夹里放一个 `custom.css`。

在运行它的电脑上，还可以从浏览器菜单把它装成一个应用。

### 在手机上用

目前需要手动开启。在电脑上运行下面这行（安装版的话就用它的启动文件，比如 `D:\memeseeks\memeseeks.cmd`，后面跟同样的参数）：

```bash
memeseeks serve --host 0.0.0.0 --token <一串足够长的口令>
```

然后在手机浏览器打开它打印出来的链接，把 `127.0.0.1` 换成电脑的局域网地址。

用普通 http 打开时，手机能搜索和「保存」；「复制」「分享」和装成应用需要 localhost 或 HTTPS，这是浏览器的规定。

### 从社区采集梗图

浏览器脚本会在你看的网页上放一只猫。点它，它会列出这一页的图；你勾选的图会连同网站名、帖子链接和标题一起进你的图库，大约一分钟后就能搜到。

脚本对三个站点做了专门适配：百度贴吧（每层楼的原图）、小红书（一篇笔记的全部图片）、豆瓣小组（帖子和回复里的大图）。其他网站用通用模式。

1. 给浏览器装扩展 [Violentmonkey](https://violentmonkey.github.io/)（Firefox 或 Chrome 都行）。
2. 在迷因捕手运行时打开网页，进入「设置 → 连接浏览器 → 安装采集 meme 脚本」。脚本是为你的服务器生成的，带着只有你的图库知道的密钥；没有这把密钥，收件箱不收图。
3. 在任意网页上点那只猫（可以把它拖到你喜欢的位置），勾选图片，在「放进」里选图集，然后点「采集」。
4. 只要一张的时候更快：直接把网页上的图片拖到猫头上，它就吞下去了，放进你上次在「放进」里选的图集。有的网站禁止拖动图片，那就用第 3 步。

字很少（少于 15 个字）的采集图多半是表情包，会先放进页头的「待确认」。点「要」就放进图库；点「不要」会移到 `<图库>/rejected`，不删除，也能一键撤销。你的选择只存在你自己的电脑上，以后用来训练一个只属于你的判别器。你自己文件夹里的图不受这条规则影响。

脚本只在你点它时动作，只采你正在看的这一页，每秒最多下载两张图。它不自动翻页，不在后台抓取，除了图片、网站名、帖子链接、帖子标题和你选的图集，什么也不发送。你可以在 Violentmonkey 的菜单里让它在某个网站上隐藏，或者把猫放回右下角。

### 网上搜索（可选）

你自己的图和网上的图分开显示。网上搜索默认关闭。要打开，先去申请一个免费的 [KLIPY](https://partner.klipy.com) API key，然后运行：

```bash
MEMESEEKS_KLIPY_KEY=<你的 key> memeseeks serve --online klipy     # 或者设置环境变量 MEMESEEKS_ONLINE=klipy
```

打开之后：

- 是**浏览器**把你的搜索词发给 KLIPY，同时发送一个每个图库随机生成的 id 和你的 IP 地址；图片也直接从 KLIPY 加载。迷因捕手的服务器不转发、也不保存这些内容。
- KLIPY 的结果按原样显示，可能包含广告。它的条款不允许过滤或重排结果，内容偏好请在 KLIPY 的合作方后台里调整。
- 能打开你网页的人都能看到这个 key。
- KLIPY 的英文和日文内容很多，中文很少。

## 你的数据在哪、怎么备份

图库文件夹（默认 `~/.memeseeks`，可以用 `-Library`、`--lib` 或 `MEMESEEKS_HOME` 指定）里全是普通文件：

| 内容 | 位置 |
|---|---|
| 图集、我喜欢 | `collections.json` |
| 设置、编号、看过的记录 | `settings.json`、`numbers.json`、`seen.json` |
| 采集和上传的图，以及它们的出处 | `inbox/`、`provenance.jsonl` |
| 待确认的选择；「不要」的图 | `review.jsonl`、`rejected/` |
| 索引（可以重建） | `index/` |

- **你自己文件夹里的图，迷因捕手只读不改。** 「移出图库」对它们也只是隐藏，原图不会动。
- **备份就是复制整个图库文件夹。** 索引丢了能重建，图集和我喜欢丢了就没了，所以这才是需要备份的东西。
- **换电脑**：把图库文件夹复制过去，安装时用 `-Library` 指向它。如果你自己的梗图文件夹换了位置，在「设置 → 来源文件夹」里重新添加一次；图集是按图片内容认图的，不会丢。

## 它是怎么找到梗图的

每张图最多从三个方面读，结果再合并排序（倒数排名融合）：

| 途径 | 用什么 | 要显卡吗 |
|---|---|---|
| 图里的字 | 先识别图中文字（[RapidOCR](https://github.com/RapidAI/RapidOCR)），再用 [BGE-M3](https://huggingface.co/BAAI/bge-m3) 按意思匹配 | 不用 |
| 画面 | [Chinese-CLIP](https://github.com/OFA-Sys/Chinese-CLIP) 图文相似度 | 不用 |
| 描述（可选） | 本地视觉语言模型（[Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)）写出主题和笑点 | 要，约 16 GB 显存 |

在维护者那批字很多的梗图上，前两个途径已经能把每条查询要找的图排进前五，所以「描述」默认关闭。数字见 `experiments/results/`。

## 命令行

```bash
memeseeks add ~/Pictures/memes            # 为一个文件夹建立索引；随时可以重跑，只处理新图
memeseeks serve                           # 网页在 http://127.0.0.1:8765/
memeseeks serve --open                    # 同上，并打开浏览器（已经在运行的话就直接打开）
memeseeks search "关于熬夜的"              # 在终端里搜
memeseeks status                          # 图库里有什么，以及哪些图某一步失败了
memeseeks eval queries.csv                # 给你自己的查询打分（见下）
memeseeks --lib D:\memes-lib status       # --lib 这类全局选项写在子命令前面
```

`add --vlm` 会另外用本地视觉语言模型给图写描述（需要显卡），`--retry-failed` 会重做上次失败的图。

**评测你自己的查询**：`queries.csv` 第一行是表头，之后每行一条查询和它应该找到的文件名，多个文件名用 `;` 分隔。文件名可以是相对于添加的文件夹的路径，也可以是不重名的文件名。

```csv
query,expected
关于熬夜的,night_owl.jpg
猫在评判你,cat_judge.png;cat_judge_2.png
```

## 手动安装（开发用）

需要 Python 3.10 或更新版本。

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
python -m venv .venv && source .venv/bin/activate        # Windows：.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # 有显卡就装对应的 CUDA 版
pip install -e ".[ml,serve]"
```

- 第一次运行会把约 3.9 GB 的模型下载到 Hugging Face 缓存（`HF_HOME`）。**在国内**请先设置 `HF_ENDPOINT=https://hf-mirror.com`。
- **Windows + Anaconda**：如果用 torch 2.9 或更新版本，不要用 Anaconda 的 Python 建虚拟环境，否则 torch 会报 `WinError 1114 … c10.dll`。原因是 Anaconda 在 `python.exe` 旁边放了一份旧的 MSVC 运行库。改用 python.org 的 Python，或者 uv 管理的 Python（`uv venv --managed-python --python 3.12`）。

## 用 Docker 运行

不用装 Python，只用 CPU。

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
cp .env.example .env        # 然后填好 MEMES_DIR 和口令（文件里写了怎么生成）
docker compose up -d
docker compose logs -f      # 等到出现 "memeseeks is at http://…"
```

- 第一次启动会把约 3.9 GB 的模型下载到 `models` 卷，并为你的文件夹建立索引。**建完索引之前 8765 端口不会响应**，请看日志。
- 之后在每台设备上打开一次 `http://<这台电脑的局域网地址>:8765/?token=<你的口令>`，浏览器会记住它。
- 以后启动只处理新图。更新代码后运行 `docker compose up -d --build`；`docker compose down -v` 会删掉图库和下载的模型。
- 梗图文件夹以只读方式挂载。容器以 uid 1000 运行；如果你把 `library` 卷换成绑定挂载，要让 uid 1000 能写那个文件夹。

## 许可证

代码：MIT。梗图知识库（将来有了之后）：CC BY-SA 4.0。字体 Noto Serif SC 与 JetBrains Mono 的子集按 SIL OFL 1.1 随附。
