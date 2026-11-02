# Git 提交速查（实验 4 双人协作）

> 仓库：`https://github.com/laptop-d2e49ecm/basketball`（私有）
> 双方共用 `master`；队友视频主线建议开 `feature/video` 分支，完成后 GitHub 发 Pull Request 合并。

## 每次提交的固定四步

```bash
cd /d/Projects/python/basketball

git pull origin master        # ① 先拉取（对方可能推了新代码）

# ……改代码、自测……

git status                    # ② 确认改动范围，没有多余文件
git add <明确路径>             # ③ 如 git add exp4/frontend（不要用 add -A / add .）
git commit -m "区域：做了什么"  #    如 "前端：检测页-按置信度渐变框颜色"
git push origin master        # ④ 推送
```

## 规则与坑（本仓库实测经验）

| 规则 | 原因 |
|---|---|
| `git add` 只写明确路径 | `add -A` 曾把交接包解压目录（33MB 视频）卷进提交；现已有 ignore 兜底，但习惯要稳 |
| 提交粒度 = 一个小功能/一个 bug | 细粒度历史 = 报告分工证据 |
| push 被拒 → `git pull --rebase origin master` 再 push | 说明对方先推了 |
| `LF/CRLF` 警告无视 | Windows 正常现象 |
| `node_modules/ dist/ *.joblib *.pt 数据/` 不会入库 | .gitignore 已配好，模型权重走交接包 |

## 常用查看命令

```bash
git log --oneline -10          # 最近提交
git show <commit>              # 看某次提交改了什么
git diff                       # 未暂存的改动
```

## 队友分支工作流（视频主线推荐）

```bash
git checkout -b feature/video      # 建并切换分支
# ……开发，按上面四步提交（push 改为 git push origin feature/video）
# 完成后：GitHub 仓库页 → Pull Requests → New PR：feature/video → master
```

## 图形界面等价操作（PyCharm）

Git → Commit（Ctrl+K）：勾选文件、写消息、Commit and Push；Git 面板看历史。
