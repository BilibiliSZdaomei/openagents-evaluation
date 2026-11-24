# OpenAgents 本地评测部署

这是 [OpenAgents Workspace](https://github.com/openagents-org/openagents/tree/2500fccb0c5623a82cf9f4155212002e4386bd68/workspace) 的固定版本部署。首次启动会在新数据库创建工作区、名为 `本地对话测评` 的线程和 `review-assistant` 智能体。浏览器用 `admin` 和你自己设的密码进入，日常网址不带工作区令牌。

## 安装和启动

1. 准备 x86_64 电脑、Python 3.10 或更新版本，以及带 Compose v2 的 Docker。Windows 使用 Docker Desktop 的 Linux 容器模式，或直接在配置好 Docker 的 WSL2 发行版内运行。Linux 使用 Docker Engine 与 Compose 插件。所有命令在本仓库根目录执行。Windows 可用 `py -3` 代替 `python`，Linux 一般用 `python3`。
2. 按 [离线依赖](OFFLINE.md) 下载并校验该 Release 的镜像，导入 Docker。应用、PostgreSQL、Nginx 共四个镜像。离线部署仍需要容器能访问 DeepSeek API 才能获得真实回复。
3. Windows 可以双击 `Start.cmd`；使用终端时运行下面的命令。首次运行按提示输入自己的 DeepSeek Key 和新设的评测密码（至少 12 个字符）。脚本生成独立数据库密码。之后使用同一命令可恢复服务。

```sh
python manage.py up
```

在部署电脑打开 [OpenAgents 评测工作区](http://openagents.localhost:18811/start/workspace)，用户名 `admin`。Chrome 首次会弹出用户名和密码框。该网址直接进入测试线程，输入 `@review-assistant 6 个货架，每个 17 箱，共有几箱？` 即可测试。模型 API 地址为 `https://api.deepseek.com/v1`，模型 ID 为 `deepseek-flash`（DeepSeek V4.1 Flash）。工作区创建时也会按上游设置初始化 Yumi。

## 使用与保存

```sh
python manage.py status
python manage.py stop
python manage.py up
```

首次安装、停服务、换端口和重启应使用同一个 `--project` 和 `--config-dir`。默认 Docker 项目名为 `openagents-evaluation`。如默认端口已占用，可用 `python manage.py up --port 19811`，浏览器访问 `http://openagents.localhost:19811/start/workspace`。普通本机评测保持默认的 `127.0.0.1` 绑定。内网团队共用时可保留此绑定，由管理员在同机配置 HTTPS 反代和内网访问控制，转发到前端，使用该 HTTPS 站点的 `/start/workspace`；如确需改监听，可传 `--bind 内网接口IP`。HTTP Basic 的用户名和密码只应在回环地址或 HTTPS 上传输。

凭据首次在部署机新建。Windows 默认位于当前用户的 `%LOCALAPPDATA%\OpenAgentsEvaluation\config`；Linux/WSL 默认位于 `~/.config/openagents-evaluation`。可用 `--config-dir` 指定仓库以外的独立私有目录。无人值守安装可在调用进程的环境里提供 `OPENAGENTS_DEEPSEEK_KEY` 和 `OPENAGENTS_LOGIN_PASSWORD`，已有配置文件优先。禁止将这些文件、容器日志、浏览器数据或运行卷放入 Git 或 Release。

数据库、上传文件、配置初始化标记、受保护的入口页面分别保存于 Compose 的 `postgres-data`、`files`、`provision`、`entry` 命名卷。普通停止/启动保留历史。迁移数据应一起备份四个卷和私有配置目录。要更换 DeepSeek Key 或登录密码，先停止本套部署，更新私有目录里对应的 `deepseek-key` 或 `login-password`，再运行 `up`。首次安装后保留生成的 `postgres-password`，修改它不会同步修改现有 PostgreSQL 用户口令。

## 部署组成

| 服务 | 用途 |
| --- | --- |
| `front` | Nginx 单一浏览器入口、统一密码验证、同源 API 代理 |
| `web` | 官方固定版本的 Next.js 前端，构建时使用同源 `/wsapi` |
| `backend` | 官方 FastAPI 后端、数据库迁移和 Cloud Agent 运行时 |
| `db` | PostgreSQL 16，保存工作区、Agent、消息与历史 |
| `bootstrap` | 首次通过上游 API 创建工作区、助手和线程，生成用于本机登录的受限页面；启动结束后显示退出码 0 属正常 |

平台原生将工作区令牌作为共享机器身份。评测入口代为向原版页面传递令牌；获得此入口权限的人共用同一工作区权限，不能用它证明个人账号权限隔离或以个人身份跨用户派活。数据库与后端没有直接发布宿主端口。本配置的基础聊天由应用与 PostgreSQL 完成，没有另设 Redis。

## 已验证

在独立 Linux x86_64 容器项目中从空 PostgreSQL 库启动并创建工作区，验证了匿名请求返回 401、使用新密码打开普通网址，以及 Windows 上全新的 Chrome 会话直接进入新线程。网页向 `review-assistant` 提问「8 个货架，每个 13 箱」，使用 DeepSeek 后收到了 `104`。该次运行使用 Release 对应的预构建应用镜像。Windows Docker Desktop 和公司服务器的安装需要在目标机器分别验证。

## 从官方源码重新构建

预构建镜像带正式上游应用和 Linux 依赖。自行构建需要 Git、Docker/BuildKit 和外网连接（GitHub、Docker Hub、PyPI、npm、Debian 软件源，以及上游构建所需的字体下载）。运行：

```sh
python manage.py build
python manage.py up --source
```

脚本取 [固定提交](https://github.com/openagents-org/openagents/tree/2500fccb0c5623a82cf9f4155212002e4386bd68)，仅将 Git 提交中的 `workspace/backend` 和 `workspace/frontend` 传入 Docker 构建，使用上游 `production.Dockerfile`、`requirements.production.lock` 和前端 `package-lock.json`。基础镜像摘要与离线镜像 ID 见 [images.lock.json](images.lock.json)。源码构建另用 `*-src` 本地镜像标签；基础系统包及构建时间戳可能令结果与 Release 文件摘要不同。源代码及构建 tar 临时放在系统临时目录，可用 `OPENAGENTS_BUILD_TEMP` 指定已有的外部临时目录。

上游代码采用 Apache License 2.0。见 [原版许可证](UPSTREAM-LICENSE) 和 [固定版本源码](https://github.com/openagents-org/openagents/tree/2500fccb0c5623a82cf9f4155212002e4386bd68)。镜像还包含各发行方组件和各自的版权声明。
