# 实施计划

复用现有 SidebarTrigger、SidebarProvider 和 Tooltip，在侧栏品牌行放置同一个桌面开关，按展开状态更换内容和可访问名称。收起后的品牌图标在 hover/focus-visible 时显露展开图标，提示通过 Tooltip 呈现。主内容页头只在手机显示导航入口。

宪章检查：仅前端布局和操作入口调整，不修改业务、权限、数据库或外部边界；验证使用离线 fixture 与现有内存 E2E 服务。

补充桌面按钮位置、hover/focus、点击/键盘切换、折叠导航和手机抽屉回归；同步 docs，运行格式化、全量检查及受影响 Playwright，更新当前 UI 修复 PR。
