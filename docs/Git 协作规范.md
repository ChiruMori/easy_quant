# Git 协作规范

## 文档定位

本文档规定分支使用、提交边界、提交信息和本地钩子操作。开发原则和质量门禁见[项目宪章](../.specify/memory/constitution.md)。

## 分支

- `master` 是在线代码主分支。
- 功能开发从目标主分支创建短期分支，建议命名为 `feat/<topic>`、`fix/<topic>` 或 `docs/<topic>`。
- `specs` 的编号目录用于稳定标识 feature，不要求与分支名相同；本项目不启用 Spec Kit 的 Git 分支扩展。
- 不对共享分支执行强制推送，不提交生成物、真实环境配置或密钥。

## 提交边界

- 一个提交只完成一个可说明、可验证的目标。
- 代码行为变化与对应测试放在同一提交。
- 新能力或行为变化的 spec、plan、tasks 与其实现保持可追溯；完成后的 feature 文档按 flow-forward 冻结。
- 相关文档随实现同步维护，不单独遗留“补文档”提交。
- 提交前检查暂存内容，避免夹带本地配置、缓存、调试输出或无关格式修改。

## 提交信息

首行采用以下格式，摘要可以使用中文：

```text
<type>(<scope>): <summary>
```

`scope` 可省略；存在破坏性变更时在冒号前增加 `!`。首行最长 72 个字符，末尾不使用句号。需要正文时，首行与正文之间空一行。

允许的 `type`：

| 类型 | 用途 |
| --- | --- |
| `feat` | 新增面向使用方的能力 |
| `fix` | 修复缺陷 |
| `docs` | 仅调整文档 |
| `refactor` | 不改变外部行为的代码重构 |
| `perf` | 性能改进 |
| `test` | 仅新增或调整测试 |
| `build` | 依赖、构建或打包变化 |
| `ci` | CI/CD 配置变化 |
| `chore` | 不属于以上类别的工程维护 |

示例：

```text
feat(online): 增加流式对话接口
fix(config): 修复生产环境配置加载
docs: 补充本地开发说明
feat(api)!: 调整对话请求协议
```

Git 自动生成的 Merge 和 Revert 提交信息允许直接使用。

## 本地钩子

首次同步依赖后安装两类钩子：

```powershell
pnpm hooks:install
```

- `pre-commit`：仅在相关目录发生变化时运行。前端依次执行 Prettier 写入、ESLint 自动修复和 TypeScript 类型检查；后端依次执行 Ruff format、Ruff 安全修复和 Pyright。
- `commit-msg`：由 `tools/check_commit_message.py` 校验提交信息。

格式化或自动修复改动文件时，pre-commit 会终止当次提交。检查改动并重新暂存后再次提交即可，不得使用 `--no-verify` 绕过。

可单独验证提交信息：

```powershell
uv run --project backend python tools/check_commit_message.py .git/COMMIT_EDITMSG
```

不得使用 `--no-verify` 绕过钩子；若钩子误判，应修正规则并补充测试。

## 提交前检查

提交前至少执行：

```powershell
pnpm check
pnpm test:e2e
uv run --project backend pre-commit run --all-files
```

开发过程中可主动执行：

```powershell
pnpm fix          # Prettier、ESLint 与 Ruff 自动格式化/修复
pnpm check        # 全量静态检查、测试与构建
```

随后使用 `git diff --cached` 检查最终提交内容，并确认 `git status --short` 中没有遗漏的必要文件。
