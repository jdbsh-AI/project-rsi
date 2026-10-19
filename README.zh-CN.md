# Project RSI

[English](README.md) · [简体中文](README.zh-CN.md)

**让 Agent 从项目里真实犯过的错误中改进，但每次采纳都先由你确认。**

Project RSI 是一份可以跨工具使用的 [Agent Skill](SKILL.md)，加上一套小型 Python 工具。它让编程助手复盘执行过程、提出具体改法、用例子检查，再通过可交互 HTML 请你决定是否采用。处理完成后，必须告诉你改了哪个规则文件或 skill、改了什么、检查结果怎样。

**本地运行，无内置数据收集。** 随附脚本和 `local` 审批服务均在本机运行；Project RSI 不内置遥测、项目资料上传或开发者收集服务。模型请求与可选的原生对话回传，遵循你选择的 harness 及服务商的数据处理方式。请阅读[信息披露边界](#本地运行与信息披露边界)和[免责声明](#免责声明)。

项目规则可以叫 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`，也可以是 Cursor 的 `.mdc`、Copilot 指令或你自己的文件名。RSI 改进的是项目的做事方法，不训练模型权重，也不扩大 Agent 的权限。

方法受到 Google Research [Harness²](https://github.com/google-research/harness2) 的 propose–probe–compose 思路启发。本项目是独立实现，不包含 Google 源码。

## 你如何决定改不改

每条建议先用大白话说明：哪里出了问题、准备怎样改、为什么有用，以及证据在哪里。修改前后对照、完整候选内容、检查和适用范围可以展开查看。

- **同意：** 校验通过后，应用你看到的这版方案。
- **不同意：** 不应用这一项修改。
- **要求调整：** 写下备注，助手重新整理方案，再请你确认。
- **先解释：** 助手先回答疑问，暂不应用。

备注是长条、可多行输入的文本框，支持较长的中文内容。页面不会预先替你选择同意。“同意”同时附带备注时，会先留待解读，防止只执行勾选却忽略你的要求。最终回执需要在人能读懂的说明里列出修改位置，不能只丢一个 `receipt.json`。

## 需要准备什么

- Python **3.9 或更新版本**，不需要安装第三方 Python 包。
- 能读取 skill、查看项目证据、运行本地命令的编程助手。
- 用于打开本地 HTML 的浏览器，或者支持原生交互卡的对话宿主。

这套工具本身不需要 API key；具体 harness 的账号和模型要求由对应工具决定。安装不会自动创建定时任务，也不会启动后台常驻服务。

下面的示例使用 macOS/Linux 常见的 shell 写法。Windows 没有 `python3` 命令时，可换成 `python` 或 `py -3`；绝对路径换成你的实际路径，PowerShell 或命令提示符中的长命令请合并成一行，不要直接复制行尾的 `\`。例如，在下载的仓库目录内运行：

```powershell
py -3 scripts/project_rsi.py init --project "C:/work/my-project" --harness workbuddy --transport local --install-skill
```

配置和计划里的项目相对路径统一用 `/`。不使用 Git 也可以在 GitHub 下载仓库 ZIP 后解压。

## 安装到你的项目

先下载仓库，在仓库目录内运行初始化命令：

```sh
git clone https://github.com/jdbsh-AI/project-rsi.git
cd project-rsi
python3 scripts/project_rsi.py profiles
python3 scripts/project_rsi.py init \
  --project /absolute/path/to/your-project \
  --harness claude \
  --transport local \
  --install-skill
```

把绝对路径换成你的项目路径，把 `claude` 换成你使用的工具。提供 `codex`、`claude`、`gemini`、`cursor`、`copilot`、`opencode`、`dsh`、`workbuddy` 八种 harness 配置，另有适合自定义目录的 `generic`。`auto` 可以识别特征明确的项目；一个项目同时有多个工具的配置时，建议明确指定。

`init` 创建 `.project-rsi/config.json`。加上 `--install-skill`，还会把 skill 安装到所选配置的第一个技能目录，例如 `.claude/skills/project-rsi/`。**初始化不会修改项目规则文件。** 按所用工具的要求刷新或重启会话后，让助手使用 Project RSI 即可。支持斜杠命令的客户端通常可以输入 `/project-rsi`；Codex 也可使用 `$project-rsi`。

项目规则不叫默认名字时，可以显式设置。下面的规则和技能目录路径都相对于目标项目：

```sh
python3 scripts/project_rsi.py init \
  --project /absolute/path/to/your-project \
  --harness generic \
  --instructions TEAM_GUIDE.md \
  --instructions docs/agent-policy.md \
  --skill-root .agents/skills \
  --transport local \
  --install-skill
```

`--instructions` 和 `--skill-root` 可以重复，分别替换对应的默认列表。规则文件支持项目内的 `.md` 和 `.mdc`。这里声明的是“允许把哪些文件作为待审修改目标”，**不会替 harness 配置文件加载规则**。你的工具需要自定义发现或导入设置时，应另外完成设置，详见[兼容说明](references/harnesses.md)。

## 先跑一次完整的隔离演示

在下载的仓库目录内运行，演示目录必须选择一个**尚不存在**的路径：

```sh
python3 scripts/project_rsi.py demo \
  --directory /absolute/path/to/new-rsi-demo \
  --harness cursor
python3 scripts/review_server.py \
  --run /absolute/path/to/new-rsi-demo/run \
  --once
```

这会创建独立的样例项目和三条提案，并在 `demo.json` 记录本地复盘 session ID。服务启动后输出 `review_url`，用浏览器打开该地址：

1. 同意一项。
2. 不同意另一项。
3. 对第三项选择要求调整，并输入多行备注。
4. 点击提交，查看页面回执和终端输出。

本地服务会校验提交、应用已同意的样例修改，并显示处理结果。使用 `--once` 时，收到一次有效提交并处理后就退出。拒绝和待调整项会记入回执，不会应用它们的候选内容。这里的所有修改都只发生在演示目录里的样例项目，不会修改你前面初始化的真实项目。

如果希望助手提交后立即继续，让助手运行这条服务命令并等待返回。你点击提交后，命令结束并返回回执，等待中的助手就能读取结果并说明。若你自行在另一个终端启动，服务仍能处理表单，但不会因此自动唤醒任意一个已经打开的 IDE 聊天。

## 正式使用

可以直接对助手说：

> 使用 Project RSI 复盘昨天本项目的工作，检查有真实执行证据的错误，包括工具或 skill 调用不合理的情况。提出小而具体的规则或技能改进，用获准的例子检查候选，再给我 HTML 审阅。未经我确认具体方案，不要修改生效的规则和技能。处理完我的选择后，明确告诉我改了哪些文件、改了什么、为什么改。

助手会读取 [SKILL.md](SKILL.md)，收集必要证据，在私有目录准备复盘产物并生成审阅页。新增规则前，应该先检查原规则是否已经覆盖这个问题。合成检查需要明确标注，不能据此宣称未来的行为效果已经得到验证。

使用本地 HTML 提交流程时，基本命令是：

```sh
python3 scripts/project_rsi.py build \
  --plan /absolute/path/to/private-run/plan.json \
  --output /absolute/path/to/private-run/form.html \
  --session-id review-session-01
python3 scripts/review_server.py \
  --run /absolute/path/to/private-run \
  --once
```

计划与命令使用相同的复盘 session ID。本地 ID 用来关联这次审阅、提交和回执，不代表工具已经验证某个 IDE 对话身份。服务会直接消费提交；如果你另行集成了获得授权的接收端，可以使用底层命令：

```sh
python3 scripts/project_rsi.py consume \
  --run /absolute/path/to/private-run \
  --submission /absolute/path/to/private-run/submission.json \
  --confirmation-reference '实际用户提交的来源引用' \
  --session-id review-session-01
```

确认前，工具会绑定计划、候选、检查结果、允许修改的目标和基线哈希。采纳前再次核对，保留经验区以外的并发修改，先记录写入计划和备份，再读回核验；同一提交重复处理不会反复写入。项目已有专门的审批或应用守卫时，仍必须通过原守卫，通用命令不能绕过。

计划字段与边界见[运行协议](references/protocol.md)，回传与验收见[提交和回执说明](references/callback.md)。复盘日志、真实证据、提交和回执应留在私有目录，不要混进公开 skill 仓库。

## 支持哪些 harness

下表是发布版内置配置的默认目标，不代表每个客户端版本都经过现场实测：

| 配置 | 默认项目规则目标 | 首个 skill 安装目录 | 默认审阅回传 |
|---|---|---|---|
| `codex` | `AGENTS.md` | `.agents/skills/project-rsi` | 原生对话交互卡 |
| `claude` | `CLAUDE.md` | `.claude/skills/project-rsi` | 本地 HTML 服务 |
| `gemini` | `GEMINI.md` | `.gemini/skills/project-rsi` | 本地 HTML 服务 |
| `cursor` | `.cursor/rules/project-rsi.mdc` | `.cursor/skills/project-rsi` | 本地 HTML 服务 |
| `copilot` | `.github/copilot-instructions.md` | `.github/skills/project-rsi` | 本地 HTML 服务 |
| `opencode` | `AGENTS.md` | `.opencode/skills/project-rsi` | 本地 HTML 服务 |
| `dsh` | `AGENTS.md` | `.dsh/skills/project-rsi` | 本地 HTML 服务 |
| `workbuddy` | `CODEBUDDY.md` | `.codebuddy/skills/project-rsi` | 本地 HTML 服务 |
| `generic` | `AGENTS.md` | `.agents/skills/project-rsi` | 本地 HTML 服务 |

有 override 或自定义入口时，用 `--instructions` 指定真正生效的文件。Codex 客户端没有原生交互卡 API 时，可以用 `--transport local`。Cursor 既有 `.mdc` 的 frontmatter 会保留，新建文件采用对应规则格式。官方来源、加载优先级和自定义文件名示例见 [references/harnesses.md](references/harnesses.md)。

初始化 DSH 时，如果没有 `AGENTS.md`，会复用已存在的 `CLAUDE.md`。初始化 WorkBuddy 时，如果没有根目录的 `CODEBUDDY.md`，会依次查找已有的 `.codebuddy/CODEBUDDY.md` 和 `AGENTS.md`。WorkBuddy 代码项目使用的 skill 目录是 **`.codebuddy/skills`**，不要自行写成 `.workbuddy/skills`。这两项适配针对本地代码项目，不会同步云端项目资产或个人 skill 库。

**“兼容”需要分开看。** 配置和离线测试能检查路径、文件生成和受控采纳，不能证明某个客户端已经加载 skill 或遵循了新经验。原生回传的真实端到端，还需要实际点击 HTML、目标对话收到消息、处理、读回，以及向用户返回结果。

原生模式依赖对话宿主提供 `window.openai.sendFollowUpMessage`，页面会检查是否存在。普通浏览器没有这个 API。本地模式通过明确运行的服务命令完成提交，并把结果返回给等待中的进程，不会向任意已有聊天注入消息。Claude Channels、OpenCode session API、Cursor SDK 可以作为专用集成入口，但本版本没有实现这些桥接。缺少回传能力时必须说明，不用未公开 socket 或第二个 CLI writer 冒充接通。

## 每晚 22:00 自动复盘

定时由你所用 harness 或另行授权的调度器负责，安装 skill 不会自动开启。可以向支持定时的宿主提出：

> 每天按我指定的时区在 22:00 使用 Project RSI，复盘本项目自上次复盘以来的工作。证据、待改内容、diff 和获准检查放在私有运行目录。用 HTML 展示建议和大白话说明，等我确认本次具体方案后才采纳。收到支持的提交回传后立即处理，不等下一次晚上复盘；处理后明确反馈修改位置和结果。没有新的可执行发现时保持安静。

创建时明确时区和项目。定时只触发分析与提案，不构成批准。表单提交的处理时间与每晚复盘时间相互独立。

## 本地运行与信息披露边界

**Project RSI 的 Python 工具和通用本地审批服务均在本机运行。** 本工具不内置统计、遥测、崩溃上报、托管后端，也不会自动把项目内容上传给开发者或其他第三方收集服务。工具本身不调用模型 API，也不要求你提供模型方的 API Key。

- **本地审批模式：** 浏览器只向带随机令牌的 `127.0.0.1` 服务提交决定。证据、候选内容、计划、diff、备份、提交和回执保存在你指定的本地目录中。随附页面不加载第三方脚本、字体或追踪资源。
- **模型处理：** 你选择的 harness 可能把它选中的项目上下文发送给你配置的模型服务商；处理方式、留存期限和使用范围由相应配置及服务条款决定。Project RSI 不为这些信息增加额外的外发目的地。
- **原生对话模式：** 表单通过所选对话宿主的 API 提交消息及可选草稿状态，审阅内容、选择、备注和本地运行目录引用可能因此交给宿主及其配置的服务处理。该模式受宿主隐私政策约束，不能视为纯本地传输。如果审批提交和存储也必须留在本机，请使用 `--transport local`。
- **其他软件与主动发布：** harness 自带遥测、插件、连接器、浏览器扩展、云同步文件夹、远程工作区，以及你另行授权的发布行为，不在本工具控制范围内。从 GitHub 安装或更新是下载公开源码；本仓库 CI 在 GitHub 运行公开源码和合成样例，不会因此自动上传你本机的私有复盘目录。

上述承诺限定于 **Project RSI 随附工具本身的行为**，不能无条件扩展成“任何 harness、模型、插件组合都只向模型方披露信息”。使用前核对所选环境的数据配置，只向模型提供必要且适当脱敏的上下文，并把私有运行目录放在公开仓库、共享目录和云同步目录之外。

## 免责声明

本项目按 [MIT 许可证](LICENSE) **“按现状”提供**，不对准确性、特定用途适用性、避免错误、安全性、保密性或 Agent 后续改进效果作保证。本项目为独立实现，不代表 Google Research 或所适配工具厂商的认可。

Agent 和模型可能出错，已批准的修改也可能影响后续项目行为。请审阅方案与 diff、保留适当备份，并在依赖结果前自行验证。使用者应确认自己有权处理有关项目资料，并选择适当的 harness、模型服务、插件和存储配置；维护者不能控制这些服务及其数据处理方式。免责与责任限制以 MIT 许可证为准，并在适用法律允许的范围内生效。

## 检查与贡献

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```

修改表单或本地回传时，还应运行上面的隔离浏览器演示。单元测试通过不代替真实宿主回传验证。欢迎提交有针对性的回归检查，并说明测试覆盖到哪一层。贡献时只使用合成样例，不提交私人项目日志、凭据、客户资料或真实会话 ID。

## 开源许可

[MIT](LICENSE)。完整方法见 [SKILL.md](SKILL.md)，受控采纳见[运行协议](references/protocol.md)，回传保证与限制见[回调说明](references/callback.md)。
