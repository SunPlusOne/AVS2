# AutoDL 全栈部署指南 (彻底摆脱本地环境)

本指南教你如何将 **前端 + 后端 + 模型** 全部部署在 AutoDL 上。
这样你就不需要本地电脑开着，也不需要搞 SSH 隧道，直接访问 AutoDL 提供的链接即可使用。

---

## 第一步：本地准备 (构建前端)

在你的本地电脑 (Windows) 上执行：

1. **构建前端**：
   打开终端进入项目根目录：
   ```powershell
   npm.cmd run build
   ```
   *成功后，你会看到一个 `dist` 文件夹生成。*

2. **准备上传**：
   确认你的本地项目包含：
   - `dist/` (刚才生成的)
   - `api/` (后端代码)
   - `deploy_full_stack.sh` (部署脚本)

---

## 第二步：上传到 AutoDL

1. 使用 VS Code Remote 或 FileZilla 连接 AutoDL。
2. 建议创建一个干净的目录，例如 `/root/AVS2_Full/`。
3. 将本地的所有文件（包括 `dist` 和 `api`）上传到该目录。

**最终 AutoDL 目录结构应如下：**
```
/root/AVS2_Full/
  ├── dist/          <-- 前端静态文件
  ├── api/           <-- 后端代码
  ├── deploy_full_stack.sh
  └── ...
```

---

## 第三步：一键启动

在 AutoDL 终端执行：

```bash
cd /root/AVS2_Full
bash deploy_full_stack.sh
```

脚本会自动：
1. 激活 `combo-avs` 环境。
2. 安装依赖。
3. 配置环境变量。
4. 启动服务 (端口 6006)。

---

## 第四步：访问使用

1. **建立简单的 HTTP 隧道** (这是最后一次用 SSH)：
   在本地电脑终端：
   ```powershell
   ssh -CNg -L 6006:127.0.0.1:6006 -p <端口> root@<域名>
   ```

2. **浏览器访问**：
   打开 http://127.0.0.1:6006/

**见证奇迹的时刻**：
- 你看到的是完整的 AVS2 网页。
- 这个网页是由 AutoDL 托管的。
- 上传视频 -> 也是传给 AutoDL。
- 推理 -> AutoDL 本地直连 GPU。
- **完全没有跨网段传输问题，速度飞快！**

---

### (进阶) 如果不想开 SSH 隧道

如果 AutoDL 开放了“自定义服务”功能（通常在控制台可以找到），你可以直接访问 `http://<AutoDL公网IP>:<映射端口>`，那样连 SSH 都不用挂了。
