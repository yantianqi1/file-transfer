# 文件中转站

面向 NAS 和家用电脑的自托管上传站。管理员用 Docker Compose 部署，网页里完成初始化和业务配置；朋友打开管理员复制的免密上传链接即可上传大文件或文件夹。

## 朋友怎么用

管理员在后台创建上传入口后，会得到一个链接：

```text
https://upload.example.com/u/一长串随机token
```

朋友打开链接后直接进入上传页，不需要输入密码或上传密钥。这个链接本身就是权限凭证，管理员可以设置大小上限、目标目录、是否允许文件夹上传，并可随时禁用。

## 上传到 GitHub 后自动构建镜像

仓库包含 GitHub Actions 工作流：

```text
.github/workflows/docker-image.yml
```

你把代码推到 GitHub 的 `main` 分支后，GitHub 会自动构建镜像并推送到 GHCR：

```text
ghcr.io/你的GitHub用户名/你的仓库名:latest
```

第一次使用 GHCR 时，请在 GitHub 仓库的 Packages 页面确认镜像可见性。如果仓库是私有的，NAS 拉镜像时需要先 `docker login ghcr.io`。

## NAS Docker Compose 部署

如果你是在 NAS 上部署，推荐复制 `compose.nas.yml`。只需要把镜像名改成你自己的 GHCR 镜像：

```yaml
image: ghcr.io/你的GitHub用户名/你的仓库名:latest
```

然后运行：

```bash
docker compose -f compose.nas.yml up -d
```

打开：

```text
http://你的设备IP:8009
```

第一次访问会进入初始化向导。初始化后，上传限制、公开访问地址、上传入口都在网页里配置，不需要再改应用配置文件。

`compose.nas.yml` 会在当前目录创建：

```text
file-transfer-data/
  uploads/   # 完成上传后的文件
  config/    # SQLite 数据库和配置
  chunks/    # 临时分片
```

如果你想把上传文件放到 NAS 的某个共享文件夹，只需要改 `compose.nas.yml` 里的左侧路径，例如：

```yaml
- /volume1/uploads:/data/uploads
```

## 公开访问地址怎么填

公开访问地址就是朋友最终打开的域名地址。你有 Cloudflare 域名时，建议后续使用：

```text
https://upload.你的域名
```

在内网穿透还没配置好之前，本地测试可以先留空，或者填：

```text
http://你的局域网IP:8009
```

等 VPS、FRP、Caddy/Nginx 配好后，再到管理员后台把公开访问地址改成 Cloudflare 域名，例如：

```text
https://upload.example.com
```

后台创建的新上传链接就会自动变成：

```text
https://upload.example.com/u/一长串随机token
```

## 推荐外网访问链路

应用本身不直接修改 VPS 或 FRP 配置。推荐链路是：

```text
Friend browser
  -> Cloudflare 域名
  -> VPS 上的 Caddy 或 Nginx
  -> VPS 上的 frps
  -> NAS/电脑上的 frpc
  -> Docker 里的文件中转站
  -> 本机或 NAS 存储
```

后续你提供 VPS IP、SSH 登录方式和域名后，可以在服务器上配置：

- `frps`
- Caddy/Nginx 反向代理
- 防火墙端口
- Cloudflare DNS 记录
- NAS/电脑侧 `frpc` 配置

安全建议：不要把服务器私钥粘贴到聊天里。更好的方式是使用你本机已有 SSH key，或创建临时低权限账号，配置完成后删除。

## 本地开发

```bash
UPLOADS_DIR=./data/uploads CONFIG_DIR=./data/config CHUNKS_DIR=./data/chunks python3 -m app.server
```

## 验证

```bash
python3 -m unittest discover -s tests -v
```
