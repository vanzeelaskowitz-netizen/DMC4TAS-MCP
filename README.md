# DMC4 TAS MCP

Windows / Python 3.13，本地 stdio。需要包含 TASK 11 的特别版 TAS 服务。播放器与服务启动方式见 TAS 项目。列工具和读 tas://combo-rules 可以离线进行。

在本目录创建环境，安装官方 PyPI 的 MCP Python SDK 1.30.0（含 FastMCP）及其依赖。录像复用 PATH 中的 FFmpeg，需 subtitles、h264_nvenc 和可见的游戏窗口。

~~~powershell
py -3.13 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --index-url https://pypi.org/simple -r requirements.txt
~~~

在打算使用的项目目录打开 PowerShell，按所用客户端选择一条注册命令。仅给出命令，由操作者执行。

~~~powershell
$tas = 'D:\Work\Claude 專案資料夾\DMC4TAS'
$mcpProject = 'D:\Work\Claude 專案資料夾\DMC4TAS-MCP'
$exe = "$mcpProject\.venv\Scripts\python.exe"
$server = "$mcpProject\server.py"
claude mcp add dmc4tas --transport stdio --scope user -e "DMC4TAS_ROOT=$tas" -- "$exe" "$server"
codex mcp add dmc4tas --env "DMC4TAS_ROOT=$tas" -- "$exe" "$server"
~~~

[Claude Code 注册文档](https://code.claude.com/docs/en/mcp) · [OpenAI Docs](https://developers.openai.com/codex/mcp)

脚本工具读写 TAS 的 runs/*.tas，录像写本项目 outputs/*.mp4。probe 在已暂停的时间线上工作，first/last 均含端点，各候选从 first 帧开始，未给出的尾部帧松开全部键。例如 first=8、last=9、candidates=[["K",""],["","K"]]、fields=["frame","hits","camera.angle"]。

`jc_points` 列出一段帧里每帧能否 JC：`can` 是游戏自己的判定，`steps` 是在那一帧真的按跳后是否踩敌（一次 probe 逐帧试），`afterHit` 表示范围内更早的帧已有敌人掉血。要保住伤害，选 `steps` 和 `afterHit` 都为真的帧。一次最多 60 帧。

生成演示时需接管特别版、载入血宫准备脚本。搜索会跳回起点并载入输出草稿，每次确认踩敌后保存进度。命令在本项目目录运行。

~~~powershell
$env:DMC4TAS_ROOT = 'D:\Work\Claude 專案資料夾\DMC4TAS'
& '.\.venv\Scripts\python.exe' combo_split_calibur.py demo.tas 30
& '.\.venv\Scripts\python.exe' record_video.py demo.tas demo.mp4 --keys
& '.\.venv\Scripts\python.exe' selftest.py
~~~
